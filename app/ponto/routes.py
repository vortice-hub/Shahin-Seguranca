from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.extensions import db, csrf
from app.models import PontoRegistro, PontoResumo, User, PontoAjuste, SolicitacaoAusencia
from app.utils import get_brasil_time, calcular_dia, format_minutes_to_hm, data_por_extenso
from datetime import datetime, date, timedelta
from sqlalchemy import func
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import logging
import calendar

logger = logging.getLogger(__name__)

ponto_bp = Blueprint('ponto', __name__, template_folder='templates', url_prefix='/ponto')

@ponto_bp.route('/api/gerar-token', methods=['GET'])
@login_required
def gerar_token_qrcode():
    if current_user.role == 'Terminal': return jsonify({'error': 'Terminal não gera token'}), 403
    s = URLSafeTimedSerializer(current_app.secret_key)
    token = s.dumps({'user_id': current_user.id, 'timestamp': get_brasil_time().timestamp()})
    return jsonify({'token': token})

@ponto_bp.route('/api/check-status', methods=['GET'])
@login_required
def check_status_ponto():
    if current_user.role == 'Terminal': return jsonify({'status': 'ignorar'})
    agora = get_brasil_time()
    ultimo_ponto = PontoRegistro.query.filter_by(user_id=current_user.id).order_by(PontoRegistro.id.desc()).first()
    if ultimo_ponto:
        dt_ponto = datetime.combine(ultimo_ponto.data_registro, ultimo_ponto.hora_registro)
        if (agora - dt_ponto).total_seconds() < 15:
            return jsonify({'marcado': True, 'tipo': ultimo_ponto.tipo, 'hora': ultimo_ponto.hora_registro.strftime('%H:%M')})
    return jsonify({'marcado': False})

@ponto_bp.route('/api/registrar-leitura', methods=['POST'])
@login_required
@csrf.exempt
def registrar_leitura_terminal():
    if current_user.role != 'Terminal' and current_user.role != 'Master': return jsonify({'error': 'Acesso negado.'}), 403
    token = request.json.get('token')
    if not token: return jsonify({'error': 'Token vazio'}), 400
    
    s = URLSafeTimedSerializer(current_app.secret_key)
    try:
        dados = s.loads(token, max_age=35)
        user_alvo = User.query.get(dados['user_id'])
        if not user_alvo: return jsonify({'error': 'Usuário inválido'}), 404
        hoje = get_brasil_time().date()
        
        ultimo = PontoRegistro.query.filter_by(user_id=user_alvo.id, data_registro=hoje).order_by(PontoRegistro.hora_registro.desc()).first()
        if ultimo:
            dt_ultimo = datetime.combine(hoje, ultimo.hora_registro)
            if (get_brasil_time() - dt_ultimo).total_seconds() < 60:
                 return jsonify({'error': f'Aguarde antes de bater o ponto novamente.'}), 400

        pontos_hoje = PontoRegistro.query.filter_by(user_id=user_alvo.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
        proxima = "Entrada"
        if len(pontos_hoje) == 1: proxima = "Ida Almoço"
        elif len(pontos_hoje) == 2: proxima = "Volta Almoço"
        elif len(pontos_hoje) == 3: proxima = "Saída"
        elif len(pontos_hoje) >= 4: proxima = "Extra"
        
        novo = PontoRegistro(user_id=user_alvo.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=proxima, latitude='QR-Code', longitude='Presencial')
        db.session.add(novo); db.session.commit()
        calcular_dia(user_alvo.id, hoje)
        return jsonify({'success': True, 'message': f'Ponto registrado: {proxima}', 'funcionario': user_alvo.real_name, 'hora': novo.hora_registro.strftime('%H:%M'), 'tipo': proxima})
    except SignatureExpired: return jsonify({'error': 'QR Code expirado.'}), 400
    except BadSignature: return jsonify({'error': 'QR Code inválido.'}), 400
    except Exception as e: return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@ponto_bp.route('/scanner')
@login_required
def terminal_scanner():
    if current_user.username != '12345678900' and current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    return render_template('ponto/terminal_leitura.html')

@ponto_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    if current_user.username == '12345678900': return redirect(url_for('ponto.terminal_scanner'))
    hoje = get_brasil_time().date()
    hoje_extenso = data_por_extenso(hoje)
    bloqueado, motivo = False, ""
    
    ausencia = SolicitacaoAusencia.query.filter(SolicitacaoAusencia.user_id == current_user.id, SolicitacaoAusencia.status == 'Aprovado', SolicitacaoAusencia.data_inicio <= hoje, SolicitacaoAusencia.data_fim >= hoje).first()
    if ausencia: bloqueado = True; motivo = f"Afastamento programado: {ausencia.tipo_ausencia}"
    elif current_user.escala == '5x2' and hoje.weekday() >= 5: bloqueado = True; motivo = "Fim de semana (Escala 5x2)."
    elif current_user.escala == '12x36' and current_user.data_inicio_escala:
        if (hoje - current_user.data_inicio_escala).days % 2 != 0: bloqueado = True; motivo = "Dia de folga (Escala 12x36)."

    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
    prox = "Entrada"
    if len(pontos) == 1: prox = "Ida Almoço"
    elif len(pontos) == 2: prox = "Volta Almoço"
    elif len(pontos) == 3: prox = "Saída"
    elif len(pontos) >= 4: prox = "Extra"

    if request.method == 'POST':
        if bloqueado: return redirect(url_for('main.dashboard'))
        db.session.add(PontoRegistro(user_id=current_user.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=prox, latitude=request.form.get('latitude'), longitude=request.form.get('longitude')))
        db.session.commit()
        calcular_dia(current_user.id, hoje)
        return redirect(url_for('main.dashboard'))
    return render_template('ponto/registro.html', proxima_acao=prox, hoje_extenso=hoje_extenso, pontos=pontos, bloqueado=bloqueado, motivo=motivo, hoje=hoje)

@ponto_bp.route('/espelho')
@login_required
def espelho_ponto():
    target_user_id = request.args.get('user_id', type=int) or current_user.id
    if target_user_id != current_user.id and current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    user = User.query.get_or_404(target_user_id)
    mes_ref = request.args.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    try: ano, mes = map(int, mes_ref.split('-'))
    except: hoje = get_brasil_time(); ano, mes = hoje.year, hoje.month; mes_ref = hoje.strftime('%Y-%m')
    
    resumos = PontoResumo.query.filter(PontoResumo.user_id == target_user_id, func.extract('year', PontoResumo.data_referencia) == ano, func.extract('month', PontoResumo.data_referencia) == mes).order_by(PontoResumo.data_referencia).all()
    detalhes = {}
    for r in resumos:
        batidas = PontoRegistro.query.filter_by(user_id=target_user_id, data_registro=r.data_referencia).order_by(PontoRegistro.hora_registro).all()
        detalhes[r.id] = [b.hora_registro.strftime('%H:%M') for b in batidas]
    dias_semana = {0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex', 5: 'Sáb', 6: 'Dom'}
    return render_template('ponto/ponto_espelho.html', resumos=resumos, user=user, detalhes=detalhes, format_hm=format_minutes_to_hm, mes_ref=mes_ref, dias_semana=dias_semana)

@ponto_bp.route('/solicitar-ajuste', methods=['GET', 'POST'])
@login_required
def solicitar_ajuste():
    pontos_dia, data_selecionada = [], None
    meus_ajustes = PontoAjuste.query.filter_by(user_id=current_user.id).order_by(PontoAjuste.created_at.desc()).limit(20).all()
    if request.method == 'POST':
        if request.form.get('acao') == 'buscar':
            try: 
                data_selecionada = datetime.strptime(request.form.get('data_busca'), '%Y-%m-%d').date()
                pontos_dia = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=data_selecionada).order_by(PontoRegistro.hora_registro).all()
            except: pass
        elif request.form.get('acao') == 'enviar':
            try:
                dt_obj = datetime.strptime(request.form.get('data_ref'), '%Y-%m-%d').date()
                p_id = int(request.form.get('ponto_id')) if request.form.get('ponto_id') else None
                solic = PontoAjuste(user_id=current_user.id, data_referencia=dt_obj, ponto_original_id=p_id, novo_horario=request.form.get('novo_horario'), tipo_batida=request.form.get('tipo_batida'), tipo_solicitacao=request.form.get('tipo_solicitacao'), justificativa=request.form.get('justificativa'))
                db.session.add(solic); db.session.commit(); flash('Enviado!')
                return redirect(url_for('ponto.solicitar_ajuste'))
            except: pass
            
    dados_extras = {}
    for p in meus_ajustes:
        if p.ponto_original_id:
            original = PontoRegistro.query.get(p.ponto_original_id)
            if original: dados_extras[p.id] = original.hora_registro.strftime('%H:%M')
    return render_template('ponto/solicitar_ajuste.html', pontos=pontos_dia, data_sel=data_selecionada, meus_ajustes=meus_ajustes, extras=dados_extras)

@ponto_bp.route('/escala', methods=['GET'])
@login_required
def minha_escala():
    hoje = get_brasil_time().date()
    ano = request.args.get('ano', hoje.year, type=int)
    mes = request.args.get('mes', hoje.month, type=int)
    _, num_dias = calendar.monthrange(ano, mes)
    dias_mes = []
    
    for dia in range(1, num_dias + 1):
        dt_atual = date(ano, mes, dia)
        tipo_dia = 'Trabalho'
        
        ausencia = SolicitacaoAusencia.query.filter(
            SolicitacaoAusencia.user_id == current_user.id,
            SolicitacaoAusencia.status == 'Aprovado',
            SolicitacaoAusencia.data_inicio <= dt_atual,
            SolicitacaoAusencia.data_fim >= dt_atual
        ).first()
        
        if ausencia: tipo_dia = ausencia.tipo_ausencia
        else:
            if current_user.escala == '5x2' and dt_atual.weekday() >= 5: tipo_dia = 'Folga'
            elif current_user.escala == '12x36' and current_user.data_inicio_escala:
                if (dt_atual - current_user.data_inicio_escala).days % 2 != 0: tipo_dia = 'Folga'
        
        dia_semana_layout = (dt_atual.weekday() + 1) % 7 
        dias_mes.append({'data': dt_atual, 'tipo': tipo_dia, 'dia_semana': dia_semana_layout})

    return render_template('ponto/minha_escala.html', ano=ano, mes=mes, dias_mes=dias_mes, hoje=hoje)

@ponto_bp.route('/solicitar-ferias', methods=['GET', 'POST'])
@login_required
def solicitar_ferias():
    if not current_user.data_admissao:
        flash("Sua data de admissão não está cadastrada. Solicite ao RH para regularizar.", "warning")

    # Módulo Analítico de Férias CLT (Cálculo de Faltas e Direitos)
    dias_direito = 30
    faltas = 0
    saldo = 0
    dias_usados = 0

    if current_user.data_admissao:
        hoje = get_brasil_time().date()
        um_ano_atras = hoje - timedelta(days=365)
        # Conta faltas injustificadas no último ano de trabalho
        faltas = PontoResumo.query.filter(
            PontoResumo.user_id == current_user.id,
            PontoResumo.data_referencia >= um_ano_atras,
            PontoResumo.status_dia == 'Falta'
        ).count()

        # Regra CLT: Redução de dias por faltas injustificadas
        if faltas <= 5: dias_direito = 30
        elif faltas <= 14: dias_direito = 24
        elif faltas <= 23: dias_direito = 18
        elif faltas <= 32: dias_direito = 12
        else: dias_direito = 0

        # Conta dias já aprovados/pendentes no sistema
        ausencias_ano = SolicitacaoAusencia.query.filter(
            SolicitacaoAusencia.user_id == current_user.id,
            SolicitacaoAusencia.tipo_ausencia == 'Férias',
            SolicitacaoAusencia.status.in_(['Aprovado', 'Pendente'])
        ).all()
        dias_usados = sum(a.quantidade_dias for a in ausencias_ano)
        saldo = dias_direito - dias_usados

    if request.method == 'POST':
        tipo = request.form.get('tipo_ausencia')
        dt_inicio = datetime.strptime(request.form.get('data_inicio'), '%Y-%m-%d').date()
        dt_fim = datetime.strptime(request.form.get('data_fim'), '%Y-%m-%d').date()
        obs = request.form.get('observacao', '')
        
        # Abono Pecuniário (Vender Férias)
        vender_ferias = request.form.get('vender_ferias') == 'sim'
        
        if dt_inicio > dt_fim:
            flash("A data de início não pode ser maior que a data de fim.", "error")
            return redirect(url_for('ponto.solicitar_ferias'))
            
        qtd_dias = (dt_fim - dt_inicio).days + 1
        dias_abono = 0

        # --- VALIDAÇÕES ESTRITAS DA CLT PARA FÉRIAS ---
        if tipo == 'Férias':
            if not current_user.data_admissao:
                flash("Data de admissão ausente. O RH deve configurar seu perfil antes de solicitar férias.", "error")
                return redirect(url_for('ponto.solicitar_ferias'))

            # Validação de Saldo e Venda (Abono)
            if vender_ferias:
                dias_abono = qtd_dias // 2 # A lógica de venda costuma ser vender o terço. Ex: tira 20, vende 10.
                if dias_abono > (dias_direito / 3):
                    flash(f"A CLT permite vender no máximo 1/3 das férias (Max: {int(dias_direito/3)} dias).", "error")
                    return redirect(url_for('ponto.solicitar_ferias'))
                
                total_descontado = qtd_dias + dias_abono
                if total_descontado > saldo:
                    flash(f"Saldo insuficiente. Você tem {saldo} dias disponíveis, mas o pedido (Descanso + Venda) totaliza {total_descontado} dias.", "error")
                    return redirect(url_for('ponto.solicitar_ferias'))
            else:
                if qtd_dias > saldo:
                    flash(f"Saldo insuficiente. Você possui apenas {saldo} dias.", "error")
                    return redirect(url_for('ponto.solicitar_ferias'))

            # Validação: Fracionamento (mínimo de 5 dias)
            if qtd_dias < 5:
                flash("Pela CLT (Reforma 2017), o período fracionado de férias não pode ser inferior a 5 dias.", "error")
                return redirect(url_for('ponto.solicitar_ferias'))

            # Validação: Início antes do DSR (Art. 134, §3º CLT)
            # Ex: Se escala é 5x2 (folga Sáb/Dom), não pode começar Quinta(3) ou Sexta(4)
            if current_user.escala == '5x2' and dt_inicio.weekday() in [3, 4]:
                flash("Ilegal: O início das férias não pode ocorrer nos 2 dias que antecedem o repouso semanal (Sáb/Dom).", "error")
                return redirect(url_for('ponto.solicitar_ferias'))

        nova_solicitacao = SolicitacaoAusencia(
            user_id=current_user.id, tipo_ausencia=tipo,
            data_inicio=dt_inicio, data_fim=dt_fim,
            quantidade_dias=qtd_dias, abono_pecuniario=vender_ferias,
            dias_abono=dias_abono, observacao=obs
        )
        db.session.add(nova_solicitacao)
        db.session.commit()
        flash("Solicitação validada e enviada com sucesso ao RH!", "success")
        return redirect(url_for('ponto.solicitar_ferias'))

    minhas_solicitacoes = SolicitacaoAusencia.query.filter_by(user_id=current_user.id).order_by(SolicitacaoAusencia.data_solicitacao.desc()).all()
    
    return render_template(
        'ponto/solicitar_ferias.html', 
        minhas_solicitacoes=minhas_solicitacoes,
        dias_direito=dias_direito,
        faltas=faltas,
        saldo=saldo,
        dias_usados=dias_usados
    )

@ponto_bp.route('/admin/ausencias', methods=['GET', 'POST'])
@login_required
def gestao_ausencias():
    if current_user.role != 'Master' and current_user.username != '50097952800': return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        solic_id = request.form.get('solicitacao_id')
        acao = request.form.get('acao')
        solicitacao = SolicitacaoAusencia.query.get_or_404(solic_id)
        
        if acao == 'aprovar':
            solicitacao.status = 'Aprovado'
            for i in range(solicitacao.quantidade_dias):
                dia_atual = solicitacao.data_inicio + timedelta(days=i)
                ponto = PontoResumo.query.filter_by(user_id=solicitacao.user_id, data_referencia=dia_atual).first()
                if ponto:
                    ponto.status_dia = solicitacao.tipo_ausencia
                    ponto.minutos_esperados = 0
                    ponto.minutos_saldo = ponto.minutos_trabalhados
                else:
                    novo_ponto = PontoResumo(user_id=solicitacao.user_id, data_referencia=dia_atual, minutos_trabalhados=0, minutos_esperados=0, minutos_saldo=0, status_dia=solicitacao.tipo_ausencia)
                    db.session.add(novo_ponto)
            flash(f"Solicitação aprovada. O ponto foi atualizado.", "success")
            
        elif acao == 'recusar':
            solicitacao.status = 'Recusado'
            flash("Solicitação recusada.", "success")
            
        elif acao == 'remover':
            if solicitacao.status == 'Aprovado':
                user = solicitacao.user
                for i in range(solicitacao.quantidade_dias):
                    dia_atual = solicitacao.data_inicio + timedelta(days=i)
                    ponto = PontoResumo.query.filter_by(user_id=solicitacao.user_id, data_referencia=dia_atual).first()
                    if ponto and ponto.status_dia == solicitacao.tipo_ausencia:
                        meta = user.carga_horaria or 528
                        if user.escala == '5x2' and dia_atual.weekday() >= 5: meta = 0
                        elif user.escala == '12x36' and user.data_inicio_escala:
                            if (dia_atual - user.data_inicio_escala).days % 2 != 0: meta = 0
                            else: meta = 720
                        ponto.status_dia = 'OK'
                        ponto.minutos_esperados = meta
                        ponto.minutos_saldo = ponto.minutos_trabalhados - meta
            solicitacao.status = 'Cancelado'
            flash("Férias revogadas com sucesso. O espelho de ponto foi restaurado.", "success")
            
        db.session.commit()
        return redirect(url_for('ponto.gestao_ausencias'))

    todas_solicitacoes = SolicitacaoAusencia.query.order_by(SolicitacaoAusencia.data_solicitacao.desc()).all()
    return render_template('ponto/gestao_ausencias.html', solicitacoes=todas_solicitacoes)

@ponto_bp.route('/admin/controle-escala', methods=['GET'])
@login_required
def controle_escala():
    if current_user.role != 'Master' and current_user.username != '50097952800': return redirect(url_for('main.dashboard'))
    data_str = request.args.get('data_ref')
    if data_str: data_ref = datetime.strptime(data_str, '%Y-%m-%d').date()
    else: data_ref = get_brasil_time().date()
    
    usuarios = User.query.filter(User.username != '12345678900').order_by(User.real_name).all()
    trabalhando, folga = [], []
    
    for u in usuarios:
        ausencia = SolicitacaoAusencia.query.filter(SolicitacaoAusencia.user_id == u.id, SolicitacaoAusencia.status == 'Aprovado', SolicitacaoAusencia.data_inicio <= data_ref, SolicitacaoAusencia.data_fim >= data_ref).first()
        escala_trabalho = True
        if u.escala == '5x2' and data_ref.weekday() >= 5: escala_trabalho = False
        elif u.escala == '12x36' and u.data_inicio_escala:
            if (data_ref - u.data_inicio_escala).days % 2 != 0: escala_trabalho = False
        
        pontos = PontoRegistro.query.filter_by(user_id=u.id, data_registro=data_ref).order_by(PontoRegistro.hora_registro).all()
        status_batida = f"{len(pontos)} marcações" if pontos else "Sem marcação"
        info = {'user': u, 'ausencia': ausencia, 'batidas': status_batida}
        
        if ausencia: info['motivo'] = ausencia.tipo_ausencia; folga.append(info)
        elif not escala_trabalho: info['motivo'] = 'Folga Escala'; folga.append(info)
        else: trabalhando.append(info)
            
    return render_template('ponto/controle_escala.html', trabalhando=trabalhando, folga=folga, data_ref=data_ref)


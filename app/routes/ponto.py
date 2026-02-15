from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import PontoRegistro, PontoResumo, User, PontoAjuste
from app.utils import get_brasil_time, calcular_dia, format_minutes_to_hm, data_por_extenso
from datetime import datetime, date
from sqlalchemy import func
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

ponto_bp = Blueprint('ponto', __name__, url_prefix='/ponto')

# --- API QR CODE ---
@ponto_bp.route('/api/gerar-token', methods=['GET'])
@login_required
def gerar_token_qrcode():
    if current_user.role == 'Terminal': return jsonify({'error': 'Terminal não gera token'}), 403
    s = URLSafeTimedSerializer(current_app.secret_key)
    token = s.dumps({'user_id': current_user.id, 'timestamp': get_brasil_time().timestamp()})
    return jsonify({'token': token})

@ponto_bp.route('/api/registrar-leitura', methods=['POST'])
@login_required
def registrar_leitura_terminal():
    if current_user.role != 'Terminal' and current_user.role != 'Master': return jsonify({'error': 'Acesso negado.'}), 403
    data = request.json
    token = data.get('token')
    if not token: return jsonify({'error': 'Token vazio'}), 400
    s = URLSafeTimedSerializer(current_app.secret_key)
    try:
        dados = s.loads(token, max_age=35)
        user_alvo = User.query.get(dados['user_id'])
        if not user_alvo: return jsonify({'error': 'Usuário inválido'}), 404
        
        hoje = get_brasil_time().date()
        pontos_hoje = PontoRegistro.query.filter_by(user_id=user_alvo.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
        proxima = "Entrada"
        if len(pontos_hoje) == 1: proxima = "Ida Almoço"
        elif len(pontos_hoje) == 2: proxima = "Volta Almoço"
        elif len(pontos_hoje) == 3: proxima = "Saída"
        elif len(pontos_hoje) >= 4: proxima = "Extra"
        
        novo = PontoRegistro(user_id=user_alvo.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=proxima, latitude='QR-Code', longitude='Presencial')
        db.session.add(novo); db.session.commit(); calcular_dia(user_alvo.id, hoje)
        return jsonify({'success': True, 'message': f'Ponto registrado: {proxima}', 'funcionario': user_alvo.real_name, 'hora': novo.hora_registro.strftime('%H:%M')})
    except SignatureExpired: return jsonify({'error': 'QR Code expirado.'}), 400
    except BadSignature: return jsonify({'error': 'QR Code inválido.'}), 400
    except Exception as e: return jsonify({'error': f'Erro interno: {str(e)}'}), 500

# --- ROTAS DE INTERFACE ---

@ponto_bp.route('/scanner')
@login_required
def terminal_scanner():
    if current_user.role != 'Terminal' and current_user.role != 'Master':
        flash('Acesso restrito.')
        return redirect(url_for('main.dashboard'))
    return render_template('ponto/terminal_leitura.html')

@ponto_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    if current_user.role == 'Terminal': return redirect(url_for('ponto.terminal_scanner'))

    hoje = get_brasil_time().date()
    hoje_extenso = data_por_extenso(hoje)
    
    bloqueado = False; motivo = ""
    if current_user.escala == '5x2' and hoje.weekday() >= 5: bloqueado = True; motivo = "Não é possível realizar a marcação de ponto."
    elif current_user.escala == '12x36' and current_user.data_inicio_escala:
        if (hoje - current_user.data_inicio_escala).days % 2 != 0: bloqueado = True; motivo = "Não é possível realizar a marcação de ponto."

    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
    prox = "Entrada"
    if len(pontos) == 1: prox = "Ida Almoço"
    elif len(pontos) == 2: prox = "Volta Almoço"
    elif len(pontos) == 3: prox = "Saída"
    elif len(pontos) >= 4: prox = "Extra"

    if request.method == 'POST':
        if bloqueado: flash('Bloqueado'); return redirect(url_for('main.dashboard'))
        db.session.add(PontoRegistro(user_id=current_user.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=prox, latitude=request.form.get('latitude'), longitude=request.form.get('longitude')))
        db.session.commit(); calcular_dia(current_user.id, hoje)
        return redirect(url_for('main.dashboard'))
    
    # CORREÇÃO: Passando 'hoje' explicitamente para o template
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
    pontos_dia = []; data_selecionada = None
    meus_ajustes = PontoAjuste.query.filter_by(user_id=current_user.id).order_by(PontoAjuste.created_at.desc()).limit(20).all()
    if request.method == 'POST':
        if request.form.get('acao') == 'buscar':
            try: data_selecionada = datetime.strptime(request.form.get('data_busca'), '%Y-%m-%d').date(); pontos_dia = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=data_selecionada).order_by(PontoRegistro.hora_registro).all()
            except: flash('Data inválida')
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
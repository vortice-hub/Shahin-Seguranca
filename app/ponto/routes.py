from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, g
from flask_login import login_required, current_user
from app.extensions import db, csrf
from app.models import PontoRegistro, PontoResumo, User, PontoAjuste, SolicitacaoAusencia, Empresa
from app.utils import get_brasil_time, format_minutes_to_hm, data_por_extenso, enviar_notificacao
from datetime import datetime, date, timedelta
import logging
import calendar

# --- IMPORTAÇÃO DOS NOVOS SERVICES E REPOSITORIES ---
from app.services.ponto_service import PontoService
from app.services.face_service import FaceService
from app.documentos.storage import salvar_imagem_storage
from app.repositories.ponto_repository import PontoRegistroRepository, PontoAjusteRepository, PontoResumoRepository, SolicitacaoAusenciaRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

ponto_bp = Blueprint('ponto', __name__, template_folder='templates', url_prefix='/ponto')

# ==============================================================================
# 📸 MÓDULO: CADASTRO BIOMÉTRICO (App do Funcionário)
# ==============================================================================
@ponto_bp.route('/registrar', methods=['GET'])
@login_required
def registrar_ponto():
    """Tela do App do funcionário para cadastrar a biometria."""
    if current_user.role == 'Terminal': return redirect(url_for('ponto.terminal_scanner'))
    
    # Verifica se o funcionário já tem o rosto salvo no banco
    biometria_cadastrada = current_user.face_encoding is not None
        
    return render_template('ponto/registro.html', biometria_cadastrada=biometria_cadastrada)

@ponto_bp.route('/api/cadastrar-biometria', methods=['POST'])
@login_required
@csrf.exempt
def cadastrar_biometria():
    """Recebe a foto do celular do funcionário (como Ficheiro Nativo), processa a I.A. e salva no Bucket."""
    if current_user.role == 'Terminal': return jsonify({'error': 'Acesso negado'}), 403
    
    # ALTERAÇÃO ALTERNATIVA 2: Recebe um ficheiro real em vez de JSON Base64
    if 'image' not in request.files: 
        return jsonify({'error': 'Nenhuma imagem enviada'}), 400
        
    file = request.files['image']
    raw_bytes = file.read()

    face_service = FaceService()
    sucesso, resultado = face_service.cadastrar_face(raw_bytes)

    if not sucesso:
        return jsonify({'success': False, 'error': resultado})

    try:
        empresa = Empresa.query.get(current_user.empresa_id)
        nome_arquivo = f"biometria_user_{current_user.id}.jpg"
        
        # Salva a imagem visual no Bucket GCS
        caminho_gcs = salvar_imagem_storage(resultado['image_bytes'], 'biometria', empresa.slug, nome_arquivo)

        if not caminho_gcs:
            return jsonify({'success': False, 'error': 'Erro de infraestrutura ao salvar a foto segura.'})

        # Salva o mapa matemático na base de dados
        user_repo = UserRepository()
        user = user_repo.get_by_id(current_user.id)
        user.face_encoding = resultado['encoding']
        user.foto_biometria_url = caminho_gcs
        user_repo.commit()

        return jsonify({'success': True, 'message': 'Biometria Facial validada e cadastrada com sucesso!'})
    except Exception as e:
        logger.error(f"Erro no cadastro biométrico: {e}")
        return jsonify({'success': False, 'error': 'Erro interno ao gravar dados.'})

# ==============================================================================
# 🏢 MÓDULO: TERMINAL INTELIGENTE (Tablet na Portaria)
# ==============================================================================
@ponto_bp.route('/scanner')
@login_required
def terminal_scanner():
    """Abre a tela do Terminal que fica com a câmera ligada."""
    if current_user.role != 'Terminal' and current_user.role != 'Master': 
        return redirect(url_for('main.dashboard'))
    return render_template('ponto/terminal_leitura.html')

@ponto_bp.route('/api/reconhecer-facial', methods=['POST'])
@login_required
@csrf.exempt
def reconhecer_facial():
    """Recebe a foto do Terminal (Ficheiro Nativo) e procura quem é o funcionário."""
    if current_user.role != 'Terminal' and current_user.role != 'Master':
        return jsonify({'error': 'Acesso negado.'}), 403

    # ALTERAÇÃO ALTERNATIVA 2: Recebe ficheiro real
    if 'image' not in request.files: 
        return jsonify({'error': 'Nenhuma imagem enviada'}), 400
        
    file = request.files['image']
    raw_bytes = file.read()

    # Busca apenas os funcionários da mesma empresa do Terminal
    usuarios_empresa = User.query.filter_by(empresa_id=current_user.empresa_id).all()

    face_service = FaceService()
    user_id = face_service.reconhecer_face(raw_bytes, usuarios_empresa)

    if not user_id:
        return jsonify({'success': False, 'error': 'Rosto não reconhecido ou baixa similaridade.'})

    user_repo = UserRepository()
    user_alvo = user_repo.get_by_id(user_id)
    ponto_service = PontoService()
    hoje = get_brasil_time().date()

    # Verifica se o funcionário está bloqueado (ex: Férias)
    bloqueado, motivo = ponto_service.verificar_bloqueio_ponto(user_alvo, hoje)
    if bloqueado:
        return jsonify({'success': False, 'error': f"Bloqueado: {motivo}"})

    # Calcula qual é a próxima batida dele (Entrada, Saída, etc)
    proxima = ponto_service.determinar_proxima_batida(user_id, hoje)
    hora_atual = get_brasil_time().strftime('%H:%M')

    return jsonify({
        'success': True,
        'user_id': user_id,
        'nome': user_alvo.real_name,
        'tipo': proxima,
        'hora': hora_atual
    })

@ponto_bp.route('/api/confirmar-ponto', methods=['POST'])
@login_required
@csrf.exempt
def confirmar_ponto():
    """Grava o ponto oficialmente após o funcionário apertar 'SIM' na tela."""
    if current_user.role != 'Terminal' and current_user.role != 'Master':
        return jsonify({'error': 'Acesso negado.'}), 403

    user_id = request.json.get('user_id')
    if not user_id: 
        return jsonify({'error': 'ID do usuário não fornecido.'}), 400

    user_repo = UserRepository()
    user_alvo = user_repo.get_by_id(user_id)

    # Trava de Segurança Multi-Tenant
    if not user_alvo or user_alvo.empresa_id != current_user.empresa_id:
        return jsonify({'error': 'Tentativa de fraude bloqueada.'}), 403

    tempo_agora = get_brasil_time()
    hoje = tempo_agora.date()

    ponto_service = PontoService()
    reg_repo = PontoRegistroRepository()

    # Trava de Anti-Spam (Evita bater 2 vezes em menos de 1 minuto)
    ultimo = reg_repo.get_last_by_user_and_date(user_alvo.id, hoje)
    if ultimo:
        dt_ultimo = datetime.combine(hoje, ultimo.hora_registro)
        if (tempo_agora - dt_ultimo).total_seconds() < 60:
             return jsonify({'error': 'Aguarde um minuto antes de bater o ponto novamente.'}), 400

    proxima = ponto_service.determinar_proxima_batida(user_alvo.id, hoje)

    novo = PontoRegistro(
        user_id=user_alvo.id, data_registro=hoje, hora_registro=tempo_agora.time(),
        tipo=proxima, latitude='Biometria Facial', longitude='Terminal Portaria',
        empresa_id=current_user.empresa_id
    )
    reg_repo.add(novo)
    reg_repo.commit()

    # Recalcula o espelho de ponto imediatamente
    ponto_service.calcular_dia(user_alvo.id, hoje)

    return jsonify({'success': True})

# ==============================================================================
# 📊 OUTRAS ROTAS (ESPELHO, ESCALA, FÉRIAS) - [MANTIDAS INTACTAS]
# ==============================================================================
@ponto_bp.route('/espelho')
@login_required
def espelho_ponto():
    target_user_id = request.args.get('user_id', type=int) or current_user.id
    
    if target_user_id != current_user.id and current_user.role != 'Master': 
        return redirect(url_for('main.dashboard'))
    
    user_repo = UserRepository()
    user = user_repo.get_by_id(target_user_id)
    
    if not user or user.empresa_id != current_user.empresa_id:
        return redirect(url_for('main.dashboard'))
    
    agora_br = get_brasil_time()
    mes_ref = request.args.get('mes_ref') or agora_br.strftime('%Y-%m')
    
    try: ano, mes = map(int, mes_ref.split('-'))
    except: ano, mes = agora_br.year, agora_br.month; mes_ref = agora_br.strftime('%Y-%m')
    
    resumo_repo = PontoResumoRepository()
    reg_repo = PontoRegistroRepository()
    
    resumos = resumo_repo.get_by_user_and_month(target_user_id, ano, mes)
    
    detalhes = {}
    for r in resumos:
        batidas = reg_repo.get_by_user_and_date(target_user_id, r.data_referencia)
        detalhes[r.id] = [b.hora_registro.strftime('%H:%M') for b in batidas]
    
    dias_semana = {0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex', 5: 'Sáb', 6: 'Dom'}
    return render_template('ponto/ponto_espelho.html', resumos=resumos, user=user, detalhes=detalhes, format_hm=format_minutes_to_hm, mes_ref=mes_ref, dias_semana=dias_semana)

@ponto_bp.route('/solicitar-ajuste', methods=['GET', 'POST'])
@login_required
def solicitar_ajuste():
    pontos_dia, data_selecionada = [], None
    ajuste_repo = PontoAjusteRepository()
    reg_repo = PontoRegistroRepository()
    
    meus_ajustes = ajuste_repo.get_by_user(current_user.id)
    
    if request.method == 'POST':
        if request.form.get('acao') == 'buscar':
            try: 
                data_selecionada = datetime.strptime(request.form.get('data_busca'), '%Y-%m-%d').date()
                pontos_dia = reg_repo.get_by_user_and_date(current_user.id, data_selecionada)
            except: pass
        elif request.form.get('acao') == 'enviar':
            try:
                dt_obj = datetime.strptime(request.form.get('data_ref'), '%Y-%m-%d').date()
                p_id = int(request.form.get('ponto_id')) if request.form.get('ponto_id') else None
                
                solic = PontoAjuste(
                    user_id=current_user.id, data_referencia=dt_obj, ponto_original_id=p_id, 
                    novo_horario=request.form.get('novo_horario'), tipo_batida=request.form.get('tipo_batida'), 
                    tipo_solicitacao=request.form.get('tipo_solicitacao'), justificativa=request.form.get('justificativa'),
                    empresa_id=current_user.empresa_id
                )
                ajuste_repo.add(solic); ajuste_repo.commit()
                
                master_empresa = User.query.filter_by(empresa_id=current_user.empresa_id, role='Master').first()
                if master_empresa:
                    enviar_notificacao(master_empresa.id, f"{current_user.real_name} solicitou um Ajuste de Ponto.", "/ponto/admin/solicitacoes")
                
                flash('Solicitação de ajuste enviada com sucesso!')
                return redirect(url_for('ponto.solicitar_ajuste'))
            except: flash('Erro ao processar solicitação.', 'error')
            
    dados_extras = {}
    for p in meus_ajustes:
        if p.ponto_original_id:
            original = reg_repo.get_by_id(p.ponto_original_id)
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
    
    ausencia_repo = SolicitacaoAusenciaRepository()
    
    for dia in range(1, num_dias + 1):
        dt_atual = date(ano, mes, dia)
        tipo_dia = 'Trabalho'
        
        ausencia = ausencia_repo.get_aprovada_por_data(current_user.id, dt_atual)
        
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
        flash("Sua data de admissão não está cadastrada. Solicite ao RH.", "warning")

    resumo_repo = PontoResumoRepository()
    ausencia_repo = SolicitacaoAusenciaRepository()
    ponto_service = PontoService()

    dias_direito = 30
    faltas = 0
    saldo = 0
    dias_usados = 0

    if current_user.data_admissao:
        hoje = get_brasil_time().date()
        um_ano_atras = hoje - timedelta(days=365)
        
        faltas = resumo_repo.get_faltas_ultimos_dias(current_user.id, um_ano_atras)

        if faltas <= 5: dias_direito = 30
        elif faltas <= 14: dias_direito = 24
        elif faltas <= 23: dias_direito = 18
        elif faltas <= 32: dias_direito = 12
        else: dias_direito = 0

        ausencias_ano = ausencia_repo.get_by_user_and_type(current_user.id, 'Férias')
        dias_usados = sum(a.quantidade_dias + a.dias_abono for a in ausencias_ano if a.status == 'Aprovado')
        saldo = dias_direito - dias_usados

    if request.method == 'POST':
        try:
             tipo = ponto_service.processar_solicitacao_ferias(current_user, request.form, saldo)
             master_empresa = User.query.filter_by(empresa_id=current_user.empresa_id, role='Master').first()
             if master_empresa:
                  enviar_notificacao(master_empresa.id, f"{current_user.real_name} enviou uma solicitação de {tipo}.", "/ponto/admin/ausencias")
             flash("Solicitação validada e enviada com sucesso ao RH!", "success")
        except ValueError as ve:
             flash(str(ve), "error")
        return redirect(url_for('ponto.solicitar_ferias'))

    minhas_solicitacoes = ausencia_repo.get_by_user(current_user.id)
    return render_template('ponto/solicitar_ferias.html', minhas_solicitacoes=minhas_solicitacoes, dias_direito=dias_direito, faltas=faltas, saldo=saldo, dias_usados=dias_usados)

@ponto_bp.route('/admin/ausencias', methods=['GET', 'POST'])
@login_required
def gestao_ausencias():
    if current_user.role != 'Master' and str(current_user.username) != '50097952800': 
        return redirect(url_for('main.dashboard'))

    ausencia_repo = SolicitacaoAusenciaRepository()
    resumo_repo = PontoResumoRepository()
    user_repo = UserRepository()

    if request.method == 'POST':
        solic_id = request.form.get('solicitacao_id')
        acao = request.form.get('acao')
        solicitacao = ausencia_repo.get_by_id(solic_id)
        if not solicitacao: return redirect(url_for('ponto.gestao_ausencias'))
        
        try:
            if acao == 'aprovar':
                solicitacao.status = 'Aprovado'
                for i in range(solicitacao.quantidade_dias):
                    dia_atual = solicitacao.data_inicio + timedelta(days=i)
                    ponto = resumo_repo.get_by_user_and_date(solicitacao.user_id, dia_atual)
                    if ponto:
                        ponto.status_dia = solicitacao.tipo_ausencia
                        ponto.minutos_esperados = 0
                        ponto.minutos_saldo = ponto.minutos_trabalhados
                    else:
                        novo_ponto = PontoResumo(user_id=solicitacao.user_id, data_referencia=dia_atual, minutos_trabalhados=0, minutos_esperados=0, minutos_saldo=0, status_dia=solicitacao.tipo_ausencia, empresa_id=g.empresa_id)
                        resumo_repo.add(novo_ponto)
                
                enviar_notificacao(solicitacao.user_id, f"A sua solicitação de {solicitacao.tipo_ausencia} foi APROVADA.", "/ponto/solicitar-ferias")
                flash(f"Solicitação aprovada e ponto atualizado.", "success")
                
            elif acao == 'recusar':
                solicitacao.status = 'Recusado'
                enviar_notificacao(solicitacao.user_id, f"A sua solicitação de {solicitacao.tipo_ausencia} foi RECUSADA.", "/ponto/solicitar-ferias")
                flash("Solicitação recusada.", "success")
              
            elif acao == 'remover':
                if solicitacao.status == 'Aprovado':
                    target_user = user_repo.get_by_id(solicitacao.user_id)
                    for i in range(solicitacao.quantidade_dias):
                        dia_atual = solicitacao.data_inicio + timedelta(days=i)
                        ponto = resumo_repo.get_by_user_and_date(solicitacao.user_id, dia_atual)
                        if ponto and ponto.status_dia == solicitacao.tipo_ausencia:
                            meta = target_user.carga_horaria or 528
                            if target_user.escala == '5x2' and dia_atual.weekday() >= 5: meta = 0
                            elif target_user.escala == '12x36' and target_user.data_inicio_escala:
                                if (dia_atual - target_user.data_inicio_escala).days % 2 != 0: meta = 0
                                else: meta = 720
                            ponto.status_dia = 'OK'
                            ponto.minutos_esperados = meta
                            ponto.minutos_saldo = ponto.minutos_trabalhados - meta
                solicitacao.status = 'Cancelado'
                enviar_notificacao(solicitacao.user_id, f"O seu período de {solicitacao.tipo_ausencia} foi CANCELADO.", "/ponto/solicitar-ferias")
                flash("Férias revogadas e espelho de ponto restaurado.", "success")
                
            ausencia_repo.commit()
        except Exception as e:
            ausencia_repo.rollback()
            flash(f"Erro ao processar: {e}", "error")
            
        return redirect(url_for('ponto.gestao_ausencias'))

    alertas_vencimento = []
    hoje = get_brasil_time().date()
    usuarios_clt = user_repo.get_all() 
    
    for u in usuarios_clt:
        if u.data_admissao:
            dias_trabalhados = (hoje - u.data_admissao).days
            anos_completos = dias_trabalhados // 365
            
            if anos_completos >= 1:
                ausencias = ausencia_repo.get_by_user_and_type(u.id, 'Férias')
                dias_usados = sum(a.quantidade_dias + a.dias_abono for a in ausencias if a.status == 'Aprovado')
                saldo_teorico = (anos_completos * 30) - dias_usados
                
                if saldo_teorico > 0:
                    ciclos_pendentes = saldo_teorico / 30.0
                    ciclo_critico = anos_completos - int(ciclos_pendentes) + 1
                    anos_para_somar = ciclo_critico + 1
                    data_limite = u.data_admissao + timedelta(days=365 * anos_para_somar)
                    dias_vencimento = (data_limite - hoje).days
                    
                    if dias_vencimento < 0:
                        alertas_vencimento.append({'user': u, 'status': 'Vencidas', 'msg': 'Risco alto de multa/dobro!'})
                    elif dias_vencimento <= 90:
                        alertas_vencimento.append({'user': u, 'status': 'A Vencer', 'msg': f'Vence em {dias_vencimento} dias.'})

    todas_solicitacoes = ausencia_repo.get_todas()
    return render_template('ponto/gestao_ausencias.html', solicitacoes=todas_solicitacoes, alertas=alertas_vencimento)

@ponto_bp.route('/admin/controle-escala', methods=['GET'])
@login_required
def controle_escala():
    if current_user.role != 'Master' and str(current_user.username) != '50097952800': 
        return redirect(url_for('main.dashboard'))
        
    data_str = request.args.get('data_ref')
    if data_str: data_ref = datetime.strptime(data_str, '%Y-%m-%d').date()
    else: data_ref = get_brasil_time().date()
    
    user_repo = UserRepository()
    ausencia_repo = SolicitacaoAusenciaRepository()
    reg_repo = PontoRegistroRepository()
    
    usuarios = user_repo.get_gestores() 
    trabalhando, folga = [], []
    
    for u in usuarios:
        ausencia = ausencia_repo.get_aprovada_por_data(u.id, data_ref)
        
        escala_trabalho = True
        if u.escala == '5x2' and data_ref.weekday() >= 5: escala_trabalho = False
        elif u.escala == '12x36' and u.data_inicio_escala:
            if (data_ref - u.data_inicio_escala).days % 2 != 0: escala_trabalho = False
        
        pontos = reg_repo.get_by_user_and_date(u.id, data_ref)
        status_batida = f"{len(pontos)} marcações" if pontos else "Sem marcação"
        info = {'user': u, 'ausencia': ausencia, 'batidas': status_batida}
        
        if ausencia: 
            info['motivo'] = ausencia.tipo_ausencia; folga.append(info)
        elif not escala_trabalho: 
            info['motivo'] = 'Folga Escala'; folga.append(info)
        else: 
            trabalhando.append(info)
            
    return render_template('ponto/controle_escala.html', trabalhando=trabalhando, folga=folga, data_ref=data_ref)


from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, PontoAjuste, Recibo, Holerite, PreCadastro, Notificacao, PontoResumo, PontoRegistro, HistoricoSaida
from app.utils import get_brasil_time, has_permission
from datetime import timedelta
from sqlalchemy import func
import traceback

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@login_required
def dashboard():
    if current_user.is_first_access:
        return redirect(url_for('auth.primeiro_acesso'))
    
    if current_user.role == 'Terminal':
        return redirect(url_for('ponto.terminal_scanner'))

    # Dados Básicos (Todos Vêem)
    dados = {
        'hoje': get_brasil_time().strftime('%d/%m/%Y'),
        'doc_pendentes': 0
    }

    # Contagem de documentos não lidos pelo utilizador
    docs_h = Holerite.query.filter_by(user_id=current_user.id, visualizado=False).count()
    docs_r = Recibo.query.filter_by(user_id=current_user.id, visualizado=False).count()
    dados['doc_pendentes'] = docs_h + docs_r

    # Dados Administrativos (Apenas se tiver permissão ou for Master)
    admin_stats = {}
    
    if has_permission('USUARIOS'):
        # FILTRO: Não conta o Terminal como funcionário ativo
        admin_stats['total_users'] = User.query.filter(User.username != '12345678900', User.username != 'terminal').count()
        admin_stats['pendentes_cadastro'] = PreCadastro.query.count()

    if has_permission('PONTO'):
        admin_stats['ajustes_pendentes'] = PontoAjuste.query.filter_by(status='Pendente').count()

    return render_template('main/dashboard.html', dados=dados, admin=admin_stats)

# --- ROTAS AJAX DO SININHO DE NOTIFICAÇÕES ---
@main_bp.route('/api/notificacoes', methods=['GET'])
@login_required
def buscar_notificacoes():
    """Busca as últimas 10 notificações do utilizador para mostrar no sino."""
    notifs = Notificacao.query.filter_by(user_id=current_user.id).order_by(Notificacao.data_criacao.desc()).limit(10).all()
    nao_lidas = Notificacao.query.filter_by(user_id=current_user.id, lida=False).count()
    
    lista = []
    for n in notifs:
        lista.append({
            'id': n.id,
            'mensagem': n.mensagem,
            'link': n.link,
            'lida': n.lida,
            'tempo': n.data_criacao.strftime('%d/%m %H:%M')
        })
        
    return jsonify({'nao_lidas': nao_lidas, 'itens': lista})

@main_bp.route('/api/notificacoes/ler/<int:notif_id>', methods=['POST'])
@login_required
def ler_notificacao(notif_id):
    """Marca uma notificação como lida quando o utilizador clica nela."""
    notif = Notificacao.query.filter_by(id=notif_id, user_id=current_user.id).first()
    if notif:
        notif.lida = True
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@main_bp.route('/api/notificacoes/ler_todas', methods=['POST'])
@login_required
def ler_todas_notificacoes():
    """Limpa o contador do sino de uma só vez."""
    Notificacao.query.filter_by(user_id=current_user.id, lida=False).update({'lida': True})
    db.session.commit()
    return jsonify({'success': True})

# --- API DE INTELIGÊNCIA EXECUTIVA (CHART.JS) BLINDADA ---
@main_bp.route('/api/analytics', methods=['GET'])
@login_required
def api_analytics():
    """Fornece dados em tempo real para os 5 gráficos do Dashboard Master."""
    is_master = current_user.role == 'Master' or current_user.username == '50097952800'
    
    if not is_master:
        return jsonify({'error': 'Acesso negado'}), 403
        
    try:
        hoje = get_brasil_time().date()
        sete_dias_atras = hoje - timedelta(days=6)
        primeiro_dia_mes = hoje.replace(day=1)

        # 1. Raio-X da Operação Hoje (Donut)
        ponto_hoje = db.session.query(PontoResumo.status_dia, func.count(PontoResumo.id)).filter(PontoResumo.data_referencia == hoje).group_by(PontoResumo.status_dia).all()
        raio_x = {status: qtd for status, qtd in ponto_hoje}
        
        # 2. Termômetro de Risco (Linhas: Faltas vs Horas Extras nos últimos 7 dias)
        dias_labels = [(sete_dias_atras + timedelta(days=i)).strftime('%d/%m') for i in range(7)]
        risco_faltas = []
        risco_extras = []
        for i in range(7):
            dia_alvo = sete_dias_atras + timedelta(days=i)
            faltas = PontoResumo.query.filter(PontoResumo.data_referencia == dia_alvo, PontoResumo.status_dia == 'Falta').count()
            extras_min = db.session.query(func.sum(PontoResumo.minutos_saldo)).filter(PontoResumo.data_referencia == dia_alvo, PontoResumo.minutos_saldo > 0).scalar() or 0
            risco_faltas.append(faltas)
            risco_extras.append(round(extras_min / 60, 1))

        # 3. Termômetro de Custos (Barras: EPI por Depto no mês atual)
        saidas = db.session.query(User.departamento, func.sum(HistoricoSaida.quantidade))\
            .join(User, User.real_name == HistoricoSaida.colaborador)\
            .filter(HistoricoSaida.data_entrega >= primeiro_dia_mes)\
            .group_by(User.departamento).all()
        custos_labels = [s[0] or 'Geral' for s in saidas]
        custos_data = [s[1] for s in saidas]

        # 4. Escudo Legal (Velocímetro: % Documentos Lidos no Mês)
        tot_holerites = Holerite.query.filter(Holerite.enviado_em >= primeiro_dia_mes).count()
        lid_holerites = Holerite.query.filter(Holerite.enviado_em >= primeiro_dia_mes, Holerite.visualizado == True).count()
        tot_recibos = Recibo.query.filter(Recibo.created_at >= primeiro_dia_mes).count()
        lid_recibos = Recibo.query.filter(Recibo.created_at >= primeiro_dia_mes, Recibo.visualizado == True).count()
        
        total_docs = tot_holerites + tot_recibos
        lidos_docs = lid_holerites + lid_recibos
        taxa_assinatura = round((lidos_docs / total_docs * 100) if total_docs > 0 else 100, 1)

        # 5. Radar de Pontualidade (Barras Empilhadas: Atrasos no Mês)
        pontual = PontoResumo.query.filter(PontoResumo.data_referencia >= primeiro_dia_mes, PontoResumo.minutos_saldo >= 0).count()
        atraso_leve = PontoResumo.query.filter(PontoResumo.data_referencia >= primeiro_dia_mes, PontoResumo.minutos_saldo < 0, PontoResumo.minutos_saldo >= -15).count()
        atraso_critico = PontoResumo.query.filter(PontoResumo.data_referencia >= primeiro_dia_mes, PontoResumo.minutos_saldo < -15).count()

        return jsonify({
            'raio_x': raio_x,
            'risco': {'labels': dias_labels, 'faltas': risco_faltas, 'extras': risco_extras},
            'custos': {'labels': custos_labels, 'data': custos_data},
            'escudo': taxa_assinatura,
            'pontualidade': [pontual, atraso_leve, atraso_critico]
        })
        
    except Exception as e:
        # Imprime o erro no console do backend (GCP Logs) para diagnóstico profundo
        print("====== ERRO NA API DE ANALYTICS ======")
        traceback.print_exc()
        print("======================================")
        # Devolve o erro formatado para o Frontend poder mostrar na tela
        return jsonify({'error': str(e)}), 500


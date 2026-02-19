from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, PontoAjuste, Recibo, Holerite, PreCadastro, Notificacao
from app.utils import get_brasil_time, has_permission

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

# --- NOVIDADE: ROTAS AJAX DO SININHO DE NOTIFICAÇÕES ---
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


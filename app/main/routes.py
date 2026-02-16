from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models import User, PontoAjuste, Recibo, Holerite, PreCadastro
from app.utils import get_brasil_time, has_permission

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@login_required
def dashboard():
    if current_user.is_first_access:
        return redirect(url_for('auth.primeiro_acesso'))
    
    # CORREÇÃO: Nome correto da rota do scanner
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
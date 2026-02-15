from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import PontoRegistro
from app.utils import get_brasil_time

main_bp = Blueprint('main', __name__, template_folder='templates')

@main_bp.route('/')
@login_required
def dashboard():
    hoje = get_brasil_time().date()
    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).count()
    status = "Não Iniciado"
    if pontos == 1: status = "Trabalhando"
    elif pontos == 2: status = "Almoço"
    elif pontos == 3: status = "Trabalhando (Tarde)"
    elif pontos >= 4: status = "Dia Finalizado"
    return render_template('main/dashboard.html', status_ponto=status)
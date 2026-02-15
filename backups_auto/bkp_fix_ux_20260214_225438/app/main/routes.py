from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import PontoRegistro, ItemEstoque, PontoResumo
from app.utils import get_brasil_time
from sqlalchemy import func, extract

main_bp = Blueprint('main', __name__, template_folder='templates')

@main_bp.route('/')
@login_required
def dashboard():
    hoje = get_brasil_time()
    hoje_date = hoje.date()
    
    # Lógica Padrão (Funcionário)
    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje_date).count()
    status = "Não Iniciado"
    if pontos == 1: status = "Trabalhando"
    elif pontos == 2: status = "Almoço"
    elif pontos == 3: status = "Trabalhando (Tarde)"
    elif pontos >= 4: status = "Dia Finalizado"

    # Lógica Master (Gráficos)
    dados_graficos = None
    
    if current_user.role == 'Master':
        # 1. Estoque Baixo (Top 5 itens críticos)
        estoque_critico = ItemEstoque.query.filter(
            ItemEstoque.quantidade <= ItemEstoque.estoque_minimo
        ).order_by(ItemEstoque.quantidade).limit(5).all()
        
        # 2. Resumo de Presença do Mês Atual
        resumos_mes = db_resumos_mes(hoje.year, hoje.month)
        
        dados_graficos = {
            'estoque_labels': [i.nome for i in estoque_critico],
            'estoque_data': [i.quantidade for i in estoque_critico],
            'ponto_status': resumos_mes
        }

    return render_template('main/dashboard.html', status_ponto=status, dados_graficos=dados_graficos)

def db_resumos_mes(ano, mes):
    # Agrega status do ponto (OK, Falta, Atraso, etc)
    stats = PontoResumo.query.with_entities(
        PontoResumo.status_dia, func.count(PontoResumo.id)
    ).filter(
        extract('year', PontoResumo.data_referencia) == ano,
        extract('month', PontoResumo.data_referencia) == mes
    ).group_by(PontoResumo.status_dia).all()
    
    # Formata para dicionário simples
    resultado = {'OK': 0, 'Falta': 0, 'Incompleto': 0, 'Hora Extra': 0, 'Débito': 0}
    for s, qtd in stats:
        if s in resultado:
            resultado[s] = qtd
        else:
            # Agrupa outros status eventuais
            resultado['Incompleto'] += qtd
            
    return resultado

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo
from app.utils import get_brasil_time, permission_required
from app.documentos.storage import salvar_no_storage, gerar_url_assinada
from app.documentos.ai_parser import extrair_dados_holerite
from pypdf import PdfReader, PdfWriter
import io

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

@documentos_bp.route('/meus-documentos')
@login_required
def meus_documentos():
    """Lista documentos vinculados ao funcionário logado."""
    holerites = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.enviado_em.desc()).all()
    recibos = Recibo.query.filter_by(user_id=current_user.id).order_by(Recibo.created_at.desc()).all()
    
    docs_formatados = []
    for h in holerites:
        docs_formatados.append({
            'id': h.id, 'tipo': 'Holerite', 'titulo': f'Holerite {h.mes_referencia}',
            'cor': 'blue', 'icone': 'fa-file-invoice-dollar', 'data': h.enviado_em,
            'visto': h.visualizado, 'rota': 'baixar_holerite'
        })
    for r in recibos:
        docs_formatados.append({
            'id': r.id, 'tipo': 'Recibo', 'titulo': 'Recibo de Benefícios',
            'cor': 'emerald', 'icone': 'fa-receipt', 'data': r.created_at,
            'visto': r.visualizado, 'rota': 'baixar_recibo'
        })
    return render_template('documentos/meus_documentos.html', docs=docs_formatados)

# Manter rotas existentes: admin_holerites, revisao_holerites, vincular_holerite, baixar_holerite, dashboard_documentos


from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo, AssinaturaDigital
from app.utils import get_brasil_time, permission_required, has_permission, limpar_nome
from app.documentos.storage import salvar_no_storage, gerar_url_assinada
from app.documentos.ai_parser import extrair_dados_holerite
from app.documentos.utils import gerar_pdf_recibo, gerar_pdf_espelho_mensal, gerar_certificado_entrega
from pypdf import PdfReader, PdfWriter
from thefuzz import process
import io

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

# --- PAINÉIS ---

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
    """Painel principal administrativo."""
    holerites_db = Holerite.query.filter(Holerite.status != 'Revisao').order_by(Holerite.enviado_em.desc()).limit(30).all()
    recibos_db = Recibo.query.order_by(Recibo.created_at.desc()).limit(20).all()
    total_revisao = Holerite.query.filter_by(status='Revisao').count()
    
    historico = []
    for h in holerites_db:
        tipo = "Espelho de Ponto" if h.conteudo_pdf else "Holerite"
        historico.append({
            'id': h.id, 'tipo': tipo, 'cor': 'purple' if h.conteudo_pdf else 'blue',
            'usuario': h.user.real_name if h.user else "Identificação Falhou",
            'info': h.mes_referencia, 'data': h.enviado_em,
            'visualizado': h.visualizado, 'rota': 'baixar_holerite'
        })
    for r in recibos_db:
        historico.append({
            'id': r.id, 'tipo': 'Recibo', 'cor': 'emerald',
            'usuario': r.user.real_name, 'info': f"R$ {r.valor:,.2f}",
            'data': r.created_at, 'visualizado': r.visualizado, 'rota': 'baixar_recibo'
        })
    historico.sort(key=lambda x: x['data'] if x['data'] else get_brasil_time(), reverse=True)
    return render_template('documentos/dashboard.html', historico=historico, pendentes_revisao=total_revisao)

@documentos_bp.route('/admin/revisao')
@login_required
@permission_required('DOCUMENTOS')
def revisao_holerites():
    pendentes = Holerite.query.filter_by(status='Revisao').all()
    funcionarios = User.query.filter(User.role != 'Terminal').order_by(User.real_name).all()
    return render_template('documentos/revisao.html', pendentes=pendentes, funcionarios=funcionarios)

@documentos_bp.route('/admin/revisao/limpar', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def limpar_revisoes():
    """Limpa todos os registros de teste na aba de revisão."""
    try:
        Holerite.query.filter_by(status='Revisao').delete()
        db.session.commit()
        flash("Histórico de revisão limpo!", "success")
    except:
        db.session.rollback()
    return redirect(url_for('documentos.revisao_holerites'))

@documentos_bp.route('/admin/auditoria')
@login_required
@permission_required('AUDITORIA')
def revisao_auditoria():
    usuarios = User.query.filter(User.role != 'Terminal').order_by(User.real_name).all()
    auditores = []
    for user in usuarios:
        assinaturas = AssinaturaDigital.query.filter_by(user_id=user.id).order_by(AssinaturaDigital.data_assinatura.desc()).all()
        auditores.append({'user': user, 'total': len(assinaturas), 'assinaturas': assinaturas})
    return render_template('documentos/auditoria.html', auditores=auditores)

# --- DOWNLOADS ---

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    # Master ou usuários com permissão DOCUMENTOS podem baixar qualquer arquivo
    if not has_permission('DOCUMENTOS') and doc.user_id != current_user.id:
        flash("Acesso não autorizado.", "error")
        return redirect(url_for('main.dashboard'))
    
    if doc.conteudo_pdf:
        return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"ponto_{doc.mes_referencia}.pdf")
    if doc.url_arquivo:
        link = gerar_url_assinada(doc.url_arquivo)
        if link: return redirect(link)
    flash("Ocorreu um erro ao gerar o link. Verifique as permissões de IAM.", "error")
    return redirect(url_for('documentos.dashboard_documentos'))

# (Mantenha as outras rotas: admin_holerites, meus_documentos, vincular_holerite como na última versão)


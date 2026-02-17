from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo
from app.utils import get_brasil_time, permission_required
from app.documentos.storage import salvar_no_storage, gerar_url_assinada
from app.documentos.ai_parser import extrair_dados_holerite
from pypdf import PdfReader, PdfWriter
import io

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
    """Painel administrativo de documentos (Dashboard)."""
    # Busca os últimos holerites para exibir no histórico
    historico_db = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(50).all()
    
    historico_view = []
    for h in historico_db:
        # A chave 'enviado_em' deve ser a mesma esperada no template
        historico_view.append({
            'id': h.id,
            'tipo': 'Holerite',
            'cor': 'blue',
            'usuario': h.user.real_name if h.user else "Aguardando Revisão",
            'info': h.mes_referencia,
            'enviado_em': h.enviado_em,
            'visualizado': h.visualizado,
            'rota': 'baixar_holerite'
        })
    
    return render_template('documentos/dashboard.html', historico=historico_view)

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

@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_holerites():
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        if not file:
            flash("Selecione um arquivo PDF.", "error")
            return redirect(request.url)
        try:
            reader = PdfReader(file)
            sucesso, revisao = 0, 0
            usuarios_sistema = {u.real_name.upper().strip(): u.id for u in User.query.all()}
            for page in reader.pages:
                writer = PdfWriter(); writer.add_page(page); buffer = io.BytesIO(); writer.write(buffer)
                pdf_bytes = buffer.getvalue()
                dados = extrair_dados_holerite(pdf_bytes)
                nome_doc = dados.get('nome', '').upper().strip() if dados else ""
                mes_ref = dados.get('mes_referencia', '2026-02') if dados else "2026-02"
                caminho_blob = salvar_no_storage(pdf_bytes, mes_ref)
                if not caminho_blob: continue
                user_id = usuarios_sistema.get(nome_doc)
                novo_h = Holerite(user_id=user_id, mes_referencia=mes_ref, url_arquivo=caminho_blob,
                                 status='Enviado' if user_id else 'Revisao', enviado_em=get_brasil_time())
                db.session.add(novo_h)
                if user_id: sucesso += 1
                else: revisao += 1
            db.session.commit()
            flash(f"Processado: {sucesso} identificados e {revisao} para revisão.", "success")
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e:
            db.session.rollback(); flash(f"Erro: {e}", "error")
    return render_template('documentos/admin_upload_holerite.html')

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if current_user.role != 'Master' and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
    if doc.url_arquivo:
        link = gerar_url_assinada(doc.url_arquivo)
        if link: return redirect(link)
    flash("Arquivo indisponível.", "error")
    return redirect(url_for('documentos.dashboard_documentos'))

@documentos_bp.route('/baixar/recibo/<int:id>', methods=['POST'])
@login_required
def baixar_recibo(id):
    doc = Recibo.query.get_or_404(id)
    if current_user.role != 'Master' and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"recibo_{id}.pdf")


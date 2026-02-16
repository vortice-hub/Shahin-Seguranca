from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite
from app.utils import get_brasil_time, permission_required
from app.documentos.storage import salvar_no_storage, gerar_url_assinada
from app.documentos.ai_parser import extrair_dados_holerite
from pypdf import PdfReader, PdfWriter
import io

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

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
            # Mapeamento de usuários ativos para busca rápida
            usuarios_sistema = {u.real_name.upper().strip(): u.id for u in User.query.all()}

            for page in reader.pages:
                # 1. Isola a página em bytes
                writer = PdfWriter()
                writer.add_page(page)
                buffer = io.BytesIO()
                writer.write(buffer)
                pdf_bytes = buffer.getvalue()

                # 2. IA extrai os dados
                dados = extrair_dados_holerite(pdf_bytes)
                nome_doc = dados.get('nome', '').upper().strip() if dados else ""
                mes_ref = dados.get('mes_referencia', '2026-02') if dados else "2026-02"

                # 3. Salva SEMPRE no Storage (Bucket privado)
                caminho_blob = salvar_no_storage(pdf_bytes, mes_ref)

                if not caminho_blob: continue

                # 4. Tenta vincular ao usuário
                user_id = usuarios_sistema.get(nome_doc)
                status = 'Enviado' if user_id else 'Revisao'

                novo_h = Holerite(
                    user_id=user_id,
                    mes_referencia=mes_ref,
                    url_arquivo=caminho_blob, # Aqui guardamos o caminho do blob
                    status=status,
                    enviado_em=get_brasil_time()
                )
                db.session.add(novo_h)
                
                if user_id: sucesso += 1
                else: revisao += 1

            db.session.commit()
            flash(f"Processado: {sucesso} identificados e {revisao} para revisão manual.", "success")
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro no processamento: {e}", "error")

    return render_template('documentos/admin_upload_holerite.html')

@documentos_bp.route('/admin/revisao')
@login_required
@permission_required('DOCUMENTOS')
def revisao_holerites():
    pendentes = Holerite.query.filter_by(status='Revisao').all()
    funcionarios = User.query.filter(User.role != 'Terminal').order_by(User.real_name).all()
    return render_template('documentos/revisao.html', pendentes=pendentes, funcionarios=funcionarios)

@documentos_bp.route('/admin/revisao/vincular', methods=['POST'])
@login_required
def vincular_holerite():
    h_id = request.form.get('holerite_id')
    u_id = request.form.get('user_id')
    h = Holerite.query.get(h_id)
    if h and u_id:
        h.user_id = u_id
        h.status = 'Enviado'
        db.session.commit()
        flash("Funcionário vinculado com sucesso!", "success")
    return redirect(url_for('documentos.revisao_holerites'))

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    # Segurança: Apenas Master (50097952800) ou o dono do documento
    if current_user.username != '50097952800' and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
    
    if doc.url_arquivo:
        # Gera a Signed URL (expira em 15 min)
        link = gerar_url_assinada(doc.url_arquivo)
        if link:
            return redirect(link)
    
    flash("Arquivo não disponível.", "error")
    return redirect(url_for('documentos.dashboard_documentos'))

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
    historico = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(50).all()
    return render_template('documentos/dashboard.html', historico=historico)
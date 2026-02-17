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

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
    holerites_db = Holerite.query.filter(Holerite.status != 'Revisao').order_by(Holerite.enviado_em.desc()).limit(30).all()
    recibos_db = Recibo.query.order_by(Recibo.created_at.desc()).limit(20).all()
    total_revisao = Holerite.query.filter_by(status='Revisao').count()
    
    historico_unificado = []
    for h in holerites_db:
        tipo_label = "Espelho de Ponto" if h.conteudo_pdf else "Holerite"
        historico_unificado.append({
            'id': h.id, 'tipo': tipo_label, 'cor': 'purple' if h.conteudo_pdf else 'blue',
            'usuario': h.user.real_name if h.user else "N/A",
            'info': h.mes_referencia, 'data': h.enviado_em,
            'visualizado': h.visualizado, 'rota': 'baixar_holerite'
        })
    for r in recibos_db:
        historico_unificado.append({
            'id': r.id, 'tipo': 'Recibo', 'cor': 'emerald',
            'usuario': r.user.real_name, 'info': f"R$ {r.valor:,.2f}",
            'data': r.created_at, 'visualizado': r.visualizado, 'rota': 'baixar_recibo'
        })
    historico_unificado.sort(key=lambda x: x['data'], reverse=True)
    return render_template('documentos/dashboard.html', historico=historico_unificado, pendentes_revisao=total_revisao)

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
            usuarios_db = User.query.filter(User.role != 'Terminal').all()
            usuarios_map = {limpar_nome(u.real_name): u.id for u in usuarios_db}
            nomes_disponiveis = list(usuarios_map.keys())

            for page in reader.pages:
                writer = PdfWriter(); writer.add_page(page); buffer = io.BytesIO(); writer.write(buffer)
                pdf_bytes = buffer.getvalue()
                dados = extrair_dados_holerite(pdf_bytes)
                
                # Se a IA falhar (403), os dados virão None
                nome_pdf = limpar_nome(dados.get('nome', '')) if dados else ""
                mes_ref = dados.get('mes_referencia', '2026-02') if dados else "2026-02"

                caminho_blob = salvar_no_storage(pdf_bytes, mes_ref)
                if not caminho_blob: continue

                user_id = None
                if nome_pdf:
                    match = process.extractOne(nome_pdf, nomes_disponiveis, score_cutoff=85)
                    if match: user_id = usuarios_map.get(match[0])

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
    try:
        Holerite.query.filter_by(status='Revisao').delete()
        db.session.commit()
        flash("Revisões limpas!", "success")
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

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    # Master ou Admin podem baixar QUALQUER arquivo, inclusive os sem dono (revisão)
    if not has_permission('DOCUMENTOS') and doc.user_id != current_user.id:
        flash("Não autorizado.", "error")
        return redirect(url_for('main.dashboard'))
    
    if doc.conteudo_pdf:
        return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"ponto_{doc.mes_referencia}.pdf")
    if doc.url_arquivo:
        link = gerar_url_assinada(doc.url_arquivo)
        if link: return redirect(link)
    flash("Link expirado ou indisponível.", "error")
    return redirect(url_for('documentos.dashboard_documentos'))

@documentos_bp.route('/admin/revisao/vincular', methods=['POST'])
@login_required
def vincular_holerite():
    h = Holerite.query.get(request.form.get('holerite_id'))
    u_id = request.form.get('user_id')
    if h and u_id:
        h.user_id = u_id; h.status = 'Enviado'; db.session.commit()
        flash("Vinculado!", "success")
    return redirect(url_for('documentos.revisao_holerites'))


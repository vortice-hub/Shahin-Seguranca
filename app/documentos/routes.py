from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo, AssinaturaDigital
from app.utils import get_brasil_time, permission_required, has_permission, limpar_nome
from app.documentos.storage import salvar_no_storage, baixar_bytes_storage
from app.documentos.ai_parser import extrair_dados_holerite
from app.documentos.utils import gerar_pdf_recibo, gerar_pdf_espelho_mensal, gerar_certificado_entrega
from pypdf import PdfReader, PdfWriter
from thefuzz import process, fuzz
import io

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
    """Painel administrativo."""
    holerites_db = Holerite.query.filter(Holerite.status != 'Revisao').order_by(Holerite.enviado_em.desc()).limit(30).all()
    recibos_db = Recibo.query.order_by(Recibo.created_at.desc()).limit(20).all()
    total_revisao = Holerite.query.filter_by(status='Revisao').count()
    
    historico = []
    for h in holerites_db:
        tipo = "Espelho de Ponto" if h.conteudo_pdf else "Holerite"
        historico.append({
            'id': h.id, 'tipo': tipo, 'cor': 'purple' if h.conteudo_pdf else 'blue',
            'usuario': h.user.real_name if h.user else "N/A",
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

@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_holerites():
    """Upload via Python Puro (Sem IA)."""
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        if not file: return redirect(request.url)
        try:
            reader = PdfReader(file)
            sucesso, revisao = 0, 0
            
            # Prepara lista de nomes normalizados para a busca
            usuarios_db = User.query.filter(User.role != 'Terminal').all()
            # Mapa: { "NOME LIMPO": ID }
            usuarios_map = {limpar_nome(u.real_name): u.id for u in usuarios_db}
            lista_nomes_banco = list(usuarios_map.keys())

            for page in reader.pages:
                writer = PdfWriter(); writer.add_page(page); buffer = io.BytesIO(); writer.write(buffer)
                pdf_bytes = buffer.getvalue()
                
                # --- EXTRAÇÃO LOCAL ---
                dados = extrair_dados_holerite(pdf_bytes, lista_nomes_banco)
                
                nome_identificado = dados.get('nome', '')
                mes_ref = dados.get('mes_referencia', '2026-02')

                caminho_blob = salvar_no_storage(pdf_bytes, mes_ref)
                if not caminho_blob: continue

                user_id = None
                if nome_identificado and nome_identificado in usuarios_map:
                    user_id = usuarios_map[nome_identificado]

                novo_h = Holerite(user_id=user_id, mes_referencia=mes_ref, url_arquivo=caminho_blob,
                                 status='Enviado' if user_id else 'Revisao', enviado_em=get_brasil_time())
                db.session.add(novo_h)
                
                if user_id: sucesso += 1
                else: revisao += 1

            db.session.commit()
            flash(f"Upload: {sucesso} identificados, {revisao} para revisão.", "success")
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e:
            db.session.rollback(); flash(f"Erro: {e}", "error")
    return render_template('documentos/admin_upload_holerite.html')

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if not has_permission('DOCUMENTOS') and doc.user_id != current_user.id:
        flash("Acesso negado.", "error")
        return redirect(url_for('main.dashboard'))
    
    if doc.conteudo_pdf:
        return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"ponto.pdf")
    
    if doc.url_arquivo:
        # Download Direto do Storage (Bypass Link Assinado)
        arquivo_bytes = baixar_bytes_storage(doc.url_arquivo)
        if arquivo_bytes:
            return send_file(io.BytesIO(arquivo_bytes), mimetype='application/pdf', as_attachment=True, download_name=f"holerite.pdf")
            
    flash("Arquivo não encontrado.", "error")
    return redirect(url_for('documentos.dashboard_documentos'))

@documentos_bp.route('/baixar/recibo/<int:id>', methods=['POST'])
@login_required
def baixar_recibo(id):
    doc = Recibo.query.get_or_404(id)
    if not has_permission('DOCUMENTOS') and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"recibo_{id}.pdf")

@documentos_bp.route('/meus-documentos')
@login_required
def meus_documentos():
    holerites = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.enviado_em.desc()).all()
    recibos = Recibo.query.filter_by(user_id=current_user.id).order_by(Recibo.created_at.desc()).all()
    docs = []
    for h in holerites:
        e_ponto = True if h.conteudo_pdf else False
        docs.append({'id': h.id, 'tipo': 'Espelho' if e_ponto else 'Holerite', 'titulo': f"{'Ponto' if e_ponto else 'Holerite'} - {h.mes_referencia}", 'cor': 'purple' if e_ponto else 'blue', 'icone': 'fa-calendar' if e_ponto else 'fa-file', 'data': h.enviado_em, 'visto': h.visualizado, 'rota': 'baixar_holerite'})
    for r in recibos:
        docs.append({'id': r.id, 'tipo': 'Recibo', 'titulo': 'Recibo', 'cor': 'emerald', 'icone': 'fa-receipt', 'data': r.created_at, 'visto': r.visualizado, 'rota': 'baixar_recibo'})
    return render_template('documentos/meus_documentos.html', docs=docs)

# (Rotas de revisão, auditoria e novos recibos mantidas)
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
    try: Holerite.query.filter_by(status='Revisao').delete(); db.session.commit()
    except: db.session.rollback()
    return redirect(url_for('documentos.revisao_holerites'))

@documentos_bp.route('/admin/revisao/vincular', methods=['POST'])
@login_required
def vincular_holerite():
    h = Holerite.query.get(request.form.get('holerite_id'))
    u_id = request.form.get('user_id')
    if h and u_id: h.user_id = u_id; h.status = 'Enviado'; db.session.commit()
    return redirect(url_for('documentos.revisao_holerites'))

@documentos_bp.route('/admin/auditoria')
@login_required
@permission_required('AUDITORIA')
def revisao_auditoria():
    usuarios = User.query.filter(User.role != 'Terminal').order_by(User.real_name).all()
    auditores = []
    for u in usuarios:
        assinaturas = AssinaturaDigital.query.filter_by(user_id=u.id).order_by(AssinaturaDigital.data_assinatura.desc()).all()
        l = [{'id':a.id, 'tipo':a.tipo_documento, 'data':a.data_assinatura, 'ip':a.ip_address} for a in assinaturas]
        auditores.append({'user': u, 'total': len(assinaturas), 'assinaturas': l})
    return render_template('documentos/auditoria.html', auditores=auditores)

@documentos_bp.route('/admin/recibo/novo', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def novo_recibo():
    if request.method == 'POST':
        u = User.query.get(request.form.get('user_id'))
        r = Recibo(user_id=u.id, valor=float(request.form.get('valor', 0)), data_pagamento=get_brasil_time().date())
        r.conteudo_pdf = gerar_pdf_recibo(r, u)
        db.session.add(r); db.session.commit()
        return redirect(url_for('documentos.dashboard_documentos'))
    users = User.query.filter(User.role!='Terminal').all()
    return render_template('documentos/novo_recibo.html', users=users, hoje=get_brasil_time().strftime('%Y-%m-%d'))

@documentos_bp.route('/admin/disparar-espelhos', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def disparar_espelhos():
    mes = request.form.get('mes_ref')
    users = User.query.filter(User.role!='Terminal', User.username!='12345678900').all()
    for u in users:
        pdf = gerar_pdf_espelho_mensal(u, mes)
        db.session.add(Holerite(user_id=u.id, mes_referencia=mes, conteudo_pdf=pdf, status='Enviado', enviado_em=get_brasil_time()))
    db.session.commit()
    return redirect(url_for('documentos.dashboard_documentos'))

@documentos_bp.route('/api/user-info/<int:id>')
@login_required
def get_user_info_api(id):
    user = User.query.get_or_404(id)
    return jsonify({'razao_social': user.razao_social_empregadora, 'cnpj': user.cnpj_empregador})


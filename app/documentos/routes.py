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

# --- PAINÉIS DE VISUALIZAÇÃO ---

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
    """Painel administrativo unificado."""
    holerites_db = Holerite.query.filter(Holerite.status != 'Revisao').order_by(Holerite.enviado_em.desc()).limit(30).all()
    recibos_db = Recibo.query.order_by(Recibo.created_at.desc()).limit(20).all()
    total_revisao = Holerite.query.filter_by(status='Revisao').count()
    
    historico = []
    for h in holerites_db:
        tipo_label = "Espelho de Ponto" if h.conteudo_pdf else "Holerite"
        historico.append({
            'id': h.id, 'tipo': tipo_label, 'cor': 'purple' if h.conteudo_pdf else 'blue',
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

@documentos_bp.route('/meus-documentos')
@login_required
def meus_documentos():
    """Área do colaborador."""
    holerites = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.enviado_em.desc()).all()
    recibos = Recibo.query.filter_by(user_id=current_user.id).order_by(Recibo.created_at.desc()).all()
    docs_formatados = []
    for h in holerites:
        e_ponto = True if h.conteudo_pdf else False
        docs_formatados.append({
            'id': h.id, 'tipo': 'Espelho de Ponto' if e_ponto else 'Holerite', 
            'titulo': f"{'Ponto' if e_ponto else 'Holerite'} - {h.mes_referencia}",
            'cor': 'purple' if e_ponto else 'blue', 'icone': 'fa-calendar-check' if e_ponto else 'fa-file-invoice-dollar', 
            'data': h.enviado_em, 'visto': h.visualizado, 'rota': 'baixar_holerite'
        })
    for r in recibos:
        docs_formatados.append({
            'id': r.id, 'tipo': 'Recibo', 'titulo': 'Recibo de Benefícios',
            'cor': 'emerald', 'icone': 'fa-receipt', 'data': r.created_at,
            'visto': r.visualizado, 'rota': 'baixar_recibo'
        })
    return render_template('documentos/meus_documentos.html', docs=docs_formatados)

# --- PROCESSAMENTO E DISPAROS ---

@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_holerites():
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        if not file: return redirect(request.url)
        try:
            reader = PdfReader(file)
            usuarios_db = User.query.filter(User.role != 'Terminal').all()
            usuarios_map = {limpar_nome(u.real_name): u.id for u in usuarios_db}
            nomes_disponiveis = list(usuarios_map.keys())

            for page in reader.pages:
                writer = PdfWriter(); writer.add_page(page); buffer = io.BytesIO(); writer.write(buffer)
                pdf_bytes = buffer.getvalue()
                dados = extrair_dados_holerite(pdf_bytes)
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
            db.session.commit()
            flash("Upload processado!", "success")
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e:
            db.session.rollback(); flash(f"Erro: {e}", "error")
    return render_template('documentos/admin_upload_holerite.html')

@documentos_bp.route('/admin/disparar-espelhos', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def disparar_espelhos():
    mes_ref = request.form.get('mes_ref')
    usuarios = User.query.filter(User.role != 'Terminal', User.username != '12345678900').all()
    for u in usuarios:
        pdf_ponto = gerar_pdf_espelho_mensal(u, mes_ref)
        novo_h = Holerite(user_id=u.id, mes_referencia=mes_ref, conteudo_pdf=pdf_ponto,
                         status='Enviado', enviado_em=get_brasil_time())
        db.session.add(novo_h)
    db.session.commit()
    flash("Espelhos disparados!", "success")
    return redirect(url_for('documentos.dashboard_documentos'))

@documentos_bp.route('/admin/recibo/novo', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def novo_recibo():
    if request.method == 'POST':
        user = User.query.get_or_404(request.form.get('user_id'))
        novo_r = Recibo(
            user_id=user.id, valor=float(request.form.get('valor', 0)),
            data_pagamento=get_brasil_time().strptime(request.form.get('data_pagamento'), '%Y-%m-%d').date(),
            tipo_vale_alimentacao='va' in request.form, tipo_vale_transporte='vt' in request.form,
            tipo_assiduidade='assiduidade' in request.form, tipo_cesta_basica='cesta' in request.form,
            forma_pagamento=request.form.get('forma_pagamento')
        )
        novo_r.conteudo_pdf = gerar_pdf_recibo(novo_r, user)
        db.session.add(novo_r); db.session.commit()
        flash("Recibo gerado!", "success")
        return redirect(url_for('documentos.dashboard_documentos'))
    users = User.query.filter(User.role != 'Terminal').order_by(User.real_name).all()
    return render_template('documentos/novo_recibo.html', users=users, hoje=get_brasil_time().strftime('%Y-%m-%d'))

# --- REVISÃO E AUDITORIA ---

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
        flash("Revisões apagadas!", "success")
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
        lista_formatada = []
        for a in assinaturas:
            ref = "Doc ID: " + str(a.documento_id)
            if a.tipo_documento == 'Holerite':
                h = Holerite.query.get(a.documento_id)
                if h: ref = h.mes_referencia
            lista_formatada.append({'id': a.id, 'tipo': a.tipo_documento, 'referencia': ref, 'data': a.data_assinatura, 'ip': a.ip_address})
        auditores.append({'user': user, 'total': len(assinaturas), 'assinaturas': lista_formatada})
    return render_template('documentos/auditoria.html', auditores=auditores)

# --- DOWNLOADS ---

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if not has_permission('DOCUMENTOS') and doc.user_id != current_user.id:
        flash("Não autorizado.", "error")
        return redirect(url_for('main.dashboard'))
    if doc.conteudo_pdf:
        return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"ponto_{doc.mes_referencia}.pdf")
    if doc.url_arquivo:
        link = gerar_url_assinada(doc.url_arquivo)
        if link: return redirect(link)
    flash("Arquivo indisponível.", "error")
    return redirect(url_for('documentos.dashboard_documentos'))

@documentos_bp.route('/baixar/recibo/<int:id>', methods=['POST'])
@login_required
def baixar_recibo(id):
    doc = Recibo.query.get_or_404(id)
    if not has_permission('DOCUMENTOS') and doc.user_id != current_user.id:
        flash("Não autorizado.", "error")
        return redirect(url_for('main.dashboard'))
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"recibo_{id}.pdf")

@documentos_bp.route('/admin/revisao/vincular', methods=['POST'])
@login_required
def vincular_holerite():
    h = Holerite.query.get(request.form.get('holerite_id'))
    u_id = request.form.get('user_id')
    if h and u_id:
        h.user_id = u_id; h.status = 'Enviado'; db.session.commit()
    return redirect(url_for('documentos.revisao_holerites'))

@documentos_bp.route('/api/user-info/<int:id>')
@login_required
def get_user_info_api(id):
    user = User.query.get_or_404(id)
    return jsonify({
        'razao_social': user.razao_social_empregadora or "LA SHAHIN SERVIÇOS DE SEGURANÇA LTDA",
        'cnpj': user.cnpj_empregador or "50.537.235/0001-95"
    })


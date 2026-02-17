from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo, AssinaturaDigital
from app.utils import get_brasil_time, permission_required
from app.documentos.storage import salvar_no_storage, gerar_url_assinada
from app.documentos.ai_parser import extrair_dados_holerite
from app.documentos.utils import gerar_pdf_recibo, gerar_pdf_espelho_mensal, gerar_certificado_entrega
from pypdf import PdfReader, PdfWriter
import io

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

# --- DASHBOARDS E LISTAGENS ---

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
    """Painel administrativo central de documentos."""
    historico_db = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(50).all()
    historico_view = []
    for h in historico_db:
        historico_view.append({
            'id': h.id, 'tipo': 'Holerite', 'cor': 'blue',
            'usuario': h.user.real_name if h.user else "Aguardando Revisão",
            'info': h.mes_referencia, 'enviado_em': h.enviado_em,
            'visualizado': h.visualizado, 'rota': 'baixar_holerite'
        })
    return render_template('documentos/dashboard.html', historico=historico_view)

@documentos_bp.route('/meus-documentos')
@login_required
def meus_documentos():
    """Área do funcionário para visualizar seus próprios documentos."""
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

# --- GESTÃO DE RECIBOS ---

@documentos_bp.route('/admin/recibo/novo', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def novo_recibo():
    """Gera um novo recibo de benefícios em PDF e salva no banco."""
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        user = User.query.get_or_404(user_id)
        
        novo_r = Recibo(
            user_id=user.id,
            valor=float(request.form.get('valor', 0)),
            data_pagamento=get_brasil_time().strptime(request.form.get('data_pagamento'), '%Y-%m-%d').date(),
            tipo_vale_alimentacao='va' in request.form,
            tipo_vale_transporte='vt' in request.form,
            tipo_assiduidade='assiduidade' in request.form,
            tipo_cesta_basica='cesta' in request.form,
            forma_pagamento=request.form.get('forma_pagamento'),
            visualizado=False
        )
        
        # Gera o conteúdo binário do PDF usando a utilitária
        novo_r.conteudo_pdf = gerar_pdf_recibo(novo_r, user)
        db.session.add(novo_r)
        db.session.commit()
        
        flash(f"Recibo gerado com sucesso para {user.real_name}!", "success")
        return redirect(url_for('documentos.dashboard_documentos'))

    users = User.query.filter(User.role != 'Terminal').order_by(User.real_name).all()
    return render_template('documentos/novo_recibo.html', users=users, hoje=get_brasil_time().strftime('%Y-%m-%d'))

@documentos_bp.route('/api/user-info/<int:id>')
@login_required
def get_user_info_api(id):
    """API de suporte para preencher dados da empresa no template de recibo."""
    user = User.query.get_or_404(id)
    return jsonify({
        'razao_social': user.razao_social_empregadora or "LA SHAHIN SERVIÇOS DE SEGURANÇA LTDA",
        'cnpj': user.cnpj_empregador or "50.537.235/0001-95"
    })

# --- GESTÃO DE HOLERITES E ESPELHOS ---

@documentos_bp.route('/admin/disparar-espelhos', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def disparar_espelhos():
    """Gera e envia o espelho de ponto mensal para todos os funcionários ativos."""
    mes_ref = request.form.get('mes_ref') # Formato AAAA-MM
    usuarios = User.query.filter(User.role != 'Terminal', User.username != '12345678900').all()
    
    contador = 0
    for u in usuarios:
        pdf_ponto = gerar_pdf_espelho_mensal(u, mes_ref)
        # Salva como um "Holerite" do tipo espelho ou lógica similar
        novo_h = Holerite(
            user_id=u.id,
            mes_referencia=mes_ref,
            conteudo_pdf=pdf_ponto,
            status='Enviado',
            enviado_em=get_brasil_time()
        )
        db.session.add(novo_h)
        contador += 1
    
    db.session.commit()
    flash(f"Disparo concluído: {contador} espelhos de ponto enviados!", "success")
    return redirect(url_for('documentos.dashboard_documentos'))

@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_holerites():
    """Upload e processamento de holerites via IA."""
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        if not file:
            flash("Selecione um arquivo PDF.", "error")
            return redirect(request.url)
        try:
            reader = PdfReader(file)
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
            db.session.commit()
            flash("Processamento de holerites concluído.", "success")
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e:
            db.session.rollback(); flash(f"Erro no processamento: {e}", "error")
    return render_template('documentos/admin_upload_holerite.html')

# --- DOWNLOADS E AUDITORIA ---

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if current_user.role != 'Master' and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
    
    # Se houver conteúdo em bytes no banco (gerado pelo sistema como o espelho)
    if doc.conteudo_pdf:
        return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"ponto_{doc.mes_referencia}.pdf")
    
    # Se for arquivo do Cloud Storage (upload de holerite real)
    if doc.url_arquivo:
        link = gerar_url_assinada(doc.url_arquivo)
        if link: return redirect(link)
    
    flash("Arquivo não disponível para download.", "error")
    return redirect(url_for('documentos.dashboard_documentos'))

@documentos_bp.route('/baixar/recibo/<int:id>', methods=['POST'])
@login_required
def baixar_recibo(id):
    doc = Recibo.query.get_or_404(id)
    if current_user.role != 'Master' and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"recibo_{id}.pdf")


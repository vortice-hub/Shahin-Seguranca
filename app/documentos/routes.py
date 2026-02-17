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
    # Filtra apenas o que não está em revisão para o histórico principal
    holerites_db = Holerite.query.filter(Holerite.status != 'Revisao').order_by(Holerite.enviado_em.desc()).limit(30).all()
    recibos_db = Recibo.query.order_by(Recibo.created_at.desc()).limit(20).all()
    total_revisao = Holerite.query.filter_by(status='Revisao').count()
    
    historico = []
    # Processa Holerites e Espelhos
    for h in holerites_db:
        tipo_label = "Espelho de Ponto" if h.conteudo_pdf else "Holerite"
        historico.append({
            'id': h.id, 
            'tipo': tipo_label, 
            'cor': 'purple' if h.conteudo_pdf else 'blue',
            'usuario': h.user.real_name if h.user else "Identificação Falhou",
            'info': h.mes_referencia, 
            'data': h.enviado_em,
            'visualizado': h.visualizado, 
            'rota': 'baixar_holerite'
        })
        
    # Processa Recibos
    for r in recibos_db:
        historico.append({
            'id': r.id, 
            'tipo': 'Recibo', 
            'cor': 'emerald',
            'usuario': r.user.real_name, 
            'info': f"R$ {r.valor:,.2f}",
            'data': r.created_at, 
            'visualizado': r.visualizado, 
            'rota': 'baixar_recibo'
        })

    # Ordena o histórico consolidado por data
    historico.sort(key=lambda x: x['data'] if x['data'] else get_brasil_time(), reverse=True)
    
    return render_template('documentos/dashboard.html', 
                           historico=historico, 
                           pendentes_revisao=total_revisao)

@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_holerites():
    """Upload de holerites com Fuzzy Matching inteligente."""
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        if not file:
            return redirect(request.url)
        try:
            reader = PdfReader(file)
            sucesso, revisao = 0, 0
            
            # Busca TODOS os usuários (exceto terminal) para comparação de nomes
            usuarios_db = User.query.filter(User.role != 'Terminal').all()
            usuarios_map = {limpar_nome(u.real_name): u.id for u in usuarios_db}
            nomes_disponiveis = list(usuarios_map.keys())

            for page in reader.pages:
                writer = PdfWriter(); writer.add_page(page); buffer = io.BytesIO(); writer.write(buffer)
                pdf_bytes = buffer.getvalue()
                
                # IA extrai dados (Requer permissões Vertex AI Predictor no GCP)
                dados = extrair_dados_holerite(pdf_bytes)
                nome_pdf = limpar_nome(dados.get('nome', '')) if dados else ""
                mes_ref = dados.get('mes_referencia', '2026-02') if dados else "2026-02"

                caminho_blob = salvar_no_storage(pdf_bytes, mes_ref)
                if not caminho_blob: continue

                user_id = None
                if nome_pdf:
                    # Fuzzy Match com score 85 (Tolera pequenas variações de sobrenome)
                    match = process.extractOne(nome_pdf, nomes_disponiveis, score_cutoff=85)
                    if match:
                        user_id = usuarios_map.get(match[0])
                        print(f"DEBUG IA: Match encontrado '{match[0]}' para o PDF '{nome_pdf}'")

                novo_h = Holerite(user_id=user_id, mes_referencia=mes_ref, url_arquivo=caminho_blob,
                                 status='Enviado' if user_id else 'Revisao', enviado_em=get_brasil_time())
                db.session.add(novo_h)
                if user_id: sucesso += 1
                else: revisao += 1

            db.session.commit()
            flash(f"Processado: {sucesso} identificados e {revisao} para revisão manual.", "success")
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e:
            db.session.rollback(); flash(f"Erro no processamento: {e}", "error")
    return render_template('documentos/admin_upload_holerite.html')

# --- AUDITORIA E REVISÃO ---

@documentos_bp.route('/admin/revisao')
@login_required
@permission_required('DOCUMENTOS')
def revisao_holerites():
    """Exibe documentos que não foram identificados pela IA."""
    pendentes = Holerite.query.filter_by(status='Revisao').all()
    funcionarios = User.query.filter(User.role != 'Terminal').order_by(User.real_name).all()
    return render_template('documentos/revisao.html', pendentes=pendentes, funcionarios=funcionarios)

@documentos_bp.route('/admin/revisao/limpar', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def limpar_revisoes():
    """Apaga os registros da aba de revisão."""
    try:
        Holerite.query.filter_by(status='Revisao').delete()
        db.session.commit()
        flash("Revisões apagadas com sucesso!", "success")
    except:
        db.session.rollback()
    return redirect(url_for('documentos.revisao_holerites'))

@documentos_bp.route('/admin/auditoria')
@login_required
@permission_required('AUDITORIA')
def revisao_auditoria():
    """Dashboard de conformidade e assinaturas."""
    usuarios = User.query.filter(User.role != 'Terminal').order_by(User.real_name).all()
    auditores = []
    for user in usuarios:
        assinaturas_db = AssinaturaDigital.query.filter_by(user_id=user.id).order_by(AssinaturaDigital.data_assinatura.desc()).all()
        # Formata para o template auditoria.html
        lista = []
        for a in assinaturas_db:
            ref = f"ID: {a.documento_id}"
            if a.tipo_documento == 'Holerite':
                h = Holerite.query.get(a.documento_id)
                if h: ref = h.mes_referencia
            lista.append({'id': a.id, 'tipo': a.tipo_documento, 'referencia': ref, 'data': a.data_assinatura, 'ip': a.ip_address})
        auditores.append({'user': user, 'total': len(assinaturas_db), 'assinaturas': lista})
    return render_template('documentos/auditoria.html', auditores=auditores)

# --- DOWNLOADS ---

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    """Permite download de holerites (Storage) ou espelhos (Bytes)."""
    doc = Holerite.query.get_or_404(id)
    # Master ou Admin podem baixar QUALQUER arquivo (incluindo os da revisão)
    if not has_permission('DOCUMENTOS') and doc.user_id != current_user.id:
        flash("Acesso não autorizado.", "error")
        return redirect(url_for('main.dashboard'))
    
    if doc.conteudo_pdf:
        return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"ponto_{doc.mes_referencia}.pdf")
    if doc.url_arquivo:
        link = gerar_url_assinada(doc.url_arquivo)
        if link: return redirect(link)
    flash("Arquivo temporariamente indisponível. Verifique o IAM do Google Cloud.", "error")
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


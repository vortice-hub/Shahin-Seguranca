from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo, EspelhoPontoDoc, AssinaturaDigital
from app.utils import get_brasil_time, remove_accents, permission_required, get_client_ip, calcular_hash_arquivo
from app.documentos.utils import gerar_pdf_recibo, gerar_pdf_espelho_mensal, gerar_certificado_entrega
# IA e Processamento
from app.documentos.ai_parser import analisar_pagina_pdf_ia
from thefuzz import process
import io
from pypdf import PdfReader, PdfWriter
from datetime import datetime
import re

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

# --- CONFIGURAÇÕES FIXAS ---
MASTER_CPF = '50097952800'
TERMINAL_CPF = '12345678900'

# --- FUNÇÕES AUXILIARES ---

def formatar_mes_ref(mes_ano_str):
    if not mes_ano_str or '-' not in mes_ano_str: return mes_ano_str
    try:
        meses = {'01':'Janeiro','02':'Fevereiro','03':'Março','04':'Abril','05':'Maio','06':'Junho','07':'Julho','08':'Agosto','09':'Setembro','10':'Outubro','11':'Novembro','12':'Dezembro'}
        ano, mes = mes_ano_str.split('-')
        return f"{meses.get(mes, mes)} {ano}"
    except: return mes_ano_str

def resolve_ref_formatada(tipo, doc_id):
    try:
        if tipo == 'Holerite':
            d = Holerite.query.get(doc_id)
            return f"Folha de {formatar_mes_ref(d.mes_referencia)}" if d else "Removido"
        elif tipo == 'Recibo':
            d = Recibo.query.get(doc_id)
            return f"Recibo R$ {d.valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if d else "Removido"
        elif tipo == 'Espelho':
            d = EspelhoPontoDoc.query.get(doc_id)
            return f"Ponto de {formatar_mes_ref(d.mes_referencia)}" if d else "Removido"
    except: return "Erro"
    return "N/A"

# --- SISTEMA DE ASSINATURA FORENSE ---

def registrar_assinatura(doc, tipo):
    """Registra os dados de quem baixou o arquivo para auditoria."""
    try:
        if current_user.id == doc.user_id:
            nova_ass = AssinaturaDigital(
                user_id=current_user.id, 
                tipo_documento=tipo, 
                documento_id=doc.id,
                hash_arquivo=calcular_hash_arquivo(doc.conteudo_pdf),
                ip_address=get_client_ip(), 
                user_agent=str(request.user_agent),
                data_assinatura=get_brasil_time()
            )
            db.session.add(nova_ass)
            doc.visualizado = True
            db.session.commit()
    except Exception as e:
        print(f"Erro assinatura: {e}")

# --- ROTAS ADMINISTRATIVAS ---

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
    """Painel principal com histórico unificado."""
    holerites = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(30).all()
    recibos = Recibo.query.order_by(Recibo.created_at.desc()).limit(30).all()
    espelhos = EspelhoPontoDoc.query.order_by(EspelhoPontoDoc.created_at.desc()).limit(30).all()
    
    historico_total = []
    for h in holerites:
        historico_total.append({'tipo': 'Holerite', 'usuario': h.user.real_name, 'info': f"Ref: {formatar_mes_ref(h.mes_referencia)}", 'data': h.enviado_em, 'visto': h.visualizado, 'id': h.id, 'cor': 'blue', 'rota': 'baixar_holerite'})
    for r in recibos:
        historico_total.append({'tipo': 'Recibo', 'usuario': r.user.real_name, 'info': f"Valor: R$ {r.valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), 'data': r.created_at, 'visto': r.visualizado, 'id': r.id, 'cor': 'emerald', 'rota': 'baixar_recibo'})
    for e in espelhos:
        historico_total.append({'tipo': 'Espelho', 'usuario': e.user.real_name, 'info': f"Ponto: {formatar_mes_ref(e.mes_referencia)}", 'data': e.created_at, 'visto': e.visualizado, 'id': e.id, 'cor': 'purple', 'rota': 'baixar_espelho'})
    
    historico_total.sort(key=lambda x: x['data'], reverse=True)
    return render_template('documentos/dashboard.html', historico=historico_total[:50])

@documentos_bp.route('/admin/auditoria')
@login_required
@permission_required('AUDITORIA')
def auditoria_documentos():
    """Lista de assinaturas digitais por funcionário."""
    users = User.query.filter(User.username != TERMINAL_CPF, User.username != 'terminal', User.username != MASTER_CPF).order_by(User.real_name).all()
    dados = []
    for u in users:
        assinaturas = AssinaturaDigital.query.filter_by(user_id=u.id).order_by(AssinaturaDigital.data_assinatura.desc()).all()
        lista_ass = [{'id': a.id, 'tipo': a.tipo_documento, 'referencia': resolve_ref_formatada(a.tipo_documento, a.documento_id), 'data': a.data_assinatura, 'ip': a.ip_address} for a in assinaturas]
        dados.append({'user': u, 'assinaturas': lista_ass, 'total': len(lista_ass)})
    return render_template('documentos/auditoria.html', auditores=dados)

@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_holerites():
    """Importação de PDF em massa com IA."""
    if request.method == 'POST':
        if request.form.get('acao') == 'limpar_tudo':
            if current_user.username == MASTER_CPF:
                Holerite.query.delete(); db.session.commit(); flash('Histórico limpo.', 'warning')
            else: flash('Acesso negado.', 'error')
            return redirect(url_for('documentos.admin_holerites'))

        file = request.files.get('arquivo_pdf')
        mes_ref_manual = request.form.get('mes_ref')
        if not file: flash('Selecione o arquivo.', 'error'); return redirect(url_for('documentos.admin_holerites'))

        try:
            reader = PdfReader(file)
            sucesso = 0
            todos_users = User.query.filter(User.username != TERMINAL_CPF, User.username != 'terminal').all()
            mapa_cpfs = {u.cpf: u for u in todos_users if u.cpf}
            lista_nomes = [u.real_name for u in todos_users]

            for i, page in enumerate(reader.pages):
                writer_tmp = PdfWriter(); writer_tmp.add_page(page)
                buffer_tmp = io.BytesIO(); writer_tmp.write(buffer_tmp)
                page_bytes = buffer_tmp.getvalue()

                dados_ia = analisar_pagina_pdf_ia(page_bytes)
                if not dados_ia.get('eh_holerite'): continue

                user_target = None
                cpf_ia = re.sub(r'\D', '', str(dados_ia.get('cpf', '')))
                if cpf_ia in mapa_cpfs: user_target = mapa_cpfs[cpf_ia]
                
                if not user_target and dados_ia.get('nome'):
                    match = process.extractOne(dados_ia['nome'], lista_nomes)
                    if match and match[1] > 80:
                        user_target = next(u for u in todos_users if u.real_name == match[0])

                if user_target:
                    mes_f = dados_ia.get('mes_referencia') if re.match(r'^\d{4}-\d{2}$', str(dados_ia.get('mes_referencia'))) else mes_ref_manual
                    existente = Holerite.query.filter_by(user_id=user_target.id, mes_referencia=mes_f).first()
                    if existente:
                        existente.conteudo_pdf = page_bytes; existente.enviado_em = get_brasil_time(); existente.visualizado = False
                    else:
                        db.session.add(Holerite(user_id=user_target.id, mes_referencia=mes_f, conteudo_pdf=page_bytes))
                    sucesso += 1
            
            db.session.commit(); flash(f'IA processou {sucesso} holerites.', 'success')
        except Exception as e: db.session.rollback(); flash(f'Erro: {e}', 'error')

    uploads = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    return render_template('documentos/admin_upload_holerite.html', uploads=uploads)

@documentos_bp.route('/admin/recibo/novo', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_novo_recibo():
    users = User.query.filter(User.username != TERMINAL_CPF, User.username != 'terminal').order_by(User.real_name).all()
    if request.method == 'POST':
        try:
            user = User.query.get(request.form.get('user_id'))
            recibo = Recibo(user_id=user.id, valor=float(request.form.get('valor')), data_pagamento=datetime.strptime(request.form.get('data_pagamento'), '%Y-%m-%d').date(), tipo_vale_alimentacao='va' in request.form, tipo_vale_transporte='vt' in request.form, tipo_assiduidade='assiduidade' in request.form, tipo_cesta_basica='cesta' in request.form, forma_pagamento=request.form.get('forma_pagamento'))
            recibo.conteudo_pdf = gerar_pdf_recibo(recibo, user)
            db.session.add(recibo); db.session.commit(); flash(f'Recibo enviado!', 'success')
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e: db.session.rollback(); flash(f'Erro: {e}', 'error')
    return render_template('documentos/novo_recibo.html', users=users, hoje=get_brasil_time().strftime('%Y-%m-%d'))

# --- ROTAS DE DOWNLOAD (O QUE CAUSA O ERRO 500 SE FALTAR) ---

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if current_user.username != MASTER_CPF and doc.user_id != current_user.id and 'DOCUMENTOS' not in (current_user.permissions or ""):
        return redirect(url_for('main.dashboard'))
    registrar_assinatura(doc, 'Holerite')
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Holerite_{doc.mes_referencia}.pdf")

@documentos_bp.route('/baixar/recibo/<int:id>', methods=['POST'])
@login_required
def baixar_recibo(id):
    doc = Recibo.query.get_or_404(id)
    if current_user.username != MASTER_CPF and doc.user_id != current_user.id and 'DOCUMENTOS' not in (current_user.permissions or ""):
        return redirect(url_for('main.dashboard'))
    registrar_assinatura(doc, 'Recibo')
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Recibo_{doc.id}.pdf")

@documentos_bp.route('/baixar/espelho/<int:id>', methods=['POST'])
@login_required
def baixar_espelho(id):
    doc = EspelhoPontoDoc.query.get_or_404(id)
    if current_user.username != MASTER_CPF and doc.user_id != current_user.id and 'DOCUMENTOS' not in (current_user.permissions or ""):
        return redirect(url_for('main.dashboard'))
    registrar_assinatura(doc, 'Espelho')
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Espelho_{doc.mes_referencia}.pdf")

# --- ROTAS DO COLABORADOR ---

@documentos_bp.route('/meus-documentos')
@login_required
def meus_documentos():
    lista = []
    hols = Holerite.query.filter_by(user_id=current_user.id).all()
    recs = Recibo.query.filter_by(user_id=current_user.id).all()
    esps = EspelhoPontoDoc.query.filter_by(user_id=current_user.id).all()
    for h in hols: lista.append({'tipo': 'Holerite', 'titulo': f'Folha {formatar_mes_ref(h.mes_referencia)}', 'data': h.enviado_em, 'id': h.id, 'rota': 'baixar_holerite', 'visto': h.visualizado, 'icone': 'fa-file-invoice-dollar', 'cor': 'blue'})
    for r in recs: lista.append({'tipo': 'Recibo', 'titulo': f'Recibo R$ {r.valor:.2f}', 'data': r.created_at, 'id': r.id, 'rota': 'baixar_recibo', 'visto': r.visualizado, 'icone': 'fa-file-signature', 'cor': 'emerald'})
    for e in esps: lista.append({'tipo': 'Espelho de Ponto', 'titulo': f'Espelho {formatar_mes_ref(e.mes_referencia)}', 'data': e.created_at, 'id': e.id, 'rota': 'baixar_espelho', 'visto': e.visualizado, 'icone': 'fa-calendar-check', 'cor': 'purple'})
    lista.sort(key=lambda x: x['data'], reverse=True)
    return render_template('documentos/meus_documentos.html', docs=lista)

@documentos_bp.route('/api/user-info/<int:user_id>')
@login_required
def api_user_info(user_id):
    if current_user.username != MASTER_CPF and 'DOCUMENTOS' not in (current_user.permissions or ""): return jsonify({'error': 'unauthorized'}), 403
    u = User.query.get_or_404(user_id)
    return jsonify({'real_name': u.real_name, 'cpf': u.cpf, 'razao_social': u.razao_social_empregadora, 'cnpj': u.cnpj_empregador})
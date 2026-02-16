from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo, EspelhoPontoDoc, AssinaturaDigital
from app.utils import get_brasil_time, remove_accents, permission_required, get_client_ip, calcular_hash_arquivo
from app.documentos.utils import gerar_pdf_recibo, gerar_pdf_espelho_mensal, gerar_certificado_entrega
# Importações da IA e PDF
from app.documentos.ai_parser import analisar_texto_holerite
from thefuzz import process
import io
from pypdf import PdfReader, PdfWriter
from datetime import datetime
import re

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

# --- FUNÇÕES AUXILIARES ---

def formatar_mes_ref(mes_ano_str):
    if not mes_ano_str or '-' not in mes_ano_str: return mes_ano_str
    try:
        meses = {'01': 'Janeiro', '02': 'Fevereiro', '03': 'Março', '04': 'Abril', '05': 'Maio', '06': 'Junho', '07': 'Julho', '08': 'Agosto', '09': 'Setembro', '10': 'Outubro', '11': 'Novembro', '12': 'Dezembro'}
        ano, mes = mes_ano_str.split('-')
        return f"{meses.get(mes, mes)} {ano}"
    except: return mes_ano_str

def resolve_ref_formatada(tipo, doc_id):
    try:
        if tipo == 'Holerite':
            d = Holerite.query.get(doc_id)
            return f"Folha de {formatar_mes_ref(d.mes_referencia)}" if d else "Documento Removido"
        elif tipo == 'Recibo':
            d = Recibo.query.get(doc_id)
            return f"Recibo R$ {d.valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if d else "Documento Removido"
        elif tipo == 'Espelho':
            d = EspelhoPontoDoc.query.get(doc_id)
            return f"Ponto de {formatar_mes_ref(d.mes_referencia)}" if d else "Documento Removido"
    except: return "Erro na referência"
    return "N/A"

# --- ROTAS ADMINISTRATIVAS ---

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
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
    users = User.query.filter(User.username != '12345678900', User.username != 'terminal', User.username != 'Thaynara', User.username != '50097952800').order_by(User.real_name).all()
    dados = []
    for u in users:
        assinaturas = AssinaturaDigital.query.filter_by(user_id=u.id).order_by(AssinaturaDigital.data_assinatura.desc()).all()
        lista_ass = [{'id': a.id, 'tipo': a.tipo_documento, 'referencia': resolve_ref_formatada(a.tipo_documento, a.documento_id), 'data': a.data_assinatura, 'ip': a.ip_address} for a in assinaturas]
        dados.append({'user': u, 'assinaturas': lista_ass, 'total': len(lista_ass)})
    return render_template('documentos/auditoria.html', auditores=dados)

@documentos_bp.route('/admin/auditoria/certificado/<int:assinatura_id>')
@login_required
@permission_required('AUDITORIA')
def baixar_certificado(assinatura_id):
    ass = AssinaturaDigital.query.get_or_404(assinatura_id)
    pdf_bytes = gerar_certificado_entrega(ass, ass.user)
    return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name=f"Certificado_Entrega_{ass.user.username}.pdf")

# --- ROTA PRINCIPAL DE IMPORTAÇÃO COM IA ---
@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_holerites():
    if request.method == 'POST':
        if request.form.get('acao') == 'limpar_tudo':
            if current_user.username == '50097952800' or current_user.username == 'Thaynara':
                Holerite.query.delete(); db.session.commit(); flash('Histórico limpo.', 'warning')
            else: flash('Ação restrita ao Master.', 'error')
            return redirect(url_for('documentos.admin_holerites'))

        file = request.files.get('arquivo_pdf')
        mes_ref_manual = request.form.get('mes_ref') # Fallback se a IA não achar data
        
        if not file:
            flash('Selecione um arquivo PDF.', 'error')
            return redirect(url_for('documentos.admin_holerites'))

        try:
            reader = PdfReader(file)
            sucesso = 0
            erros = 0
            
            # Carrega todos os usuários para comparação (exceto sistemas)
            todos_users = User.query.filter(User.username != '12345678900', User.username != 'terminal').all()
            mapa_cpfs = {u.cpf: u for u in todos_users if u.cpf}
            lista_nomes = [u.real_name for u in todos_users]

            for i, page in enumerate(reader.pages):
                texto_pagina = page.extract_text()
                
                # 1. Analisa com a Vertex AI
                dados_ia = analisar_texto_holerite(texto_pagina)
                
                # Se a IA disser que não é holerite ou der erro grave
                if not dados_ia.get('eh_holerite'):
                    print(f"Página {i+1} ignorada pela IA: {dados_ia}")
                    continue

                user_encontrado = None
                
                # 2. Tenta Match Exato por CPF (Prioridade Máxima)
                cpf_ia = dados_ia.get('cpf')
                if cpf_ia:
                    cpf_limpo = re.sub(r'\D', '', cpf_ia)
                    if cpf_limpo in mapa_cpfs:
                        user_encontrado = mapa_cpfs[cpf_limpo]

                # 3. Se não achou por CPF, tenta Match por Nome (Fuzzy)
                if not user_encontrado and dados_ia.get('nome'):
                    nome_ia = dados_ia.get('nome')
                    # Usa FuzzyWuzzy para achar o nome mais parecido na lista
                    melhor_match = process.extractOne(nome_ia, lista_nomes)
                    if melhor_match and melhor_match[1] > 85: # 85% de certeza mínima
                        nome_banco = melhor_match[0]
                        user_encontrado = next((u for u in todos_users if u.real_name == nome_banco), None)

                # 4. Salva o Documento
                if user_encontrado:
                    # Cria um novo PDF só com essa página
                    writer = PdfWriter()
                    writer.add_page(page)
                    out = io.BytesIO()
                    writer.write(out)
                    
                    # Usa a data da IA ou a manual
                    ref_final = dados_ia.get('mes_referencia')
                    # Valida formato AAAA-MM
                    if not ref_final or not re.match(r'^\d{4}-\d{2}$', ref_final):
                        ref_final = mes_ref_manual

                    # Salva no banco
                    # Verifica se já existe para não duplicar no mesmo mês
                    existente = Holerite.query.filter_by(user_id=user_encontrado.id, mes_referencia=ref_final).first()
                    
                    if existente:
                        existente.conteudo_pdf = out.getvalue()
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False
                    else:
                        novo = Holerite(
                            user_id=user_encontrado.id, 
                            mes_referencia=ref_final, 
                            conteudo_pdf=out.getvalue()
                        )
                        db.session.add(novo)
                    
                    sucesso += 1
                else:
                    erros += 1
                    print(f"ALERTA: Usuário não identificado na página {i+1}. Dados IA: {dados_ia}")

            db.session.commit()
            
            msg = f'Processamento IA concluído: {sucesso} enviados.'
            if erros > 0: msg += f' {erros} páginas não identificadas (verifique o PDF).'
            
            if sucesso > 0: flash(msg, 'success')
            else: flash('Nenhum holerite identificado. Verifique se o PDF está legível.', 'warning')

        except Exception as e:
            db.session.rollback()
            flash(f'Erro crítico no processamento: {e}', 'error')

    uploads = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    return render_template('documentos/admin_upload_holerite.html', uploads=uploads)

@documentos_bp.route('/admin/recibo/novo', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_novo_recibo():
    users = User.query.filter(User.username != '12345678900', User.username != 'terminal').order_by(User.real_name).all()
    if request.method == 'POST':
        try:
            user = User.query.get(request.form.get('user_id'))
            recibo = Recibo(user_id=user.id, valor=float(request.form.get('valor')), data_pagamento=datetime.strptime(request.form.get('data_pagamento'), '%Y-%m-%d').date(), tipo_vale_alimentacao='va' in request.form, tipo_vale_transporte='vt' in request.form, tipo_assiduidade='assiduidade' in request.form, tipo_cesta_basica='cesta' in request.form, forma_pagamento=request.form.get('forma_pagamento'))
            recibo.conteudo_pdf = gerar_pdf_recibo(recibo, user)
            db.session.add(recibo); db.session.commit()
            flash(f'Recibo enviado para {user.real_name}!', 'success')
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e: db.session.rollback(); flash(f'Erro: {e}', 'error')
    hoje = get_brasil_time().strftime('%Y-%m-%d')
    return render_template('documentos/novo_recibo.html', users=users, hoje=hoje)

@documentos_bp.route('/admin/disparar-espelhos', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def disparar_espelhos():
    mes_ref = request.form.get('mes_ref')
    if not mes_ref: flash('Selecione o mês.', 'error'); return redirect(url_for('documentos.dashboard_documentos'))
    try:
        users = User.query.filter(User.username != '12345678900', User.username != 'terminal', User.username != 'Thaynara', User.username != '50097952800').all()
        count = 0
        for user in users:
            existente = EspelhoPontoDoc.query.filter_by(user_id=user.id, mes_referencia=mes_ref).first()
            pdf_bytes = gerar_pdf_espelho_mensal(user, mes_ref)
            if existente: existente.conteudo_pdf = pdf_bytes; existente.visualizado = False; existente.created_at = get_brasil_time()
            else: db.session.add(EspelhoPontoDoc(user_id=user.id, mes_referencia=mes_ref, conteudo_pdf=pdf_bytes))
            count += 1
        db.session.commit(); flash(f'{count} espelhos enviados.', 'success')
    except Exception as e: db.session.rollback(); flash(f'Erro: {e}', 'error')
    return redirect(url_for('documentos.dashboard_documentos'))

# --- ROTAS USER ---
@documentos_bp.route('/meus-documentos')
@login_required
def meus_documentos():
    lista = []
    for h in Holerite.query.filter_by(user_id=current_user.id).all():
        lista.append({'tipo': 'Holerite', 'titulo': f'Folha de {formatar_mes_ref(h.mes_referencia)}', 'data': h.enviado_em, 'id': h.id, 'rota': 'baixar_holerite', 'visto': h.visualizado, 'icone': 'fa-file-invoice-dollar', 'cor': 'blue'})
    for r in Recibo.query.filter_by(user_id=current_user.id).all():
        lista.append({'tipo': 'Recibo', 'titulo': f'Recibo - R$ {r.valor:.2f}', 'data': r.created_at, 'id': r.id, 'rota': 'baixar_recibo', 'visto': r.visualizado, 'icone': 'fa-file-signature', 'cor': 'emerald'})
    for e in EspelhoPontoDoc.query.filter_by(user_id=current_user.id).all():
        lista.append({'tipo': 'Espelho de Ponto', 'titulo': f'Espelho - {formatar_mes_ref(e.mes_referencia)}', 'data': e.created_at, 'id': e.id, 'rota': 'baixar_espelho', 'visto': e.visualizado, 'icone': 'fa-calendar-check', 'cor': 'purple'})
    lista.sort(key=lambda x: x['data'], reverse=True)
    return render_template('documentos/meus_documentos.html', docs=lista)

def registrar_assinatura(doc, tipo):
    if current_user.id == doc.user_id:
        db.session.add(AssinaturaDigital(user_id=current_user.id, tipo_documento=tipo, documento_id=doc.id, hash_arquivo=calcular_hash_arquivo(doc.conteudo_pdf), ip_address=get_client_ip(), user_agent=str(request.user_agent), data_assinatura=get_brasil_time()))
        doc.visualizado = True; db.session.commit()

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    perms = current_user.permissions or ""
    if current_user.username != '50097952800' and current_user.username != 'Thaynara' and 'DOCUMENTOS' not in perms and doc.user_id != current_user.id: return redirect(url_for('main.dashboard'))
    registrar_assinatura(doc, 'Holerite')
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Holerite_{doc.mes_referencia}.pdf")

@documentos_bp.route('/baixar/recibo/<int:id>', methods=['POST'])
@login_required
def baixar_recibo(id):
    doc = Recibo.query.get_or_404(id)
    perms = current_user.permissions or ""
    if current_user.username != '50097952800' and current_user.username != 'Thaynara' and 'DOCUMENTOS' not in perms and doc.user_id != current_user.id: return redirect(url_for('main.dashboard'))
    registrar_assinatura(doc, 'Recibo')
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Recibo_{doc.id}.pdf")

@documentos_bp.route('/baixar/espelho/<int:id>', methods=['POST'])
@login_required
def baixar_espelho(id):
    doc = EspelhoPontoDoc.query.get_or_404(id)
    perms = current_user.permissions or ""
    if current_user.username != '50097952800' and current_user.username != 'Thaynara' and 'DOCUMENTOS' not in perms and doc.user_id != current_user.id: return redirect(url_for('main.dashboard'))
    registrar_assinatura(doc, 'Espelho')
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Espelho_{doc.mes_referencia}.pdf")

@documentos_bp.route('/api/user-info/<int:user_id>')
@login_required
def api_user_info(user_id):
    perms = current_user.permissions or ""
    if current_user.username != '50097952800' and current_user.username != 'Thaynara' and 'DOCUMENTOS' not in perms: return jsonify({'error': 'unauthorized'}), 403
    u = User.query.get_or_404(user_id)
    return jsonify({'real_name': u.real_name, 'cpf': u.cpf, 'razao_social': u.razao_social_empregadora, 'cnpj': u.cnpj_empregador})
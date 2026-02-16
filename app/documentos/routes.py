from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo, EspelhoPontoDoc, AssinaturaDigital
from app.utils import get_brasil_time, remove_accents, permission_required, get_client_ip, calcular_hash_arquivo
from app.documentos.utils import gerar_pdf_recibo, gerar_pdf_espelho_mensal, gerar_certificado_entrega
from app.documentos.ai_parser import analisar_pagina_pdf_ia # Nova função
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

# --- ROTAS ADMINISTRATIVAS ---

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
    holerites = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(30).all()
    recibos = Recibo.query.order_by(Recibo.created_at.desc()).limit(30).all()
    espelhos = EspelhoPontoDoc.query.order_by(EspelhoPontoDoc.created_at.desc()).limit(30).all()
    historico_total = []
    for h in holerites: historico_total.append({'tipo': 'Holerite', 'usuario': h.user.real_name, 'info': f"Ref: {formatar_mes_ref(h.mes_referencia)}", 'data': h.enviado_em, 'visto': h.visualizado, 'id': h.id, 'cor': 'blue', 'rota': 'baixar_holerite'})
    for r in recibos: historico_total.append({'tipo': 'Recibo', 'usuario': r.user.real_name, 'info': f"Valor: R$ {r.valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), 'data': r.created_at, 'visto': r.visualizado, 'id': r.id, 'cor': 'emerald', 'rota': 'baixar_recibo'})
    for e in espelhos: historico_total.append({'tipo': 'Espelho', 'usuario': e.user.real_name, 'info': f"Ponto: {formatar_mes_ref(e.mes_referencia)}", 'data': e.created_at, 'visto': e.visualizado, 'id': e.id, 'cor': 'purple', 'rota': 'baixar_espelho'})
    historico_total.sort(key=lambda x: x['data'], reverse=True)
    return render_template('documentos/dashboard.html', historico=historico_total[:50])

@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_holerites():
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        mes_ref_manual = request.form.get('mes_ref')
        
        if not file:
            flash('Selecione o arquivo.', 'error')
            return redirect(url_for('documentos.admin_holerites'))

        try:
            reader = PdfReader(file)
            sucesso = 0
            # Carrega usuários para o Match
            todos_users = User.query.filter(User.username != '12345678900', User.username != 'terminal').all()
            mapa_cpfs = {u.cpf: u for u in todos_users if u.cpf}
            lista_nomes = [u.real_name for u in todos_users]

            for i, page in enumerate(reader.pages):
                # Extrai a página individualmente como bytes
                writer_tmp = PdfWriter()
                writer_tmp.add_page(page)
                buffer_tmp = io.BytesIO()
                writer_tmp.write(buffer_tmp)
                page_bytes = buffer_tmp.getvalue()

                # IA analisa visualmente o PDF
                dados_ia = analisar_pagina_pdf_ia(page_bytes)
                
                if not dados_ia.get('eh_holerite'): continue

                user_target = None
                
                # 1. Match por CPF
                cpf_ia = re.sub(r'\D', '', str(dados_ia.get('cpf', '')))
                if cpf_ia in mapa_cpfs:
                    user_target = mapa_cpfs[cpf_ia]
                
                # 2. Match por Nome (Fuzzy)
                if not user_target and dados_ia.get('nome'):
                    match = process.extractOne(dados_ia['nome'], lista_nomes)
                    if match and match[1] > 80:
                        user_target = next(u for u in todos_users if u.real_name == match[0])

                if user_target:
                    mes_final = dados_ia.get('mes_referencia') or mes_ref_manual
                    existente = Holerite.query.filter_by(user_id=user_target.id, mes_referencia=mes_final).first()
                    if existente:
                        existente.conteudo_pdf = page_bytes
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False
                    else:
                        db.session.add(Holerite(user_id=user_target.id, mes_referencia=mes_final, conteudo_pdf=page_bytes))
                    sucesso += 1
            
            db.session.commit()
            flash(f'Sucesso! {sucesso} holerites processados via IA.', 'success')
        except Exception as e:
            flash(f'Erro no processamento: {e}', 'error')

    uploads = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    return render_template('documentos/admin_upload_holerite.html', uploads=uploads)

# (Mantenha as demais rotas: auditoria, baixar_certificado, admin_novo_recibo, etc. como estavam no passo anterior)
@documentos_bp.route('/admin/auditoria')
@login_required
@permission_required('AUDITORIA')
def auditoria_documentos():
    users = User.query.filter(User.username != '12345678900', User.username != 'terminal', User.username != '50097952800').order_by(User.real_name).all()
    dados = []
    for u in users:
        assinaturas = AssinaturaDigital.query.filter_by(user_id=u.id).order_by(AssinaturaDigital.data_assinatura.desc()).all()
        lista_ass = []
        for a in assinaturas:
            lista_ass.append({'id': a.id, 'tipo': a.tipo_documento, 'data': a.data_assinatura, 'ip': a.ip_address})
        dados.append({'user': u, 'assinaturas': lista_ass, 'total': len(lista_ass)})
    return render_template('documentos/auditoria.html', auditores=dados)

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if current_user.username != '50097952800' and doc.user_id != current_user.id: return redirect(url_for('main.dashboard'))
    registrar_assinatura(doc, 'Holerite')
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Holerite_{doc.mes_referencia}.pdf")

def registrar_assinatura(doc, tipo):
    if current_user.id == doc.user_id:
        db.session.add(AssinaturaDigital(user_id=current_user.id, tipo_documento=tipo, documento_id=doc.id, hash_arquivo=calcular_hash_arquivo(doc.conteudo_pdf), ip_address=get_client_ip(), user_agent=str(request.user_agent), data_assinatura=get_brasil_time()))
        doc.visualizado = True; db.session.commit()

@documentos_bp.route('/meus-documentos')
@login_required
def meus_documentos():
    lista = []
    for h in Holerite.query.filter_by(user_id=current_user.id).all():
        lista.append({'tipo': 'Holerite', 'titulo': f'Folha {h.mes_referencia}', 'data': h.enviado_em, 'id': h.id, 'rota': 'baixar_holerite', 'visto': h.visualizado, 'icone': 'fa-file-invoice-dollar', 'cor': 'blue'})
    lista.sort(key=lambda x: x['data'], reverse=True)
    return render_template('documentos/meus_documentos.html', docs=lista)
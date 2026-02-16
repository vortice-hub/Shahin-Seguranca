from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo, EspelhoPontoDoc, AssinaturaDigital
from app.utils import get_brasil_time, remove_accents, permission_required, get_client_ip, calcular_hash_arquivo
from app.documentos.utils import gerar_pdf_recibo, gerar_pdf_espelho_mensal, gerar_certificado_entrega
import io
from pypdf import PdfReader, PdfWriter
from datetime import datetime

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

# --- FUNÇÕES AUXILIARES DE FORMATAÇÃO ---

def formatar_mes_ref(mes_ano_str):
    """Converte '2026-02' em 'Fevereiro 2026'."""
    if not mes_ano_str or '-' not in mes_ano_str:
        return mes_ano_str
    try:
        meses = {
            '01': 'Janeiro', '02': 'Fevereiro', '03': 'Março', '04': 'Abril',
            '05': 'Maio', '06': 'Junho', '07': 'Julho', '08': 'Agosto',
            '09': 'Setembro', '10': 'Outubro', '11': 'Novembro', '12': 'Dezembro'
        }
        ano, mes = mes_ano_str.split('-')
        return f"{meses.get(mes, mes)} {ano}"
    except:
        return mes_ano_str

def resolve_ref_formatada(tipo, doc_id):
    """Busca a referência amigável do documento original para a auditoria."""
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
    except:
        return "Erro na referência"
    return "N/A"

# --- ROTAS ADMINISTRATIVAS ---

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
    """Painel principal do RH com Histórico Unificado."""
    # Busca os últimos envios de cada categoria
    holerites = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(30).all()
    recibos = Recibo.query.order_by(Recibo.created_at.desc()).limit(30).all()
    espelhos = EspelhoPontoDoc.query.order_by(EspelhoPontoDoc.created_at.desc()).limit(30).all()
    
    historico_total = []
    
    for h in holerites:
        historico_total.append({
            'tipo': 'Holerite', 
            'usuario': h.user.real_name, 
            'info': f"Ref: {formatar_mes_ref(h.mes_referencia)}", 
            'data': h.enviado_em, 
            'visto': h.visualizado, 
            'id': h.id, 
            'cor': 'blue', 
            'rota': 'baixar_holerite'
        })
        
    for r in recibos:
        historico_total.append({
            'tipo': 'Recibo', 
            'usuario': r.user.real_name, 
            'info': f"Valor: R$ {r.valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), 
            'data': r.created_at, 
            'visto': r.visualizado, 
            'id': r.id, 
            'cor': 'emerald', 
            'rota': 'baixar_recibo'
        })
        
    for e in espelhos:
        historico_total.append({
            'tipo': 'Espelho', 
            'usuario': e.user.real_name, 
            'info': f"Ponto: {formatar_mes_ref(e.mes_referencia)}", 
            'data': e.created_at, 
            'visto': e.visualizado, 
            'id': e.id, 
            'cor': 'purple', 
            'rota': 'baixar_espelho'
        })
    
    # Ordena por data de envio (mais recente primeiro)
    historico_total.sort(key=lambda x: x['data'], reverse=True)
    
    return render_template('documentos/dashboard.html', historico=historico_total[:50])

@documentos_bp.route('/admin/auditoria')
@login_required
@permission_required('AUDITORIA')
def auditoria_documentos():
    """Lista alfabética de funcionários com acordeão de assinaturas."""
    # Busca todos os utilizadores (exceto sistemas) ordenados alfabeticamente
    users = User.query.filter(User.username != 'terminal', User.username != '50097952800').order_by(User.real_name).all()
    
    dados_auditoria = []
    for u in users:
        assinaturas = AssinaturaDigital.query.filter_by(user_id=u.id).order_by(AssinaturaDigital.data_assinatura.desc()).all()
        lista_ass = []
        for a in assinaturas:
            lista_ass.append({
                'id': a.id,
                'tipo': a.tipo_documento,
                'referencia': resolve_ref_formatada(a.tipo_documento, a.documento_id),
                'data': a.data_assinatura,
                'ip': a.ip_address
            })
        
        dados_auditoria.append({
            'user': u,
            'assinaturas': lista_ass,
            'total': len(lista_ass)
        })

    return render_template('documentos/auditoria.html', auditores=dados_auditoria)

@documentos_bp.route('/admin/auditoria/certificado/<int:assinatura_id>')
@login_required
@permission_required('AUDITORIA')
def baixar_certificado(assinatura_id):
    """Gera o PDF do Certificado Forense de entrega."""
    ass = AssinaturaDigital.query.get_or_404(assinatura_id)
    pdf_bytes = gerar_certificado_entrega(ass, ass.user)
    return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name=f"Certificado_Entrega_{ass.user.username}.pdf")

@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_holerites():
    """Upload e separação de PDFs de Holerites."""
    if request.method == 'POST':
        if request.form.get('acao') == 'limpar_tudo':
            if current_user.username == '50097952800':
                Holerite.query.delete(); db.session.commit(); flash('Histórico de holerites limpo.', 'warning')
            else:
                flash('Ação restrita ao Master absoluto.', 'error')
            return redirect(url_for('documentos.admin_holerites'))

        file = request.files.get('arquivo_pdf')
        mes_ref = request.form.get('mes_ref')
        if not file or not mes_ref: 
            flash('Arquivo e mês são obrigatórios.', 'error')
            return redirect(url_for('documentos.admin_holerites'))
            
        try:
            reader = PdfReader(file)
            sucesso = 0
            
            def encontrar_user(texto):
                texto_limpo = remove_accents(texto).upper()
                for u in User.query.all():
                    if u.username == 'terminal': continue
                    nome_limpo = remove_accents(u.real_name).upper().strip()
                    if len(nome_limpo.split()) > 1 and nome_limpo in texto_limpo: return u
                return None

            for page in reader.pages:
                user = encontrar_user(page.extract_text())
                if user:
                    writer = PdfWriter(); writer.add_page(page)
                    out = io.BytesIO(); writer.write(out)
                    existente = Holerite.query.filter_by(user_id=user.id, mes_referencia=mes_ref).first()
                    
                    if existente:
                        existente.conteudo_pdf = out.getvalue()
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False
                    else:
                        novo = Holerite(user_id=user.id, mes_referencia=mes_ref, conteudo_pdf=out.getvalue())
                        db.session.add(novo)
                    sucesso += 1
                    
            db.session.commit()
            flash(f'Processamento concluído: {sucesso} holerites enviados.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro no processamento do PDF: {e}', 'error')

    uploads = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    return render_template('documentos/admin_upload_holerite.html', uploads=uploads)

@documentos_bp.route('/admin/recibo/novo', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_novo_recibo():
    """Geração de recibos avulsos para benefícios."""
    users = User.query.filter(User.username != 'terminal').order_by(User.real_name).all()
    if request.method == 'POST':
        try:
            user = User.query.get(request.form.get('user_id'))
            recibo = Recibo(
                user_id=user.id, 
                valor=float(request.form.get('valor')),
                data_pagamento=datetime.strptime(request.form.get('data_pagamento'), '%Y-%m-%d').date(),
                tipo_vale_alimentacao='va' in request.form, 
                tipo_vale_transporte='vt' in request.form,
                tipo_assiduidade='assiduidade' in request.form, 
                tipo_cesta_basica='cesta' in request.form,
                forma_pagamento=request.form.get('forma_pagamento')
            )
            recibo.conteudo_pdf = gerar_pdf_recibo(recibo, user)
            db.session.add(recibo)
            db.session.commit()
            flash(f'Recibo gerado e enviado para {user.real_name}!', 'success')
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao gerar recibo: {e}', 'error')
            
    hoje = get_brasil_time().strftime('%Y-%m-%d')
    return render_template('documentos/novo_recibo.html', users=users, hoje=hoje)

@documentos_bp.route('/admin/disparar-espelhos', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def disparar_espelhos():
    """Geração em massa de PDFs de espelhos de ponto."""
    mes_ref = request.form.get('mes_ref')
    if not mes_ref:
        flash('Mês de referência não selecionado.', 'error')
        return redirect(url_for('documentos.dashboard_documentos'))
        
    try:
        users = User.query.filter(User.username != 'terminal', User.username != '50097952800').all()
        count = 0
        for user in users:
            existente = EspelhoPontoDoc.query.filter_by(user_id=user.id, mes_referencia=mes_ref).first()
            pdf_bytes = gerar_pdf_espelho_mensal(user, mes_ref)
            
            if existente:
                existente.conteudo_pdf = pdf_bytes
                existente.visualizado = False
                existente.created_at = get_brasil_time()
            else:
                novo = EspelhoPontoDoc(user_id=user.id, mes_referencia=mes_ref, conteudo_pdf=pdf_bytes)
                db.session.add(novo)
            count += 1
            
        db.session.commit()
        flash(f'Sucesso: {count} espelhos de ponto enviados.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao disparar espelhos: {e}', 'error')
        
    return redirect(url_for('documentos.dashboard_documentos'))

# --- ROTAS DO UTILIZADOR (COLABORADOR) ---

@documentos_bp.route('/meus-documentos')
@login_required
def meus_documentos():
    """Listagem de documentos disponíveis para o funcionário."""
    lista_docs = []
    
    # Busca Holerites
    for h in Holerite.query.filter_by(user_id=current_user.id).all():
        lista_docs.append({
            'tipo': 'Holerite', 
            'titulo': f'Folha de {formatar_mes_ref(h.mes_referencia)}', 
            'data': h.enviado_em, 
            'id': h.id, 
            'rota': 'baixar_holerite', 
            'visto': h.visualizado, 
            'icone': 'fa-file-invoice-dollar', 
            'cor': 'blue'
        })
        
    # Busca Recibos
    for r in Recibo.query.filter_by(user_id=current_user.id).all():
        lista_docs.append({
            'tipo': 'Recibo', 
            'titulo': f'Recibo de Benefícios - R$ {r.valor:.2f}', 
            'data': r.created_at, 
            'id': r.id, 
            'rota': 'baixar_recibo', 
            'visto': r.visualizado, 
            'icone': 'fa-file-signature', 
            'cor': 'emerald'
        })
        
    # Busca Espelhos
    for e in EspelhoPontoDoc.query.filter_by(user_id=current_user.id).all():
        lista_docs.append({
            'tipo': 'Espelho de Ponto', 
            'titulo': f'Espelho de Ponto - {formatar_mes_ref(e.mes_referencia)}', 
            'data': e.created_at, 
            'id': e.id, 
            'rota': 'baixar_espelho', 
            'visto': e.visualizado, 
            'icone': 'fa-calendar-check', 
            'cor': 'purple'
        })
        
    lista_docs.sort(key=lambda x: x['data'], reverse=True)
    return render_template('documentos/meus_documentos.html', docs=lista_docs)

# --- DOWNLOADS E REGISTO DE ASSINATURA ---

def registrar_assinatura(doc, tipo):
    """Regista silenciosamente os dados forenses no momento do download."""
    try:
        # Só regista se quem baixa for o proprietário do documento
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
        print(f"Erro ao registar assinatura forense: {e}")

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    # Permissão: Dono do doc ou Master/RH
    perms = current_user.permissions or ""
    if current_user.username != '50097952800' and 'DOCUMENTOS' not in perms and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
        
    registrar_assinatura(doc, 'Holerite')
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Holerite_{doc.mes_referencia}.pdf")

@documentos_bp.route('/baixar/recibo/<int:id>', methods=['POST'])
@login_required
def baixar_recibo(id):
    doc = Recibo.query.get_or_404(id)
    perms = current_user.permissions or ""
    if current_user.username != '50097952800' and 'DOCUMENTOS' not in perms and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
        
    registrar_assinatura(doc, 'Recibo')
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Recibo_{doc.id}.pdf")

@documentos_bp.route('/baixar/espelho/<int:id>', methods=['POST'])
@login_required
def baixar_espelho(id):
    doc = EspelhoPontoDoc.query.get_or_404(id)
    perms = current_user.permissions or ""
    if current_user.username != '50097952800' and 'DOCUMENTOS' not in perms and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
        
    registrar_assinatura(doc, 'Espelho')
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Espelho_{doc.mes_referencia}.pdf")

@documentos_bp.route('/api/user-info/<int:user_id>')
@login_required
def api_user_info(user_id):
    """API para preenchimento automático no cadastro de recibos."""
    perms = current_user.permissions or ""
    if current_user.username != '50097952800' and 'DOCUMENTOS' not in perms:
        return jsonify({'error': 'unauthorized'}), 403
        
    u = User.query.get_or_404(user_id)
    return jsonify({
        'real_name': u.real_name, 
        'cpf': u.cpf, 
        'razao_social': u.razao_social_empregadora, 
        'cnpj': u.cnpj_empregador
    })



from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo, AssinaturaDigital, Atestado, PontoResumo
from app.utils import get_brasil_time, permission_required, has_permission, limpar_nome, get_client_ip, calcular_hash_arquivo, enviar_notificacao, format_minutes_to_hm
from app.documentos.storage import salvar_no_storage, baixar_bytes_storage
from app.documentos.ai_parser import extrair_dados_holerite
from app.documentos.utils import gerar_pdf_recibo, gerar_pdf_espelho_mensal, gerar_certificado_entrega
from app.documentos.atestado_parser import analisar_atestado_vision
from datetime import datetime, timedelta
from pypdf import PdfReader, PdfWriter
import io
import pandas as pd 

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

@documentos_bp.route('/admin')
@login_required
@permission_required('DOCUMENTOS')
def dashboard_documentos():
    f_nome = request.args.get('nome', '').strip()
    f_mes = request.args.get('mes', '')
    f_tipo = request.args.get('tipo', '')

    q_holerite = Holerite.query.filter(Holerite.status != 'Revisao')
    q_recibo = Recibo.query

    if f_nome:
        q_holerite = q_holerite.join(User).filter(User.real_name.ilike(f'%{f_nome}%'))
        q_recibo = q_recibo.join(User).filter(User.real_name.ilike(f'%{f_nome}%'))
    
    if f_mes:
        q_holerite = q_holerite.filter(Holerite.mes_referencia == f_mes)
        q_recibo = q_recibo.filter(db.extract('month', Recibo.data_pagamento) == int(f_mes.split('-')[1]),
                                   db.extract('year', Recibo.data_pagamento) == int(f_mes.split('-')[0]))

    holerites_db = q_holerite.order_by(Holerite.enviado_em.desc()).limit(50).all()
    recibos_db = q_recibo.order_by(Recibo.created_at.desc()).limit(50).all()
    total_revisao = Holerite.query.filter_by(status='Revisao').count()
    
    historico = []
    
    if not f_tipo or f_tipo in ['Holerite', 'Espelho']:
        for h in holerites_db:
            is_ponto = True if h.url_arquivo and 'espelhos' in h.url_arquivo else False
            tipo_label = "Espelho de Ponto" if is_ponto else "Holerite"
            historico.append({
                'id': h.id, 'doc_type': 'holerite',
                'tipo': tipo_label, 'cor': 'purple' if is_ponto else 'blue',
                'usuario': h.user.real_name if h.user else "N/A",
                'info': h.mes_referencia, 'data': h.enviado_em,
                'visualizado': h.visualizado, 'rota': 'baixar_holerite'
            })

    if not f_tipo or f_tipo == 'Recibo':
        for r in recibos_db:
            historico.append({
                'id': r.id, 'doc_type': 'recibo',
                'tipo': 'Recibo', 'cor': 'emerald',
                'usuario': r.user.real_name, 'info': f"R$ {r.valor:,.2f}",
                'data': r.created_at, 'visualizado': r.visualizado, 'rota': 'baixar_recibo'
            })

    historico.sort(key=lambda x: x['data'] if x['data'] else get_brasil_time(), reverse=True)
    return render_template('documentos/dashboard.html', historico=historico, pendentes_revisao=total_revisao, f_nome=f_nome, f_mes=f_mes, f_tipo=f_tipo)

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if not has_permission('DOCUMENTOS') and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
    
    if not doc.url_arquivo:
        flash("Arquivo não encontrado no servidor de nuvem.", "error")
        return redirect(url_for('documentos.dashboard_documentos'))

    arquivo_bytes = baixar_bytes_storage(doc.url_arquivo)
    nome_download = f"ponto_{doc.mes_referencia}.pdf" if 'espelhos' in doc.url_arquivo else f"holerite_{doc.mes_referencia}.pdf"
    
    if doc.user_id == current_user.id and not doc.visualizado:
        doc.visualizado = True
        assinatura = AssinaturaDigital(
            user_id=current_user.id, documento_id=doc.id,
            tipo_documento=f"Doc - {doc.mes_referencia}",
            hash_arquivo=calcular_hash_arquivo(arquivo_bytes),
            data_assinatura=get_brasil_time(), ip_address=get_client_ip(),
            user_agent=request.headers.get('User-Agent', 'Desconhecido')[:250]
        )
        db.session.add(assinatura); db.session.commit()

    return send_file(io.BytesIO(arquivo_bytes), mimetype='application/pdf', as_attachment=True, download_name=nome_download)

@documentos_bp.route('/baixar/recibo/<int:id>', methods=['POST'])
@login_required
def baixar_recibo(id):
    doc = Recibo.query.get_or_404(id)
    if not has_permission('DOCUMENTOS') and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
        
    if not doc.url_arquivo:
        flash("Recibo não encontrado na nuvem.", "error")
        return redirect(url_for('documentos.dashboard_documentos'))

    arquivo_bytes = baixar_bytes_storage(doc.url_arquivo)
    
    if doc.user_id == current_user.id and not doc.visualizado:
        doc.visualizado = True
        assinatura = AssinaturaDigital(
            user_id=current_user.id, documento_id=doc.id,
            tipo_documento=f"Recibo - R$ {doc.valor}",
            hash_arquivo=calcular_hash_arquivo(arquivo_bytes),
            data_assinatura=get_brasil_time(), ip_address=get_client_ip(),
            user_agent=request.headers.get('User-Agent', 'Desconhecido')[:250]
        )
        db.session.add(assinatura); db.session.commit()

    return send_file(io.BytesIO(arquivo_bytes), mimetype='application/pdf', as_attachment=True, download_name=f"recibo_{id}.pdf")

@documentos_bp.route('/meus-documentos')
@login_required
def meus_documentos():
    holerites = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.enviado_em.desc()).all()
    recibos = Recibo.query.filter_by(user_id=current_user.id).order_by(Recibo.created_at.desc()).all()
    docs = []
    for h in holerites:
        e_ponto = True if h.url_arquivo and 'espelhos' in h.url_arquivo else False
        docs.append({'id': h.id, 'tipo': 'Espelho' if e_ponto else 'Holerite', 'titulo': f"{'Ponto' if e_ponto else 'Holerite'} - {h.mes_referencia}", 'cor': 'purple' if e_ponto else 'blue', 'icone': 'fa-calendar' if e_ponto else 'fa-file', 'data': h.enviado_em, 'visto': h.visualizado, 'rota': 'baixar_holerite'})
    for r in recibos:
        docs.append({'id': r.id, 'tipo': 'Recibo', 'titulo': 'Recibo', 'cor': 'emerald', 'icone': 'fa-receipt', 'data': r.created_at, 'visto': r.visualizado, 'rota': 'baixar_recibo'})
    return render_template('documentos/meus_documentos.html', docs=docs)

@documentos_bp.route('/admin/revisao')
@login_required
@permission_required('DOCUMENTOS')
def revisao_holerites():
    pendentes = Holerite.query.filter_by(status='Revisao').all()
    funcionarios = User.query.filter(User.username != '12345678900', User.username != 'terminal').order_by(User.real_name).all()
    return render_template('documentos/revisao.html', pendentes=pendentes, funcionarios=funcionarios)

@documentos_bp.route('/admin/revisao/vincular', methods=['POST'])
@login_required
def vincular_holerite():
    h = Holerite.query.get(request.form.get('holerite_id'))
    u_id = request.form.get('user_id')
    if h and u_id: 
        h.user_id = u_id
        h.status = 'Enviado'
        db.session.commit()
        enviar_notificacao(u_id, f"Seu Holerite ({h.mes_referencia}) foi liberado.", "/documentos/meus-documentos")
    return redirect(url_for('documentos.revisao_holerites'))

@documentos_bp.route('/admin/auditoria')
@login_required
@permission_required('DOCUMENTOS')
def revisao_auditoria():
    usuarios = User.query.filter(User.username != '12345678900', User.username != 'terminal').order_by(User.real_name).all()
    auditores = []
    for u in usuarios:
        assinaturas = AssinaturaDigital.query.filter_by(user_id=u.id).order_by(AssinaturaDigital.data_assinatura.desc()).all()
        l = [{'id':a.id, 'tipo':a.tipo_documento, 'data':a.data_assinatura, 'ip':a.ip_address} for a in assinaturas]
        auditores.append({'user': u, 'total': len(assinaturas), 'assinaturas': l})
    return render_template('documentos/auditoria.html', auditores=auditores)

@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_holerites():
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        if not file: return redirect(request.url)
        try:
            reader = PdfReader(file)
            sucesso, revisao = 0, 0
            usuarios_db = User.query.filter(User.role != 'Terminal').all()
            usuarios_map = {limpar_nome(u.real_name): u.id for u in usuarios_db}
            lista_nomes_banco = list(usuarios_map.keys())

            for page in reader.pages:
                writer = PdfWriter(); writer.add_page(page); buffer = io.BytesIO(); writer.write(buffer)
                pdf_bytes = buffer.getvalue()
                dados = extrair_dados_holerite(pdf_bytes, lista_nomes_banco)
                nome_identificado = dados.get('nome', '')
                mes_ref = dados.get('mes_referencia', '2026-02')
                caminho_blob = salvar_no_storage(pdf_bytes, f"holerites/{mes_ref}")
                if not caminho_blob: continue
                user_id = usuarios_map.get(nome_identificado)
                novo_h = Holerite(user_id=user_id, mes_referencia=mes_ref, url_arquivo=caminho_blob,
                                 status='Enviado' if user_id else 'Revisao', enviado_em=get_brasil_time())
                db.session.add(novo_h)
                if user_id: 
                    sucesso += 1
                    enviar_notificacao(user_id, f"Novo Holerite disponível ({mes_ref}).", "/documentos/meus-documentos")
                else: revisao += 1
            db.session.commit()
            flash(f"Processado: {sucesso} enviados, {revisao} para revisão.", "success")
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e:
            db.session.rollback(); flash(f"Erro: {e}", "error")
    return render_template('documentos/admin_upload_holerite.html')

@documentos_bp.route('/admin/recibo/novo', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def novo_recibo():
    if request.method == 'POST':
        u = User.query.get(request.form.get('user_id'))
        r = Recibo(user_id=u.id, valor=float(request.form.get('valor', 0)), data_pagamento=get_brasil_time().date())
        pdf_bytes = gerar_pdf_recibo(r, u)
        mes_ref = get_brasil_time().strftime('%Y-%m')
        r.url_arquivo = salvar_no_storage(pdf_bytes, f"recibos/{mes_ref}")
        db.session.add(r); db.session.commit()
        enviar_notificacao(u.id, "Novo Recibo disponível.", "/documentos/meus-documentos")
        return redirect(url_for('documentos.dashboard_documentos'))
    users = User.query.filter(User.username != '12345678900').all()
    return render_template('documentos/novo_recibo.html', users=users, hoje=get_brasil_time().strftime('%Y-%m-%d'))

@documentos_bp.route('/admin/disparar-espelhos', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def disparar_espelhos():
    mes = request.form.get('mes_ref')
    users = User.query.filter(User.username != '12345678900').all()
    sucessos = 0
    for u in users:
        try:
            pdf_bytes = gerar_pdf_espelho_mensal(u, mes)
            caminho_blob = salvar_no_storage(pdf_bytes, f"espelhos/{mes}")
            db.session.add(Holerite(user_id=u.id, mes_referencia=mes, url_arquivo=caminho_blob, status='Enviado', enviado_em=get_brasil_time()))
            enviar_notificacao(u.id, f"Espelho de Ponto ({mes}) disponível.", "/documentos/meus-documentos")
            sucessos += 1
        except Exception as e: print(f"Erro: {e}")
    db.session.commit(); flash(f'{sucessos} espelhos gerados!', 'success')
    return redirect(url_for('documentos.dashboard_documentos'))

# --- MÓDULO DE ATESTADOS ---
@documentos_bp.route('/atestados/meus')
@login_required
def meus_atestados():
    atestados = Atestado.query.filter_by(user_id=current_user.id).order_by(Atestado.data_envio.desc()).all()
    return render_template('documentos/meus_atestados.html', atestados=atestados)

@documentos_bp.route('/atestado/novo', methods=['GET', 'POST'])
@login_required
def enviar_atestado():
    if request.method == 'POST':
        file = request.files.get('arquivo_atestado')
        if not file:
            flash('Selecione um arquivo.', 'error')
            return redirect(request.url)
        try:
            file_bytes = file.read()
            caminho_blob = salvar_no_storage(file_bytes, f"atestados/{get_brasil_time().strftime('%Y-%m')}")
            dados_ia = analisar_atestado_vision(file_bytes, current_user.real_name)
            dt_inicio = datetime.strptime(dados_ia['data_inicio'], '%Y-%m-%d').date() if dados_ia['data_inicio'] else None
            novo_at = Atestado(user_id=current_user.id, data_envio=get_brasil_time(), url_arquivo=caminho_blob,
                              data_inicio_afastamento=dt_inicio, quantidade_dias=dados_ia['dias_afastamento'],
                              texto_extraido=dados_ia['texto_bruto'], status='Revisao')
            db.session.add(novo_at); db.session.commit()
            flash('Atestado enviado com sucesso!', 'success')
            return redirect(url_for('documentos.meus_atestados'))
        except: flash('Erro ao processar atestado.', 'error')
    return render_template('documentos/enviar_atestado.html')

@documentos_bp.route('/admin/atestados')
@login_required
@permission_required('DOCUMENTOS')
def gestao_atestados():
    atestados = Atestado.query.order_by(Atestado.data_envio.desc()).all()
    return render_template('documentos/gestao_atestados.html', atestados=atestados)

@documentos_bp.route('/admin/atestados/<int:id>/avaliar', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def avaliar_atestado(id):
    at = Atestado.query.get_or_404(id)
    acao = request.form.get('acao')
    if acao == 'aprovar':
        at.status = 'Aprovado'
        enviar_notificacao(at.user_id, "Seu atestado foi APROVADO.", "/documentos/atestados/meus")
    else:
        at.status = 'Recusado'
        at.motivo_recusa = request.form.get('motivo_recusa')
        enviar_notificacao(at.user_id, "Seu atestado foi RECUSADO.", "/documentos/atestados/meus")
    db.session.commit(); flash('Avaliação concluída.', 'success')
    return redirect(url_for('documentos.gestao_atestados'))

# --- MÓDULO DE RELATÓRIO DE FOLHA (EXCEL) ---
@documentos_bp.route('/relatorio-folha')
@login_required
@permission_required('DOCUMENTOS')
def relatorio_folha():
    return render_template('documentos/relatorio_folha.html')

@documentos_bp.route('/relatorio-folha/exportar', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def exportar_relatorio_folha():
    data_inicio = datetime.strptime(request.form.get('data_inicio'), '%Y-%m-%d').date()
    data_fim = datetime.strptime(request.form.get('data_fim'), '%Y-%m-%d').date()
    usuarios = User.query.filter(User.username != 'terminal').all()
    dados = []
    for u in usuarios:
        pontos = PontoResumo.query.filter(PontoResumo.user_id == u.id, PontoResumo.data_referencia >= data_inicio, PontoResumo.data_referencia <= data_fim).all()
        esperado = sum(p.minutos_esperados for p in pontos)
        realizado = sum(p.minutos_trabalhados for p in pontos)
        dados.append({'Nome': u.real_name, 'CPF': u.cpf, 'Horas Esperadas': format_minutes_to_hm(esperado), 'Horas Realizadas': format_minutes_to_hm(realizado), 'Saldo': format_minutes_to_hm(realizado - esperado)})
    df = pd.DataFrame(dados)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name="relatorio_folha.xlsx")


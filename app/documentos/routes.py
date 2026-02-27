from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify, g, current_app
from flask_login import login_required, current_user
import io
import traceback
import threading

from app.extensions import db
from app.models import User, Holerite, Recibo, Atestado, AssinaturaDigital
from app.utils import get_brasil_time, permission_required, has_permission, get_client_ip, enviar_notificacao
from app.documentos.storage import baixar_bytes_storage, salvar_no_storage
from app.documentos.atestado_parser import analisar_atestado_vision

# --- IMPORTAÇÃO DOS NOVOS SERVICES E REPOSITORIES ---
from app.services.documento_service import DocumentoService
from app.repositories.documento_repository import (HoleriteRepository, ReciboRepository, 
                                                   AtestadoRepository, AssinaturaDigitalRepository)

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

# --- FUNÇÃO ASSÍNCRONA PARA A I.A. LER O ATESTADO EM SEGUNDO PLANO ---
def processar_atestado_background(app, atestado_id, file_bytes, real_name):
    """
    Esta função corre de forma invisível. Ela não prende o ecrã do funcionário.
    Usa o contexto da app para ter permissão de escrever no banco de dados.
    """
    with app.app_context():
        try:
            print(f"[BACKGROUND TASK] A iniciar IA para atestado {atestado_id}...")
            
            # Chama a IA super pesada (demora 3 a 10 segundos)
            dados_ia = analisar_atestado_vision(file_bytes, real_name)
            
            atestado_repo = AtestadoRepository()
            atestado = atestado_repo.get_by_id(atestado_id)
            
            if atestado:
                # Atualiza a base de dados com o que a IA descobriu
                atestado.data_inicio_afastamento = dados_ia.get('data_inicio')
                atestado.quantidade_dias = dados_ia.get('dias_afastamento')
                atestado.texto_extraido = dados_ia.get('texto_bruto')
                # Muda de "A Processar IA" para "Revisao" (pronto para o RH ver)
                atestado.status = 'Revisao'
                atestado_repo.commit()
                print(f"[BACKGROUND TASK] IA finalizada com sucesso. Atestado {atestado_id} atualizado.")
                
        except Exception as e:
            print(f"[BACKGROUND TASK] ERRO NA IA para atestado {atestado_id}: {e}")
            traceback.print_exc()

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
            historico.append({
                'id': h.id, 'doc_type': 'holerite', 'tipo': "Espelho de Ponto" if is_ponto else "Holerite", 
                'cor': 'purple' if is_ponto else 'blue', 'usuario': h.user.real_name if h.user else "N/A",
                'info': h.mes_referencia, 'data': h.enviado_em, 'visualizado': h.visualizado, 'rota': 'documentos.baixar_holerite'
            })

    if not f_tipo or f_tipo == 'Recibo':
        for r in recibos_db:
            historico.append({
                'id': r.id, 'doc_type': 'recibo', 'tipo': 'Recibo', 'cor': 'emerald',
                'usuario': r.user.real_name, 'info': f"R$ {r.valor:,.2f}",
                'data': r.created_at, 'visualizado': r.visualizado, 'rota': 'documentos.baixar_recibo'
            })

    historico.sort(key=lambda x: x['data'] if x['data'] else get_brasil_time(), reverse=True)
    return render_template('documentos/dashboard.html', historico=historico, pendentes_revisao=total_revisao, f_nome=f_nome, f_mes=f_mes, f_tipo=f_tipo)

@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def admin_holerites():
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        if not file: return redirect(request.url)
        try:
            doc_service = DocumentoService()
            sucesso, revisao = doc_service.processar_holerites_lote(file.read(), g.empresa.slug)
            flash(f"Processado: {sucesso} enviados, {revisao} para revisão manual.", "success")
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e:
            flash(f"Erro ao processar: {e}", "error")
    return render_template('documentos/admin_upload_holerite.html')

@documentos_bp.route('/admin/disparar-espelhos', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def disparar_espelhos():
    try:
        from app.services.ponto_service import PontoService
        ponto_service = PontoService()
        
        mes_ref = request.form.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
        
        if hasattr(ponto_service, 'gerar_espelhos_lote'):
            sucesso, msg = ponto_service.gerar_espelhos_lote(g.empresa_id, mes_ref)
            if sucesso:
                flash(f"Espelhos processados: {msg}", "success")
            else:
                flash(f"Atenção no processamento: {msg}", "warning")
        else:
            flash("A função de gerar espelhos em lote ainda não foi escrita no PontoService.", "warning")
            
    except Exception as e:
        traceback.print_exc()
        flash(f"Erro ao disparar espelhos: {str(e)}", "error")
        
    return redirect(url_for('documentos.dashboard_documentos'))

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['GET', 'POST'])
@login_required
def baixar_holerite(id):
    holerite_repo = HoleriteRepository()
    doc = holerite_repo.get_by_id(id)
    
    if not doc or (not has_permission('DOCUMENTOS') and doc.user_id != current_user.id):
        return redirect(url_for('main.dashboard'))
    
    arquivo_bytes = baixar_bytes_storage(doc.url_arquivo)
    if not arquivo_bytes:
        flash("Falha ao comunicar com a Nuvem.", "error")
        return redirect(url_for('documentos.dashboard_documentos'))

    if doc.user_id == current_user.id and not doc.visualizado:
        doc.visualizado = True
        holerite_repo.commit()
        
        doc_service = DocumentoService()
        tipo_doc = f"{'Espelho de Ponto' if 'espelhos' in doc.url_arquivo else 'Holerite'} - {doc.mes_referencia}"
        doc_service.registrar_assinatura(current_user.id, doc.id, tipo_doc, arquivo_bytes, get_client_ip(), request.headers.get('User-Agent', '')[:250])

    nome = f"ponto_{doc.mes_referencia}.pdf" if 'espelhos' in doc.url_arquivo else f"holerite_{doc.mes_referencia}.pdf"
    buffer = io.BytesIO(arquivo_bytes)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=nome)

@documentos_bp.route('/baixar/recibo/<int:id>', methods=['GET', 'POST'])
@login_required
def baixar_recibo(id):
    recibo_repo = ReciboRepository()
    doc = recibo_repo.get_by_id(id)
    
    if not doc or (not has_permission('DOCUMENTOS') and doc.user_id != current_user.id):
        return redirect(url_for('main.dashboard'))

    arquivo_bytes = baixar_bytes_storage(doc.url_arquivo)
    if not arquivo_bytes: return redirect(url_for('documentos.dashboard_documentos'))
        
    if doc.user_id == current_user.id and not doc.visualizado:
        doc.visualizado = True
        recibo_repo.commit()
        
        doc_service = DocumentoService()
        doc_service.registrar_assinatura(current_user.id, doc.id, f"Recibo - R$ {doc.valor}", arquivo_bytes, get_client_ip(), request.headers.get('User-Agent', '')[:250])

    buffer = io.BytesIO(arquivo_bytes)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=f"recibo_{id}.pdf")

@documentos_bp.route('/meus-documentos')
@login_required
def meus_documentos():
    h_repo, r_repo = HoleriteRepository(), ReciboRepository()
    holerites = h_repo.get_by_user(current_user.id)
    recibos = r_repo.get_by_user(current_user.id)
    
    docs = []
    for h in holerites:
        e_ponto = True if h.url_arquivo and 'espelhos' in h.url_arquivo else False
        docs.append({'id': h.id, 'tipo': 'Espelho' if e_ponto else 'Holerite', 'titulo': f"{'Ponto' if e_ponto else 'Holerite'} - {h.mes_referencia}", 'cor': 'purple' if e_ponto else 'blue', 'icone': 'fa-calendar' if e_ponto else 'fa-file', 'data': h.enviado_em, 'visto': h.visualizado, 'rota': 'documentos.baixar_holerite'})
    for r in recibos:
        docs.append({'id': r.id, 'tipo': 'Recibo', 'titulo': 'Recibo', 'cor': 'emerald', 'icone': 'fa-receipt', 'data': r.created_at, 'visto': r.visualizado, 'rota': 'documentos.baixar_recibo'})
    return render_template('documentos/meus_documentos.html', docs=docs)

# ==========================================================
# ENVIO RÁPIDO DE ATESTADO (BACKGROUND TASK)
# ==========================================================
@documentos_bp.route('/atestado/novo', methods=['GET', 'POST'])
@login_required
def enviar_atestado():
    if request.method == 'POST':
        file = request.files.get('arquivo_atestado')
        if not file or file.filename == '': return redirect(request.url)
        try:
            file_bytes = file.read()
            mes_ref = get_brasil_time().strftime('%Y-%m')
            
            # 1. Faz upload do ficheiro cru (Muito Rápido)
            caminho_blob = salvar_no_storage(file_bytes, f"atestados/{mes_ref}", g.empresa.slug)
            if not caminho_blob: return redirect(request.url)

            # 2. Guarda o atestado na BD sem processar a IA. Status inicial "Processando IA"
            atestado_repo = AtestadoRepository()
            novo_atestado = Atestado(
                user_id=current_user.id, 
                data_envio=get_brasil_time(), 
                url_arquivo=caminho_blob,
                status='A Processar IA' 
            )
            atestado_repo.add(novo_atestado)
            atestado_repo.commit()
            
            # 3. Dispara a Thread invisível para ler a imagem, e NÃO ESPERA por ela!
            app = current_app._get_current_object()
            threading.Thread(
                target=processar_atestado_background, 
                args=(app, novo_atestado.id, file_bytes, current_user.real_name)
            ).start()
            
            # 4. Dispara a notificação para o Chefe
            master = User.query.filter_by(username='50097952800').first()
            if master: enviar_notificacao(master.id, f"Novo Atestado de {current_user.real_name}.", "/documentos/admin/atestados")
            
            # 5. Ecrã livre para o funcionário! Menos de 1 segundo de espera.
            flash('O Atestado foi recebido pelo sistema e está a ser lido pela Inteligência Artificial!', 'success')
            return redirect(url_for('documentos.meus_atestados'))
            
        except Exception as e:
            print(f"[ERRO ATESTADO CRÍTICO]: {e}")
            flash('Erro ao enviar o atestado. Tente novamente.', 'error')
            
    return render_template('documentos/enviar_atestado.html')

@documentos_bp.route('/admin/atestados/<int:id>/avaliar', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def avaliar_atestado(id):
    atestado_repo = AtestadoRepository()
    atestado = atestado_repo.get_by_id(id)
    if not atestado: return redirect(url_for('documentos.gestao_atestados'))
    
    try:
        doc_service = DocumentoService()
        doc_service.avaliar_atestado(atestado, request.form.get('acao'), request.form)
        flash('Atestado avaliado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro: {e}', 'error')
    return redirect(url_for('documentos.gestao_atestados'))

@documentos_bp.route('/relatorio-folha/exportar', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def exportar_relatorio_folha():
    data_inicio = request.form.get('data_inicio')
    data_fim = request.form.get('data_fim')
    
    if not data_inicio or not data_fim:
        flash('Datas obrigatórias.', 'error')
        return redirect(url_for('documentos.relatorio_folha'))
        
    try:
        doc_service = DocumentoService()
        output = doc_service.gerar_relatorio_excel(data_inicio, data_fim)
        
        if not output:
            flash('Nenhum dado encontrado para as datas selecionadas.', 'warning')
            return redirect(url_for('documentos.relatorio_folha'))
            
        nome_arquivo = f"Fechamento_{data_inicio}_a_{data_fim}.xlsx"
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=nome_arquivo)
        
    except AttributeError as ae:
        traceback.print_exc()
        flash(f'Erro de formato nos dados do relatório. Contacte o suporte. Detalhe: {str(ae)}', 'error')
        return redirect(url_for('documentos.relatorio_folha'))
    except Exception as e:
        traceback.print_exc()
        flash(f'Erro ao processar dados matemáticos do fechamento. O erro original foi neutralizado. Detalhe: {str(e)}', 'error')
        return redirect(url_for('documentos.relatorio_folha'))

@documentos_bp.route('/admin/auditoria')
@login_required
@permission_required('DOCUMENTOS')
def auditoria_assinaturas():
    assinaturas = AssinaturaDigital.query.order_by(AssinaturaDigital.data_assinatura.desc()).all()
    return render_template('documentos/auditoria.html', assinaturas=assinaturas)

@documentos_bp.route('/admin/revisao', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def revisao_holerites():
    holerite_repo = HoleriteRepository()
    if request.method == 'POST':
        h_id = request.form.get('holerite_id')
        user_id = request.form.get('user_id')
        h = holerite_repo.get_by_id(h_id)
        if h and user_id:
            h.user_id = user_id
            h.status = 'Enviado'
            holerite_repo.commit()
            enviar_notificacao(user_id, "O seu documento revisado já está disponível para assinatura.", "/documentos/meus-documentos")
            flash('Documento associado ao colaborador com sucesso!', 'success')
        return redirect(url_for('documentos.revisao_holerites'))
        
    pendentes = holerite_repo.get_pendentes_revisao()
    usuarios = User.query.filter(User.role != 'Terminal', User.username != '50097952800').order_by(User.real_name).all()
    return render_template('documentos/revisao.html', pendentes=pendentes, usuarios=usuarios)

@documentos_bp.route('/admin/recibo/novo', methods=['GET', 'POST'])
@login_required
@permission_required('DOCUMENTOS')
def novo_recibo():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        valor = request.form.get('valor')
        data_pagamento = request.form.get('data_pagamento')
        arquivo = request.files.get('arquivo_pdf')
        
        if arquivo and arquivo.filename:
            file_bytes = arquivo.read()
            caminho = salvar_no_storage(file_bytes, f"recibos/{data_pagamento[:7]}", g.empresa.slug)
            if caminho:
                novo_r = Recibo(user_id=user_id, valor=float(valor), data_pagamento=data_pagamento, url_arquivo=caminho)
                db.session.add(novo_r)
                db.session.commit()
                enviar_notificacao(user_id, f"Novo Recibo de Pagamento disponível (R$ {valor}).", "/documentos/meus-documentos")
                flash("Recibo enviado com sucesso!", "success")
                return redirect(url_for('documentos.dashboard_documentos'))
        flash("Erro ao enviar o recibo. Verifique se o arquivo é válido.", "error")
            
    usuarios = User.query.filter(User.role != 'Terminal', User.username != '50097952800').order_by(User.real_name).all()
    return render_template('documentos/novo_recibo.html', usuarios=usuarios)

@documentos_bp.route('/atestado/baixar/<int:id>')
@login_required
def baixar_atestado(id):
    atestado_repo = AtestadoRepository()
    doc = atestado_repo.get_by_id(id)
    
    if not doc or (not has_permission('DOCUMENTOS') and doc.user_id != current_user.id):
        return redirect(url_for('main.dashboard'))
        
    arquivo_bytes = baixar_bytes_storage(doc.url_arquivo)
    if not arquivo_bytes:
        flash("Arquivo não encontrado na nuvem.", "error")
        return redirect(url_for('documentos.gestao_atestados'))
        
    buffer = io.BytesIO(arquivo_bytes)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=f"atestado_{id}.pdf")

@documentos_bp.route('/atestados/meus')
@login_required
def meus_atestados():
    atestado_repo = AtestadoRepository()
    atestados = atestado_repo.get_by_user(current_user.id)
    return render_template('documentos/meus_atestados.html', atestados=atestados)

@documentos_bp.route('/admin/atestados')
@login_required
@permission_required('DOCUMENTOS')
def gestao_atestados():
    atestados = Atestado.query.order_by(Atestado.data_envio.desc()).all()
    return render_template('documentos/gestao_atestados.html', atestados=atestados)

@documentos_bp.route('/relatorio-folha')
@login_required
@permission_required('DOCUMENTOS')
def relatorio_folha():
    return render_template('documentos/relatorio_folha.html')


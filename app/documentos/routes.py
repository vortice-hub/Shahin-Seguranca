from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo, AssinaturaDigital, Atestado, PontoResumo
from app.utils import get_brasil_time, permission_required, has_permission, limpar_nome, get_client_ip, calcular_hash_arquivo
from app.documentos.storage import salvar_no_storage, baixar_bytes_storage
from app.documentos.ai_parser import extrair_dados_holerite
from app.documentos.utils import gerar_pdf_recibo, gerar_pdf_espelho_mensal, gerar_certificado_entrega
from app.documentos.atestado_parser import analisar_atestado_vision
from datetime import datetime, timedelta
from pypdf import PdfReader, PdfWriter
from thefuzz import process, fuzz
import io

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
            is_ponto = True if h.conteudo_pdf else False
            if f_tipo == 'Holerite' and is_ponto: continue
            if f_tipo == 'Espelho' and not is_ponto: continue
            
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

@documentos_bp.route('/excluir/<doc_type>/<int:id>', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def excluir_documento(doc_type, id):
    try:
        if doc_type == 'holerite':
            item = Holerite.query.get_or_404(id)
            db.session.delete(item)
        elif doc_type == 'recibo':
            item = Recibo.query.get_or_404(id)
            db.session.delete(item)
        db.session.commit()
        flash("Documento removido com sucesso.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao excluir: {e}", "error")
    return redirect(url_for('documentos.dashboard_documentos'))

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
            flash(f"Processado: {sucesso} enviados, {revisao} para revisão manual.", "success")
            return redirect(url_for('documentos.dashboard_documentos'))
        except Exception as e:
            db.session.rollback(); flash(f"Erro: {e}", "error")
    return render_template('documentos/admin_upload_holerite.html')

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if not has_permission('DOCUMENTOS') and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
    
    arquivo_bytes = None
    nome_download = "documento.pdf"
    
    if doc.conteudo_pdf:
        arquivo_bytes = doc.conteudo_pdf
        nome_download = f"ponto_{doc.mes_referencia}.pdf"
    elif doc.url_arquivo:
        arquivo_bytes = baixar_bytes_storage(doc.url_arquivo)
        nome_download = f"holerite_{doc.mes_referencia}.pdf"
        
    if not arquivo_bytes:
        flash("Erro ao baixar o arquivo. Arquivo não encontrado no servidor.", "error")
        return redirect(url_for('documentos.dashboard_documentos'))

    if doc.user_id == current_user.id and not doc.visualizado:
        doc.visualizado = True
        tipo_doc = "Espelho de Ponto" if doc.conteudo_pdf else "Holerite"
        
        user_agent_info = request.headers.get('User-Agent')
        if user_agent_info:
            user_agent_info = user_agent_info[:250]
        else:
            user_agent_info = 'Desconhecido'

        assinatura = AssinaturaDigital(
            user_id=current_user.id,
            documento_id=doc.id,
            tipo_documento=f"{tipo_doc} - {doc.mes_referencia}",
            hash_arquivo=calcular_hash_arquivo(arquivo_bytes),
            data_assinatura=get_brasil_time(),
            ip_address=get_client_ip(),
            user_agent=user_agent_info
        )
        db.session.add(assinatura)
        db.session.commit()

    return send_file(io.BytesIO(arquivo_bytes), mimetype='application/pdf', as_attachment=True, download_name=nome_download)

@documentos_bp.route('/baixar/recibo/<int:id>', methods=['POST'])
@login_required
def baixar_recibo(id):
    doc = Recibo.query.get_or_404(id)
    if not has_permission('DOCUMENTOS') and doc.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
        
    arquivo_bytes = doc.conteudo_pdf
    if not arquivo_bytes:
        flash("Erro: Recibo vazio.", "error")
        return redirect(url_for('documentos.dashboard_documentos'))
        
    if doc.user_id == current_user.id and not doc.visualizado:
        doc.visualizado = True
        
        user_agent_info = request.headers.get('User-Agent')
        if user_agent_info:
            user_agent_info = user_agent_info[:250]
        else:
            user_agent_info = 'Desconhecido'

        assinatura = AssinaturaDigital(
            user_id=current_user.id,
            documento_id=doc.id,
            tipo_documento=f"Recibo - R$ {doc.valor}",
            hash_arquivo=calcular_hash_arquivo(arquivo_bytes),
            data_assinatura=get_brasil_time(),
            ip_address=get_client_ip(),
            user_agent=user_agent_info
        )
        db.session.add(assinatura)
        db.session.commit()

    return send_file(io.BytesIO(arquivo_bytes), mimetype='application/pdf', as_attachment=True, download_name=f"recibo_{id}.pdf")

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

@documentos_bp.route('/admin/auditoria/certificado/<int:id>')
@login_required
@permission_required('AUDITORIA')
def baixar_certificado_auditoria(id):
    assinatura = AssinaturaDigital.query.get_or_404(id)
    usuario = User.query.get(assinatura.user_id)
    
    if not usuario:
        flash("Usuário vinculado à assinatura não encontrado.", "error")
        return redirect(url_for('documentos.revisao_auditoria'))

    # CORREÇÃO DO ERRO DO CERTIFICADO:
    # O script de geração de PDF espera o atributo "nome", então nós o adicionamos temporariamente.
    usuario.nome = usuario.real_name

    try:
        pdf_bytes = gerar_certificado_entrega(assinatura, usuario)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"Auditoria_{usuario.real_name}_{assinatura.id}.pdf"
        )
    except Exception as e:
        print(f"Erro ao gerar certificado de auditoria: {e}")
        flash("Erro interno ao gerar o documento de auditoria. Verifique os logs.", "error")
        return redirect(url_for('documentos.revisao_auditoria'))

@documentos_bp.route('/atestado/novo', methods=['GET', 'POST'])
@login_required
def enviar_atestado():
    if request.method == 'POST':
        file = request.files.get('arquivo_atestado')
        if not file or file.filename == '':
            flash('Nenhum arquivo selecionado.', 'error')
            return redirect(request.url)
        
        try:
            file_bytes = file.read()
            mes_ref = get_brasil_time().strftime('%Y-%m')
            
            caminho_blob = salvar_no_storage(file_bytes, f"atestado_{mes_ref}")
            if not caminho_blob:
                flash('Erro ao salvar o arquivo no servidor.', 'error')
                return redirect(request.url)

            dados_ia = analisar_atestado_vision(file_bytes, current_user.real_name)
            
            data_inicio_db = None
            if dados_ia['data_inicio']:
                data_inicio_db = datetime.strptime(dados_ia['data_inicio'], '%Y-%m-%d').date()

            novo_atestado = Atestado(
                user_id=current_user.id,
                data_envio=get_brasil_time(),
                url_arquivo=caminho_blob,
                data_inicio_afastamento=data_inicio_db,
                quantidade_dias=dados_ia['dias_afastamento'],
                texto_extraido=dados_ia['texto_bruto'],
                status='Revisao' 
            )
            db.session.add(novo_atestado)
            db.session.commit()
            
            flash('Atestado enviado com sucesso! O RH fará a análise em breve.', 'success')
            return redirect(url_for('documentos.meus_documentos'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Erro no envio de atestado: {e}")
            flash('Ocorreu um erro ao processar seu atestado.', 'error')
            return redirect(request.url)

    return render_template('documentos/enviar_atestado.html')

@documentos_bp.route('/admin/atestados')
@login_required
@permission_required('DOCUMENTOS')
def gestao_atestados():
    """Painel do Master para revisar atestados enviados."""
    atestados = Atestado.query.order_by(Atestado.data_envio.desc()).all()
    return render_template('documentos/gestao_atestados.html', atestados=atestados)

@documentos_bp.route('/atestado/baixar/<int:id>')
@login_required
def baixar_atestado(id):
    """Rota para abrir a foto ou PDF do atestado no navegador."""
    atestado = Atestado.query.get_or_404(id)
    if not has_permission('DOCUMENTOS') and atestado.user_id != current_user.id:
        flash("Acesso negado.", "error")
        return redirect(url_for('main.dashboard'))
    
    if atestado.url_arquivo:
        arquivo_bytes = baixar_bytes_storage(atestado.url_arquivo)
        if arquivo_bytes:
            ext = 'pdf' if 'pdf' in atestado.url_arquivo.lower() else 'jpeg'
            mimetype = 'application/pdf' if ext == 'pdf' else f'image/{ext}'
            return send_file(io.BytesIO(arquivo_bytes), mimetype=mimetype, as_attachment=False, download_name=f"atestado_{id}.{ext}")
    
    flash("Arquivo não encontrado no servidor.", "error")
    return redirect(request.referrer or url_for('main.dashboard'))

@documentos_bp.route('/admin/atestados/<int:id>/avaliar', methods=['POST'])
@login_required
@permission_required('DOCUMENTOS')
def avaliar_atestado(id):
    """Aprova ou Recusa um atestado e desconta as horas automaticamente."""
    atestado = Atestado.query.get_or_404(id)
    acao = request.form.get('acao')
    
    try:
        if acao == 'aprovar':
            atestado.status = 'Aprovado'
            
            # MÁGICA: Abater horas no PontoResumo
            if atestado.data_inicio_afastamento and atestado.quantidade_dias:
                for i in range(atestado.quantidade_dias):
                    dia_atual = atestado.data_inicio_afastamento + timedelta(days=i)
                    ponto = PontoResumo.query.filter_by(user_id=atestado.user_id, data_referencia=dia_atual).first()
                    
                    if ponto:
                        ponto.status_dia = 'Atestado'
                        ponto.minutos_esperados = 0
                        ponto.minutos_saldo = ponto.minutos_trabalhados - ponto.minutos_esperados
                    else:
                        # Se o dia ainda não existe no Ponto, cria zerado
                        novo_ponto = PontoResumo(
                            user_id=atestado.user_id,
                            data_referencia=dia_atual,
                            minutos_trabalhados=0,
                            minutos_esperados=0,
                            minutos_saldo=0,
                            status_dia='Atestado'
                        )
                        db.session.add(novo_ponto)
                        
        elif acao == 'recusar':
            atestado.status = 'Recusado'
            atestado.motivo_recusa = request.form.get('motivo_recusa', 'Recusado pelo RH')
        
        db.session.commit()
        flash(f'Atestado {atestado.status} com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao avaliar atestado: {e}', 'error')
        
    return redirect(url_for('documentos.gestao_atestados'))


from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time, remove_accents
import cloudinary
import cloudinary.uploader
import io
import logging
import requests
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

holerite_bp = Blueprint('holerite', __name__, url_prefix='/holerites')

try:
    if not cloudinary.config().cloud_name:
        cloudinary.config(
            cloud_name = "dxb4fbdjy",
            api_key = "537342766187832",
            api_secret = "cbINpCjQtRh7oKp-uVX2YPdOKaI"
        )
except: pass

def encontrar_usuario_por_nome(texto_pagina):
    texto_limpo = remove_accents(texto_pagina).upper()
    users = User.query.all()
    candidatos = []
    for user in users:
        nome_user_limpo = remove_accents(user.real_name).upper().strip()
        if len(nome_user_limpo.split()) > 1 and nome_user_limpo in texto_limpo:
            candidatos.append(user)
    if len(candidatos) == 1: return candidatos[0]
    return None

@holerite_bp.route('/admin/importar', methods=['GET', 'POST'])
@login_required
def admin_importar():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        if request.form.get('acao') == 'limpar_tudo':
            try:
                Holerite.query.delete()
                db.session.commit()
                flash('Limpeza concluída.')
            except Exception as e:
                db.session.rollback()
                flash(f'Erro: {e}')
            return redirect(url_for('holerite.admin_importar'))

        file = request.files.get('arquivo_pdf')
        mes_ref = request.form.get('mes_ref')
        
        if not file: return redirect(url_for('holerite.admin_importar'))
            
        try:
            reader = PdfReader(file)
            sucesso = 0
            
            for i, page in enumerate(reader.pages):
                texto = page.extract_text()
                user = encontrar_usuario_por_nome(texto)
                
                if user:
                    writer = PdfWriter()
                    writer.add_page(page)
                    output_stream = io.BytesIO()
                    writer.write(output_stream)
                    output_stream.seek(0)
                    
                    filename = f"holerite_{user.id}_{mes_ref}_{int(get_brasil_time().timestamp())}"
                    
                    # Upload como AUTO (Deixa o Cloudinary decidir o melhor jeito)
                    upload_result = cloudinary.uploader.upload(
                        output_stream, 
                        public_id=filename, 
                        resource_type="auto", 
                        folder="holerites_v53"
                    )
                    
                    url_pdf = upload_result.get('secure_url')
                    pid = upload_result.get('public_id')
                    
                    existente = Holerite.query.filter_by(user_id=user.id, mes_referencia=mes_ref).first()
                    if existente:
                        existente.url_arquivo = url_pdf
                        existente.public_id = pid
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False
                    else:
                        novo = Holerite(user_id=user.id, mes_referencia=mes_ref, url_arquivo=url_pdf, public_id=pid)
                        db.session.add(novo)
                    
                    sucesso += 1
            
            db.session.commit()
            flash(f'Sucesso: {sucesso} holerites enviados.')
            
        except Exception as e:
            logger.error(f"ERRO UPLOAD: {e}")
            db.session.rollback()
            flash(f'Erro: {str(e)}')

    ultimos = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    return render_template('admin_upload_holerite.html', uploads=ultimos)

@holerite_bp.route('/meus-documentos')
@login_required
def meus_holerites():
    docs = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.mes_referencia.desc()).all()
    return render_template('meus_holerites.html', holerites=docs)

# --- ROTA DE DOWNLOAD (PROXY) ---
@holerite_bp.route('/baixar/<int:id>', methods=['GET', 'POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if doc.user_id != current_user.id: 
        flash("Acesso negado.")
        return redirect(url_for('main.dashboard'))
    
    # Registra visualização
    if not doc.visualizado:
        doc.visualizado = True
        doc.visualizado_em = get_brasil_time()
        db.session.commit()
        
    try:
        # O PULO DO GATO: O servidor baixa o arquivo do Cloudinary
        response = requests.get(doc.url_arquivo)
        
        if response.status_code == 200:
            # Cria um arquivo na memória para entregar ao usuário
            arquivo_memoria = io.BytesIO(response.content)
            
            # Define o nome do arquivo para download
            nome_download = f"Holerite_{doc.mes_referencia}.pdf"
            
            return send_file(
                arquivo_memoria,
                mimetype='application/pdf',
                as_attachment=True, # Força o download
                download_name=nome_download
            )
        else:
            flash(f"Erro ao buscar arquivo na nuvem (Status {response.status_code}). Tente novamente.")
            return redirect(url_for('holerite.meus_holerites'))
            
    except Exception as e:
        logger.error(f"Erro Proxy Download: {e}")
        flash("Erro ao baixar documento. Contate o RH.")
        return redirect(url_for('holerite.meus_holerites'))
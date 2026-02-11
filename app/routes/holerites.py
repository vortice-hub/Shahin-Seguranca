from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time, remove_accents
import cloudinary
import cloudinary.uploader
import re
import io
from pypdf import PdfReader, PdfWriter

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
    # Normaliza o texto da pagina (Maiusculo, sem acento)
    texto_limpo = remove_accents(texto_pagina).upper()
    
    # Busca usuarios ativos
    users = User.query.all()
    
    candidatos = []
    
    for user in users:
        # Normaliza nome do usuario
        nome_user_limpo = remove_accents(user.real_name).upper().strip()
        
        # Verifica se o nome completo esta contido no texto da pagina
        if nome_user_limpo in texto_limpo:
            candidatos.append(user)
            
    # Se achou exatamente 1, retorna ele. Se achou 0 ou mais de 1 (homonimos), retorna None por seguranca.
    if len(candidatos) == 1:
        return candidatos[0]
    return None

@holerite_bp.route('/admin/importar', methods=['GET', 'POST'])
@login_required
def admin_importar():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        mes_ref = request.form.get('mes_ref')
        
        if not file or not mes_ref:
            flash('Selecione arquivo e mês.')
            return redirect(url_for('holerite.admin_importar'))
            
        try:
            reader = PdfReader(file)
            sucesso = 0
            falha = 0
            
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
                    
                    upload = cloudinary.uploader.upload(
                        output_stream, 
                        public_id=filename, 
                        resource_type="auto",
                        folder="holerites_shahin"
                    )
                    
                    url = upload.get('secure_url')
                    pid = upload.get('public_id')
                    
                    existente = Holerite.query.filter_by(user_id=user.id, mes_referencia=mes_ref).first()
                    if existente:
                        existente.url_arquivo = url
                        existente.public_id = pid
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False
                    else:
                        novo = Holerite(user_id=user.id, mes_referencia=mes_ref, url_arquivo=url, public_id=pid)
                        db.session.add(novo)
                    
                    sucesso += 1
                else:
                    falha += 1
            
            db.session.commit()
            flash(f'Processado: {sucesso} identificados por NOME. {falha} páginas não identificadas/ambíguas.')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {str(e)}')
            
    return render_template('admin_upload_holerite.html')

@holerite_bp.route('/meus-documentos')
@login_required
def meus_holerites():
    docs = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.mes_referencia.desc()).all()
    return render_template('meus_holerites.html', holerites=docs)

@holerite_bp.route('/confirmar-recebimento/<int:id>', methods=['POST'])
@login_required
def confirmar_recebimento(id):
    doc = Holerite.query.get_or_404(id)
    if doc.user_id != current_user.id: return redirect(url_for('main.dashboard'))
    if not doc.visualizado:
        doc.visualizado = True
        doc.visualizado_em = get_brasil_time()
        db.session.commit()
        flash('Recebimento confirmado.')
    return redirect(doc.url_arquivo)
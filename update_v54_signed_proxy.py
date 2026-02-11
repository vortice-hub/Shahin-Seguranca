import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V54: Fix Holerite 401 - Geracao de URL Assinada para Download Seguro"

# --- APP/ROUTES/HOLERITES.PY (Download com Assinatura) ---
FILE_BP_HOLERITES = """
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time, remove_accents
import cloudinary
import cloudinary.uploader
import cloudinary.utils
import io
import logging
import requests
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

holerite_bp = Blueprint('holerite', __name__, url_prefix='/holerites')

# Configuração (Sempre garantindo as credenciais)
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
                    
                    filename = f"holerite_{user.id}_{mes_ref}_{int(get_brasil_time().timestamp())}.pdf"
                    
                    # Upload RAW com type='upload' (Tenta forçar publico, mas a leitura usará assinatura)
                    upload_result = cloudinary.uploader.upload(
                        output_stream, 
                        public_id=filename, 
                        resource_type="raw", 
                        folder="holerites_v54",
                        type="upload" 
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

# --- DOWNLOAD BLINDADO (URL ASSINADA) ---
@holerite_bp.route('/baixar/<int:id>', methods=['POST'])
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
        # TENTATIVA 1: Gerar URL Assinada como RAW
        # O sign_url=True usa a API Secret para criar um token de acesso temporário
        signed_url, options = cloudinary.utils.cloudinary_url(
            doc.public_id, 
            resource_type="raw", 
            sign_url=True
        )
        
        logger.info(f"Tentando baixar RAW assinado: {signed_url}")
        response = requests.get(signed_url)
        
        # TENTATIVA 2: Se der 404/401, tenta como IMAGE (as vezes o Cloudinary classifica PDF como imagem)
        if response.status_code != 200:
            logger.warning(f"Falha RAW ({response.status_code}). Tentando como IMAGE...")
            signed_url_img, opts = cloudinary.utils.cloudinary_url(
                doc.public_id, 
                resource_type="image", 
                sign_url=True
            )
            response = requests.get(signed_url_img)

        # Se funcionou algum dos dois
        if response.status_code == 200:
            arquivo_memoria = io.BytesIO(response.content)
            nome_download = f"Holerite_{doc.mes_referencia}.pdf"
            
            return send_file(
                arquivo_memoria,
                mimetype='application/pdf',
                as_attachment=True, 
                download_name=nome_download
            )
        else:
            # Falhou tudo
            logger.error(f"Erro Final Cloudinary: {response.status_code} - {response.text}")
            flash(f"Erro ao recuperar arquivo (Erro {response.status_code}). Contate o Suporte.")
            return redirect(url_for('holerite.meus_holerites'))
            
    except Exception as e:
        logger.error(f"Exceção Download: {e}")
        flash("Erro interno ao baixar documento.")
        return redirect(url_for('holerite.meus_holerites'))
"""

# --- FUNÇÕES ---
def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())
    print(f"Atualizado: {path}")

def git_update():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO V54! URL ASSINADA <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V54 SIGNED PROXY: {PROJECT_NAME} ---")
    write_file("app/routes/holerites.py", FILE_BP_HOLERITES)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



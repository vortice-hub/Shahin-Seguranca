import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V50: Debug Mode - Correcao URL Cloudinary (Raw) e Logs Detalhados"

# --- APP/ROUTES/HOLERITES.PY (Blindado e Tagarela) ---
FILE_BP_HOLERITES = """
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time, remove_accents
import cloudinary
import cloudinary.uploader
import io
import logging
from pypdf import PdfReader, PdfWriter

# Logger para ver no Render
logger = logging.getLogger(__name__)

holerite_bp = Blueprint('holerite', __name__, url_prefix='/holerites')

# Configuraçao Explicita
cloudinary.config(
    cloud_name = "dxb4fbdjy",
    api_key = "537342766187832",
    api_secret = "cbINpCjQtRh7oKp-uVX2YPdOKaI"
)

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
        # Limpeza
        if request.form.get('acao') == 'limpar_tudo':
            Holerite.query.delete()
            db.session.commit()
            flash('Limpeza concluída.')
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
                    # Prepara PDF individual
                    writer = PdfWriter()
                    writer.add_page(page)
                    output_stream = io.BytesIO()
                    writer.write(output_stream)
                    output_stream.seek(0)
                    
                    # --- CORREÇÃO CRITICA V50 ---
                    # 1. Nome do arquivo PRECISA ter .pdf no final para resource_type='raw'
                    filename = f"holerite_{user.id}_{mes_ref}_{int(get_brasil_time().timestamp())}.pdf"
                    
                    logger.info(f"Iniciando upload para: {user.real_name} - Arquivo: {filename}")
                    
                    # 2. Upload forçado como RAW (Arquivo bruto)
                    upload_result = cloudinary.uploader.upload(
                        output_stream, 
                        public_id=filename, 
                        resource_type="raw", # Obriga ser Raw
                        folder="holerites_v50", # Pasta nova para não misturar com erros antigos
                        format="pdf"
                    )
                    
                    logger.info(f"Resposta Cloudinary: {upload_result}")
                    
                    url_pdf = upload_result.get('secure_url')
                    pid = upload.get('public_id')
                    
                    # Salva no banco
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
            flash(f'Sucesso: {sucesso} holerites processados e enviados.')
            
        except Exception as e:
            logger.error(f"ERRO NO UPLOAD: {e}")
            db.session.rollback()
            flash(f'Erro no upload: {str(e)}')

    ultimos = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    return render_template('admin_upload_holerite.html', uploads=ultimos)

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
        
    # LOG PARA DEBUG
    logger.info(f"Redirecionando usuario {current_user.real_name} para {doc.url_arquivo}")
    
    return redirect(doc.url_arquivo)
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
        print("\n>>> SUCESSO V50! LOGS ATIVADOS E UPLOAD CORRIGIDO <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V50 DEBUG: {PROJECT_NAME} ---")
    write_file("app/routes/holerites.py", FILE_BP_HOLERITES)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



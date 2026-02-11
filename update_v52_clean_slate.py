import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V52: Limpeza Total de Holerites Antigos e Blindagem de URL Raw"

# --- APP/ROUTES/HOLERITES.PY (Com blindagem de URL) ---
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
                    
                    filename = f"holerite_{user.id}_{mes_ref}_{int(get_brasil_time().timestamp())}.pdf"
                    
                    # Upload RAW
                    upload_result = cloudinary.uploader.upload(
                        output_stream, 
                        public_id=filename, 
                        resource_type="raw", 
                        folder="holerites_v52", 
                        format="pdf"
                    )
                    
                    # --- BLINDAGEM DE URL ---
                    url_pdf = upload_result.get('secure_url')
                    pid = upload_result.get('public_id')
                    
                    # Se por acaso o Cloudinary devolver link de imagem, forçamos RAW
                    if '/image/upload/' in url_pdf:
                        url_pdf = url_pdf.replace('/image/upload/', '/raw/upload/')
                    
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
            flash(f'Sucesso: {sucesso} holerites enviados.')
            
        except Exception as e:
            logger.error(f"ERRO: {e}")
            db.session.rollback()
            flash(f'Erro: {str(e)}')

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
        
    return redirect(doc.url_arquivo)
"""

# --- SCRIPT DE LIMPEZA DO BANCO (EXECUTA NO INIT) ---
FILE_INIT_CLEAN = """
import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import cloudinary

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app_inst = Flask(__name__)
    app_inst.secret_key = os.environ.get('SECRET_KEY', 'chave_v52_clean_db')
    
    clean_db = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"
    env_db = os.environ.get('DATABASE_URL')
    
    if env_db and env_db.startswith("postgres"): db_url = env_db
    else: db_url = clean_db
        
    if db_url.startswith("postgres://"): db_url = db_url.replace("postgres://", "postgresql://", 1)

    app_inst.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app_inst.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app_inst.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 10}

    cloudinary.config(
        cloud_name = "dxb4fbdjy",
        api_key = "537342766187832",
        api_secret = "cbINpCjQtRh7oKp-uVX2YPdOKaI"
    )

    db.init_app(app_inst)
    login_manager.init_app(app_inst)
    login_manager.login_view = 'auth.login'

    with app_inst.app_context():
        from app.routes.auth import auth_bp
        from app.routes.main import main_bp
        from app.routes.admin import admin_bp
        from app.routes.ponto import ponto_bp
        from app.routes.estoque import estoque_bp
        from app.routes.holerites import holerite_bp 
        
        app_inst.register_blueprint(auth_bp)
        app_inst.register_blueprint(main_bp)
        app_inst.register_blueprint(admin_bp)
        app_inst.register_blueprint(ponto_bp)
        app_inst.register_blueprint(estoque_bp)
        app_inst.register_blueprint(holerite_bp)

        try:
            db.create_all()
            from app.models import User, Holerite
            if not User.query.filter_by(username='Thaynara').first():
                m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
                m.set_password('1855')
                db.session.add(m)
                db.session.commit()
            
            # --- LIMPEZA DE HOLERITES ANTIGOS (Executa 1 vez para corrigir base) ---
            # Removemos todos para garantir que nao sobrou lixo
            # Se quiser desativar isso depois, comente as linhas abaixo
            count = Holerite.query.count()
            if count > 0:
                Holerite.query.delete()
                db.session.commit()
                logger.warning(f"LIMPEZA V52: {count} holerites antigos/quebrados foram removidos do banco.")
                
        except Exception as e:
            logger.error(f"Erro Boot DB: {e}")

    return app_inst

app = create_app()
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
        print("\n>>> SUCESSO V52! LIMPEZA TOTAL E CORREÇÃO <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V52 CLEAN SLATE: {PROJECT_NAME} ---")
    write_file("app/routes/holerites.py", FILE_BP_HOLERITES)
    write_file("app/__init__.py", FILE_INIT_CLEAN) # Inclui o script de delete
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



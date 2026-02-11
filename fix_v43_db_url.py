import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V43: Fix Critical - Cleaning Neon DB URL (Removing psql command wrapper)"

# --- 1. app/__init__.py (Com URL Limpa e Segura) ---
FILE_INIT = """
import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instancias globais
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app_inst = Flask(__name__)
    app_inst.secret_key = os.environ.get('SECRET_KEY', 'chave_v43_final_db_fix')
    
    # --- CONFIGURAÇÃO DO BANCO DE DADOS ---
    
    # 1. URL Limpa (Extraida do seu comando psql)
    # Removemos o 'psql' e as aspas, e mantemos apenas o sslmode=require para compatibilidade máxima
    clean_db_url = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"
    
    # 2. Tenta pegar do Ambiente do Render (caso você tenha configurado lá)
    env_db = os.environ.get('DATABASE_URL')
    
    # 3. Lógica de Decisão
    # Se a variável do Render existir E começar com postgres, usa ela. Senão, usa a hardcoded.
    if env_db and env_db.startswith("postgres"):
        db_url = env_db
    else:
        db_url = clean_db_url
        
    # 4. Correção de Protocolo (Obrigatório para SQLAlchemy novo)
    # Transforma postgres:// em postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    # Log de Debug (Para sabermos o que está acontecendo nos logs do Render)
    logger.info(f"Tentando conectar com URL iniciada em: {db_url[:20]}...")

    app_inst.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app_inst.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Configurações do Pool de Conexão (Evita quedas)
    app_inst.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10
    }

    # Inicializa Extensions
    db.init_app(app_inst)
    login_manager.init_app(app_inst)
    login_manager.login_view = 'auth.login'

    # Registra Blueprints
    with app_inst.app_context():
        from app.routes.auth import auth_bp
        from app.routes.main import main_bp
        from app.routes.admin import admin_bp
        from app.routes.ponto import ponto_bp
        from app.routes.estoque import estoque_bp
        
        app_inst.register_blueprint(auth_bp)
        app_inst.register_blueprint(main_bp)
        app_inst.register_blueprint(admin_bp)
        app_inst.register_blueprint(ponto_bp)
        app_inst.register_blueprint(estoque_bp)

        # Criação de Tabelas
        try:
            db.create_all()
            # Verifica Master
            from app.models import User
            if not User.query.filter_by(username='Thaynara').first():
                m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
                m.set_password('1855')
                db.session.add(m)
                db.session.commit()
        except Exception as e:
            logger.error(f"Erro no Boot do Banco: {e}")

    return app_inst

# Instância Global para o Gunicorn
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
        print("\n>>> SUCESSO V43! URL DO BANCO CORRIGIDA <<<")
    except Exception as e:
        print(f"Erro Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- FIX V43 DB URL: {PROJECT_NAME} ---")
    
    # Atualiza apenas o init onde fica a conexao
    write_file("app/__init__.py", FILE_INIT)
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



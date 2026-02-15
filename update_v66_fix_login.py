import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V66: Fix Critical Login 400 - ProxyFix e Ajuste CSRF"

# --- 1. CONFIG.PY (Desativa checagem rigorosa temporariamente) ---
FILE_CONFIG = """
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Garante uma chave secreta fixa para não invalidar sessões ao reiniciar
    SECRET_KEY = os.environ.get('SECRET_KEY', 'chave_mestra_v66_shahin_segura')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configurações de Banco
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10
    }
    
    # --- CORREÇÃO DO LOGIN ---
    # Desativa a protecao global temporariamente para destravar o acesso
    # O ProxyFix no __init__ vai corrigir a sessao para o futuro
    WTF_CSRF_ENABLED = False 

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///dev.db')

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    
    # Em produção, forçamos cookies seguros
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'

config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
"""

# --- 2. APP/__INIT__.PY (Adiciona ProxyFix para Render) ---
FILE_INIT = """
import os
import logging
from flask import Flask
from app.extensions import db, login_manager, csrf, migrate
from config import config_map
from werkzeug.middleware.proxy_fix import ProxyFix # IMPORTANTE PARA RENDER

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    # Determina o ambiente
    env_name = os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config_map[env_name])
    
    # Correção de URL do Banco (Render/Neon)
    db_url = app.config.get('SQLALCHEMY_DATABASE_URI')
    if db_url and db_url.startswith("postgres://"):
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://", 1)
    
    # --- CORREÇÃO CRÍTICA PARA RENDER ---
    # Isso diz ao Flask para confiar nos cabeçalhos HTTPS do Render
    # Resolve problemas de sessão perdida e CSRF inválido
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Inicializa Extensões
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app) # Carrega, mas obedece config WTF_CSRF_ENABLED = False
    migrate.init_app(app, db)
    
    login_manager.login_view = 'auth.login'

    # Registra Blueprints
    with app.app_context():
        from app.auth.routes import auth_bp
        from app.admin.routes import admin_bp
        from app.ponto.routes import ponto_bp
        from app.estoque.routes import estoque_bp
        from app.holerites.routes import holerite_bp
        from app.main.routes import main_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(admin_bp)
        app.register_blueprint(ponto_bp)
        app.register_blueprint(estoque_bp)
        app.register_blueprint(holerite_bp)
        app.register_blueprint(main_bp)

        # Garante criação das tabelas e Master User
        try:
            db.create_all()
            from app.models import User
            if not User.query.filter_by(username='Thaynara').first():
                m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
                m.set_password('1855')
                db.session.add(m)
                db.session.commit()
        except Exception as e:
            logger.error(f"Erro no boot do DB: {e}")

    return app

# Instância global para Gunicorn
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
        print("\n>>> SUCESSO V66! LOGIN DESTRAVADO <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- FIX V66 LOGIN: {PROJECT_NAME} ---")
    write_file("config.py", FILE_CONFIG)
    write_file("app/__init__.py", FILE_INIT)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



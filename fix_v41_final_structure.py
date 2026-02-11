import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V41: Fix Final - Conexao Banco Blindada e Estrutura de Boot Robusta"

# --- 1. app/__init__.py (O Coração do Sistema) ---
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
    app_inst.secret_key = os.environ.get('SECRET_KEY', 'chave_v41_segura_final')
    
    # --- CONFIGURAÇÃO BLINDADA DO BANCO DE DADOS ---
    # 1. URL Padrão (Fallback Seguro)
    default_db = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"
    
    # 2. Tenta pegar do Render
    env_db = os.environ.get('DATABASE_URL')
    
    # 3. Lógica de Seleção
    if env_db and len(env_db.strip()) > 0:
        db_url = env_db.strip()
    else:
        db_url = default_db
        
    # 4. Correção para SQLAlchemy (postgres:// -> postgresql://)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    # Debug (Mostra no log se pegou a URL certa, escondendo a senha)
    try:
        masked = db_url.split('@')[1] if '@' in db_url else 'LOCAL/INVALID'
        logger.info(f"Iniciando conexao com Banco: ...@{masked}")
    except:
        logger.info("Iniciando conexao com Banco (URL mascarada falhou)")

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

    # Registra Blueprints (Rotas)
    with app_inst.app_context():
        # Importação dentro do contexto para evitar ciclo
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

        # Criação de Tabelas e Master User (Segurança)
        try:
            db.create_all()
            from app.models import User
            if not User.query.filter_by(username='Thaynara').first():
                m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
                m.set_password('1855')
                db.session.add(m)
                db.session.commit()
                logger.info("Usuario Master verificado/criado.")
        except Exception as e:
            logger.error(f"Erro no boot do banco: {e}")

    return app_inst

# --- INSTANCIA GLOBAL ---
# Isso permite que o Gunicorn encontre 'app' se procurar neste arquivo
app = create_app()
"""

# --- 2. run.py (O Gatilho Correto) ---
FILE_RUN = """
from app import create_app

# Cria a aplicação usando a fábrica
app = create_app()

if __name__ == "__main__":
    # Roda localmente
    app.run(debug=True)
"""

# --- 3. Procfile (Comando de Inicialização) ---
# Força o uso do run:app que é o padrão correto para essa estrutura
FILE_PROCFILE = """web: gunicorn run:app"""

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
        print("\n>>> SUCESSO V41! CORREÇÃO FINAL ENVIADA <<<")
    except Exception as e:
        print(f"Erro Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- FIX V41 FINAL: {PROJECT_NAME} ---")
    
    # Reescreve arquivos vitais
    write_file("app/__init__.py", FILE_INIT)
    write_file("run.py", FILE_RUN)
    write_file("Procfile", FILE_PROCFILE)
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



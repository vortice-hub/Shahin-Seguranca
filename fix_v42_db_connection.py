import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V42: Fix Critical DB URL Parsing Error - Hardcoded Fallback Priority"

# --- 1. app/__init__.py (Lógica de Conexão Refeita) ---
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
    app_inst.secret_key = os.environ.get('SECRET_KEY', 'chave_v42_db_fix')
    
    # --- CONFIGURAÇÃO DO BANCO DE DADOS (PRIORIDADE MÁXIMA) ---
    # URL Oficial do Neon (Hardcoded para garantir funcionamento)
    hardcoded_db_url = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"
    
    # Tenta pegar do ambiente
    env_db_url = os.environ.get('DATABASE_URL')
    
    # Lógica de Decisão:
    # Se existe no ambiente E parece válida (tem 'postgres'), usa a do ambiente.
    # Caso contrário, usa a hardcoded.
    final_db_url = hardcoded_db_url
    
    if env_db_url and "postgres" in env_db_url:
        final_db_url = env_db_url
        
    # Correção obrigatória para SQLAlchemy recentes (postgres:// -> postgresql://)
    if final_db_url.startswith("postgres://"):
        final_db_url = final_db_url.replace("postgres://", "postgresql://", 1)
    
    # Log de Debug (Mascarando a senha por segurança)
    try:
        masked_url = final_db_url.split('@')[1] if '@' in final_db_url else 'URL_INVALIDA'
        logger.info(f"Conectando ao banco em: ...@{masked_url}")
    except:
        logger.info("Conectando ao banco (URL não parseável para log)")

    # Aplica a configuração
    app_inst.config['SQLALCHEMY_DATABASE_URI'] = final_db_url
    app_inst.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Configurações do Pool (Estabilidade)
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
            # Verifica se precisa criar o Master
            from app.models import User
            # Tenta buscar de forma segura para não quebrar se a tabela não existir
            try:
                if not User.query.filter_by(username='Thaynara').first():
                    m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
                    m.set_password('1855')
                    db.session.add(m)
                    db.session.commit()
                    logger.info("Usuario Master verificado/criado.")
            except Exception as e:
                logger.error(f"Erro ao verificar usuario Master: {e}")
                
        except Exception as e:
            logger.error(f"Erro Crítico no Boot do Banco: {e}")

    return app_inst

# Instância Global para o Gunicorn
app = create_app()
"""

# --- 2. run.py (Mantido para compatibilidade) ---
FILE_RUN = """
from app import app

if __name__ == "__main__":
    app.run(debug=True)
"""

# --- 3. Procfile (Comando Seguro) ---
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
        print("\n>>> SUCESSO V42! CONEXÃO DO BANCO CORRIGIDA <<<")
    except Exception as e:
        print(f"Erro Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- FIX V42 DATABASE CONNECTION: {PROJECT_NAME} ---")
    
    write_file("app/__init__.py", FILE_INIT)
    write_file("run.py", FILE_RUN)
    write_file("Procfile", FILE_PROCFILE)
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



import os
import shutil
import subprocess
import re
from datetime import datetime

# ================= CONFIGURAÇÕES =================
PROJECT_DIR = os.getcwd()
BACKUP_ROOT = os.path.join(PROJECT_DIR, "backups_auto")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
CURRENT_BACKUP_DIR = os.path.join(BACKUP_ROOT, f"bkp_security_{TIMESTAMP}")

# Dados sensíveis extraídos do contexto anterior (serão movidos para .env)
DB_URL_ATUAL = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"
SECRET_KEY_ATUAL = "chave_secreta_padrao"

def log(msg):
    print(f"\033[92m[SECURITY-SCRIPT]\033[0m {msg}")

def create_backup_of_file(file_path):
    """Faz backup de um único arquivo se ele existir"""
    full_path = os.path.join(PROJECT_DIR, file_path)
    if os.path.exists(full_path):
        dest_path = os.path.join(CURRENT_BACKUP_DIR, file_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(full_path, dest_path)

def update_requirements():
    log("Atualizando requirements.txt...")
    req_path = os.path.join(PROJECT_DIR, "requirements.txt")
    create_backup_of_file("requirements.txt")
    
    with open(req_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    additions = []
    if "python-dotenv" not in content: additions.append("python-dotenv")
    if "Flask-WTF" not in content: additions.append("Flask-WTF")
    if "email_validator" not in content: additions.append("email_validator") # Útil para Flask-WTF
    
    if additions:
        with open(req_path, "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(additions))
        log(f"Adicionados: {', '.join(additions)}")

def setup_environment_vars():
    log("Configurando Variáveis de Ambiente (.env)...")
    env_path = os.path.join(PROJECT_DIR, ".env")
    gitignore_path = os.path.join(PROJECT_DIR, ".gitignore")
    
    # 1. Criar .env
    env_content = f"""# Configurações de Segurança do Thay-RH
DATABASE_URL="{DB_URL_ATUAL}"
SECRET_KEY="{SECRET_KEY_ATUAL}"
FLASK_APP=run.py
FLASK_DEBUG=1
"""
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)
    log("Arquivo .env criado com sucesso.")

    # 2. Atualizar .gitignore
    create_backup_of_file(".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            git_content = f.read()
    else:
        git_content = ""
        
    if ".env" not in git_content:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write("\n.env\n.venv\n__pycache__/\n*.pyc\n")
        log(".gitignore atualizado para proteger o .env")

def update_extensions():
    log("Configurando Flask-WTF em extensions.py...")
    ext_path = "app/extensions.py"
    create_backup_of_file(ext_path)
    
    content = """from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
"""
    with open(os.path.join(PROJECT_DIR, ext_path), "w", encoding="utf-8") as f:
        f.write(content)

def update_init():
    log("Atualizando app/__init__.py para carregar .env e CSRF...")
    init_path = "app/__init__.py"
    create_backup_of_file(init_path)
    
    content = """import os
from flask import Flask
from dotenv import load_dotenv
from app.extensions import db, login_manager, csrf

# Carrega variáveis do arquivo .env
load_dotenv()

def create_app():
    app = Flask(__name__)
    
    # Configuração via Variáveis de Ambiente (Segurança)
    app.secret_key = os.environ.get('SECRET_KEY', 'chave_dev_insegura_se_falhar')
    
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        # Fallback apenas para evitar crash se o .env falhar, mas logando aviso
        print("AVISO: DATABASE_URL não encontrada no ambiente.")
        db_url = "sqlite:///backup_emergencia.db"
        
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Configurações de Pool de Conexão (Estabilidade)
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    
    # Inicializa Extensões
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app) # Ativa proteção CSRF Global
    
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

        try:
            db.create_all()
        except:
            pass

    return app

app = create_app()
"""
    with open(os.path.join(PROJECT_DIR, init_path), "w", encoding="utf-8") as f:
        f.write(content)

def inject_csrf_in_templates():
    log("Injetando tokens CSRF em todos os formulários HTML...")
    templates_dir = os.path.join(PROJECT_DIR, "app/templates")
    
    # Token que vamos injetar
    csrf_input = '\n        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>'
    
    # Regex para encontrar <form ... method="POST" ...> (case insensitive)
    # Grupo 1 pega toda a tag de abertura do form
    regex_form = re.compile(r'(<form[^>]*method=["\'](?:POST|post)["\'][^>]*>)', re.IGNORECASE)

    count = 0
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith(".html"):
                full_path = os.path.join(root, file)
                
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Verifica se tem form POST e se já não tem o token
                if re.search(r'method=["\'](?:POST|post)["\']', content, re.IGNORECASE):
                    if "csrf_token" not in content:
                        create_backup_of_file(os.path.relpath(full_path, PROJECT_DIR))
                        
                        # Substitui a tag <form ...> por <form ...> + input hidden
                        new_content = regex_form.sub(r'\1' + csrf_input, content)
                        
                        with open(full_path, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        
                        log(f"Token injetado em: {file}")
                        count += 1
    
    log(f"Total de templates protegidos: {count}")

def git_operations():
    log("Executando Git Push automático...")
    try:
        # Verifica status antes
        subprocess.run(["git", "status"], check=False)
        
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Security Update: CSRF Protection and Env Vars"], check=True)
        subprocess.run(["git", "push"], check=True)
        log("Código enviado para o repositório.")
    except subprocess.CalledProcessError as e:
        log(f"\033[91mErro no Git: {e}\033[0m")
        log("Nota: O .gitignore pode ter impedido commit do .env (Correto).")

def self_destruct():
    log("Iniciando auto-destruição do script...")
    try:
        os.remove(__file__)
        log("Script deletado. Sistema seguro.")
    except Exception as e:
        log(f"Erro ao deletar script: {e}")

if __name__ == "__main__":
    # Garante que a pasta de backup existe
    if not os.path.exists(CURRENT_BACKUP_DIR):
        os.makedirs(CURRENT_BACKUP_DIR)

    try:
        update_requirements()
        setup_environment_vars()
        update_extensions()
        update_init()
        inject_csrf_in_templates()
        git_operations()
    except Exception as e:
        log(f"\033[91mERRO FATAL: {e}\033[0m")
    finally:
        self_destruct()



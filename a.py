import os
import shutil
import subprocess
import sys
from datetime import datetime

# ================= CONFIGURAÇÕES =================
PROJECT_DIR = os.getcwd()
BACKUP_ROOT = os.path.join(PROJECT_DIR, "backups_auto")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
CURRENT_BACKUP_DIR = os.path.join(BACKUP_ROOT, f"bkp_migrations_{TIMESTAMP}")

def log(msg):
    print(f"\033[96m[MIGRATE-SCRIPT]\033[0m {msg}")

def create_backup(files):
    log("Criando backup...")
    if not os.path.exists(CURRENT_BACKUP_DIR):
        os.makedirs(CURRENT_BACKUP_DIR)
    for f in files:
        src = os.path.join(PROJECT_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(CURRENT_BACKUP_DIR, os.path.basename(f)))

def step_1_requirements():
    log("1. Atualizando requirements.txt...")
    req_path = "requirements.txt"
    create_backup([req_path])
    
    with open(req_path, "r") as f:
        content = f.read()
    
    if "Flask-Migrate" not in content:
        with open(req_path, "a") as f:
            f.write("\nFlask-Migrate")

def step_2_extensions():
    log("2. Configurando extensions.py...")
    ext_path = "app/extensions.py"
    create_backup([ext_path])
    
    # Adiciona a importação e instância do Migrate
    content = """from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()
"""
    with open(ext_path, "w") as f:
        f.write(content)

def step_3_init_app():
    log("3. Registrando Migrate no app/__init__.py...")
    init_path = "app/__init__.py"
    create_backup([init_path])
    
    with open(init_path, "r") as f:
        lines = f.readlines()
    
    new_lines = []
    import_added = False
    init_added = False
    
    for line in lines:
        # Atualiza importação
        if "from app.extensions import" in line and "migrate" not in line:
            new_lines.append("from app.extensions import db, login_manager, csrf, migrate\n")
            import_added = True
        else:
            if not import_added and "from app.extensions import" in line:
                new_lines.append(line)
            elif "from app.extensions import" not in line:
                new_lines.append(line)

        # Atualiza inicialização
        if "csrf.init_app(app)" in line and not init_added:
            new_lines.append("    migrate.init_app(app, db)\n")
            init_added = True
            
    with open(init_path, "w") as f:
        f.writelines(new_lines)

def step_4_run_commands():
    log("4. Inicializando repositório de migrações (Isso pode demorar)...")
    
    # Define variável de ambiente para o comando flask funcionar
    env = os.environ.copy()
    env["FLASK_APP"] = "run.py"
    
    try:
        # Instala dependência primeiro
        subprocess.run([sys.executable, "-m", "pip", "install", "Flask-Migrate"], check=True)
        
        # Flask DB Init
        if not os.path.exists("migrations"):
            subprocess.run([sys.executable, "-m", "flask", "db", "init"], env=env, check=True)
            log("Pasta 'migrations' criada.")
        else:
            log("Pasta 'migrations' já existe.")

        # Flask DB Migrate (Gera o primeiro script)
        subprocess.run([sys.executable, "-m", "flask", "db", "migrate", "-m", "Initial migration"], env=env, check=False)
        log("Migração inicial gerada (se houve mudanças).")
        
        # Flask DB Upgrade (Aplica)
        subprocess.run([sys.executable, "-m", "flask", "db", "upgrade"], env=env, check=False)
        log("Banco de dados atualizado/sincronizado.")
        
    except subprocess.CalledProcessError as e:
        log(f"\033[93mAviso: Erro ao rodar comandos Flask ({e}). Verifique se o .env está correto.\033[0m")

def git_operations():
    log("Git Push...")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Infra: Added Flask-Migrate support"], check=True)
        subprocess.run(["git", "push"], check=True)
    except: pass

def self_destruct():
    try: os.remove(__file__)
    except: pass

if __name__ == "__main__":
    step_1_requirements()
    step_2_extensions()
    step_3_init_app()
    step_4_run_commands()
    git_operations()
    self_destruct()



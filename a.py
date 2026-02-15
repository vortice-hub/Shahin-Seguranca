import os
import shutil
import subprocess
import re
from datetime import datetime

# ================= CONFIGURAÇÕES =================
PROJECT_DIR = os.getcwd()
BACKUP_ROOT = os.path.join(PROJECT_DIR, "backups_auto")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
CURRENT_BACKUP_DIR = os.path.join(BACKUP_ROOT, f"bkp_structure_{TIMESTAMP}")

def log(msg):
    print(f"\033[96m[ARCH-SCRIPT]\033[0m {msg}")

def ensure_dir_exists(file_path):
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

def create_backup(files_list):
    log("Criando backup de segurança...")
    if not os.path.exists(CURRENT_BACKUP_DIR):
        os.makedirs(CURRENT_BACKUP_DIR)
    
    for file_path in files_list:
        full_path = os.path.join(PROJECT_DIR, file_path)
        if os.path.exists(full_path):
            dest_path = os.path.join(CURRENT_BACKUP_DIR, file_path)
            ensure_dir_exists(dest_path)
            shutil.copy2(full_path, dest_path)

def step_1_create_config():
    log("ETAPA 1: Criando config.py centralizado...")
    config_content = """import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'chave_padrao_desenvolvimento')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///dev.db')

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

# Dicionário para facilitar a seleção
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
"""
    with open("config.py", "w", encoding="utf-8") as f:
        f.write(config_content)

def step_2_update_init():
    log("ETAPA 1.2: Atualizando app/__init__.py para usar Config...")
    init_path = "app/__init__.py"
    create_backup([init_path])
    
    content = """import os
from flask import Flask
from app.extensions import db, login_manager, csrf
from config import config_map

def create_app():
    app = Flask(__name__)
    
    # Determina o ambiente (padrão: development)
    env_name = os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config_map[env_name])
    
    # Correção para URLs Postgres do Render/Neon
    db_url = app.config.get('SQLALCHEMY_DATABASE_URI')
    if db_url and db_url.startswith("postgres://"):
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://", 1)
    
    # Inicializa Extensões
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
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
    with open(init_path, "w", encoding="utf-8") as f:
        f.write(content)

def step_3_create_global_css():
    log("ETAPA 2: Criando CSS Híbrido (app/static/css/style.css)...")
    css_dir = "app/static/css"
    if not os.path.exists(css_dir):
        os.makedirs(css_dir)
    
    css_content = """/* Estilos Globais do Thay-RH */

/* Componentes de Formulário (Extraídos dos templates) */
.label-pro { 
    display: block; 
    font-size: 0.7rem; 
    font-weight: 700; 
    color: #64748b; 
    text-transform: uppercase; 
    margin-bottom: 0.5rem; 
    letter-spacing: 0.05em;
} 

.input-pro { 
    width: 100%; 
    background-color: #f8fafc; 
    border: 1px solid #e2e8f0; 
    border-radius: 0.5rem; 
    padding: 0.75rem 1rem; 
    color: #1e293b; 
    font-weight: 500; 
    outline: none; 
    transition: all 0.2s;
}

.input-pro:focus {
    background-color: #ffffff;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

/* Utilitários de Animação */
.animate-fade-in { 
    animation: fadeIn 0.5s ease-out; 
}

@keyframes fadeIn { 
    from { opacity: 0; transform: translateY(10px); } 
    to { opacity: 1; transform: translateY(0); } 
}
"""
    with open(os.path.join(css_dir, "style.css"), "w", encoding="utf-8") as f:
        f.write(css_content)

def step_4_update_base_html():
    log("ETAPA 2.1: Conectando CSS no base.html...")
    base_path = "app/templates/base.html"
    create_backup([base_path])
    
    with open(base_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Injeta o link do CSS se não existir
    css_link = '<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/style.css\') }}">'
    if "style.css" not in content:
        content = content.replace("</head>", f"    {css_link}\n</head>")
        # Remove estilos inline antigos se existirem no head
        content = re.sub(r'<style>.*?body.*?keyframes.*?</style>', '', content, flags=re.DOTALL)
        
        with open(base_path, "w", encoding="utf-8") as f:
            f.write(content)

def step_5_organize_templates():
    log("ETAPA 3: Organizando Templates e Rotas...")
    
    # Mapa de Movimentação: {Origem: Destino}
    moves = {
        # ADMIN
        "app/templates/novo_usuario.html": "app/admin/templates/admin/novo_usuario.html",
        "app/templates/sucesso_usuario.html": "app/admin/templates/admin/sucesso_usuario.html",
        "app/templates/admin_solicitacoes.html": "app/admin/templates/admin/solicitacoes.html",
        "app/templates/admin_liberar_acesso.html": "app/admin/templates/admin/liberar_acesso.html",
        "app/templates/admin_importar_csv.html": "app/admin/templates/admin/importar_csv.html",
        # PONTO
        "app/templates/ponto_registro.html": "app/ponto/templates/ponto/registro.html",
    }
    
    # Mapa de Atualização de Rotas: {ArquivoRota: [(OldTemplate, NewTemplate)]}
    route_updates = {
        "app/admin/routes.py": [
            ("'novo_usuario.html'", "'admin/novo_usuario.html'"),
            ("'sucesso_usuario.html'", "'admin/sucesso_usuario.html'"),
            ("'admin_solicitacoes.html'", "'admin/solicitacoes.html'"),
            ("'admin_liberar_acesso.html'", "'admin/liberar_acesso.html'"),
            ("'admin_importar_csv.html'", "'admin/importar_csv.html'"),
        ],
        "app/ponto/routes.py": [
            ("'ponto_registro.html'", "'ponto/registro.html'")
        ]
    }

    # Backup das rotas
    create_backup(list(route_updates.keys()))

    # 1. Mover Arquivos e Limpar CSS Inline
    for src, dest in moves.items():
        full_src = os.path.join(PROJECT_DIR, src)
        if os.path.exists(full_src):
            ensure_dir_exists(os.path.join(PROJECT_DIR, dest))
            
            with open(full_src, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Remove blocos <style> que definem .label-pro e .input-pro (já estão no global)
            content = re.sub(r'<style>.*?\.label-pro.*?</style>', '', content, flags=re.DOTALL)
            
            with open(os.path.join(PROJECT_DIR, dest), 'w', encoding='utf-8') as f:
                f.write(content)
            
            os.remove(full_src)
            log(f"Movido: {src} -> {dest}")
        else:
            log(f"Aviso: {src} não encontrado, pulando movimento.")

    # 2. Atualizar Referências nas Rotas
    for route_file, replacements in route_updates.items():
        full_path = os.path.join(PROJECT_DIR, route_file)
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for old, new in replacements:
                content = content.replace(old, new)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            log(f"Rota atualizada: {route_file}")

def git_operations():
    log("Executando Git Push...")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Arch Upgrade: Config Class, Global CSS and Organized Templates"], check=True)
        subprocess.run(["git", "push"], check=True)
        log("Código enviado.")
    except Exception as e:
        log(f"Erro Git: {e}")

def self_destruct():
    try:
        os.remove(__file__)
        log("Script limpo.")
    except: pass

if __name__ == "__main__":
    try:
        step_1_create_config()
        step_2_update_init()
        step_3_create_global_css()
        step_4_update_base_html()
        step_5_organize_templates()
        git_operations()
    except Exception as e:
        log(f"\033[91mErro Fatal: {e}\033[0m")
    finally:
        self_destruct()



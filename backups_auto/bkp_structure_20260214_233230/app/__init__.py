import os
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

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
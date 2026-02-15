import os
import logging
from flask import Flask
from app.extensions import db, login_manager, csrf, migrate
from config import config_map
from werkzeug.middleware.proxy_fix import ProxyFix

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    env_name = os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config_map[env_name])
    
    db_url = app.config.get('SQLALCHEMY_DATABASE_URI')
    if db_url and db_url.startswith("postgres://"):
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://", 1)
    
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    
    login_manager.login_view = 'auth.login'

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
            from app.models import User
            
            # 1. Garante Master
            if not User.query.filter_by(username='Thaynara').first():
                m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
                m.set_password('1855')
                db.session.add(m)
                logger.info("Usuario Master criado.")

            # 2. Garante Terminal (RECRIAÇÃO)
            term = User.query.filter_by(username='terminal').first()
            if not term:
                t = User(
                    username='terminal',
                    real_name='Terminal de Ponto',
                    role='Terminal',
                    is_first_access=False,
                    cpf='00000000000',
                    salario=0.0
                )
                t.set_password('terminal1234')
                db.session.add(t)
                logger.info("Usuario Terminal criado.")
            else:
                # Se ja existe, forca a senha para garantir
                term.set_password('terminal1234')
                logger.info("Senha do Terminal resetada para padrao.")
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Erro no boot do DB: {e}")

    return app

app = create_app()
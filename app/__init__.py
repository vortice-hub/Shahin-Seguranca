import os
import logging
from flask import Flask
from app.extensions import db, login_manager, csrf, migrate
from config import config_map
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import text

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
    
    # Inicialização das extensões
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    
    login_manager.login_view = 'auth.login'

    # --- CORREÇÃO: USER LOADER (O que estava faltando) ---
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # --- REGISTO DE FUNÇÕES PARA O HTML ---
    @app.context_processor
    def inject_permissions():
        from app.utils import has_permission
        return dict(has_permission=has_permission)

    with app.app_context():
        # Importação de Blueprints
        from app.auth.routes import auth_bp
        from app.admin.routes import admin_bp
        from app.ponto.routes import ponto_bp
        from app.estoque.routes import estoque_bp
        from app.documentos.routes import documentos_bp
        from app.main.routes import main_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(admin_bp)
        app.register_blueprint(ponto_bp)
        app.register_blueprint(estoque_bp)
        app.register_blueprint(documentos_bp)
        app.register_blueprint(main_bp)

        try:
            db.create_all()
            
            # Patch de permissões
            try:
                with db.engine.connect() as connection:
                    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions VARCHAR(255) DEFAULT '';"))
                    connection.commit()
                logger.info(">>> PATCH DE BANCO (PERMISSÕES) APLICADO <<<")
            except Exception as e:
                logger.warning(f"Info Patch Banco: {e}")

            from app.models import User
            
            # --- GESTÃO DO USUÁRIO MASTER ---
            cpf_master = '50097952800'
            master = User.query.filter_by(username=cpf_master).first()
            
            if not master:
                m = User(
                    username=cpf_master, 
                    cpf=cpf_master,
                    real_name='Thaynara Master', 
                    role='Master', 
                    is_first_access=False, 
                    permissions="ALL",
                    salario=0.0
                )
                m.set_password('1855')
                db.session.add(m)
                logger.info(f"Novo Master {cpf_master} criado.")
            else:
                if master.role != 'Master': master.role = 'Master'
                master.permissions = "ALL"

            # Garantir usuário terminal
            term = User.query.filter_by(username='12345678900').first()
            if not term:
                t = User(username='12345678900', real_name='Terminal de Ponto', role='Terminal', is_first_access=False, cpf='12345678900', salario=0.0)
                t.set_password('terminal1234')
                db.session.add(t)
            
            db.session.commit()
        except Exception as e:
            logger.error(f"Erro no boot do DB: {e}")

    return app

app = create_app()


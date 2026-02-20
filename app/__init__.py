import os
import logging
from flask import Flask, render_template
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

    # --- CORREÇÃO: USER LOADER ---
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_permissions():
        from app.utils import has_permission
        return dict(has_permission=has_permission)

    # --- INTERCETORES DE ERRO GLOBAIS ---
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

    with app.app_context():
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

    # --- COMANDO DE SEEDING ISOLADO E LIMPO (FASE 3) ---
    @app.cli.command("setup-db")
    def setup_db():
        """Comando manual para criar tabelas e utilizadores padrão."""
        with app.app_context():
            try:
                db.create_all()
                
                from app.models import User
                
                # GESTÃO MASTER
                cpf_master = '50097952800'
                master = User.query.filter_by(username=cpf_master).first()
                if not master:
                    m = User(username=cpf_master, cpf=cpf_master, real_name='Thaynara Master', role='Master', is_first_access=False, permissions="ALL", salario=0.0)
                    senha_master = os.environ.get('MASTER_PASSWORD', '1855')
                    m.set_password(senha_master)
                    db.session.add(m)
                else:
                    master.role = 'Master'
                    master.permissions = "ALL"

                # GESTÃO TERMINAL
                term = User.query.filter_by(username='12345678900').first()
                if not term:
                    t = User(username='12345678900', real_name='Terminal de Ponto', role='Terminal', is_first_access=False, cpf='12345678900', salario=0.0)
                    senha_terminal = os.environ.get('TERMINAL_PASSWORD', 'terminal1234')
                    t.set_password(senha_terminal)
                    db.session.add(t)
                
                db.session.commit()
                print(">>> BANCO DE DADOS E UTILIZADORES CONFIGURADOS COM SUCESSO <<<")
                logger.info(">>> BOOT DO BANCO DE DADOS OK <<<")
            except Exception as e:
                print(f"Erro ao configurar DB: {e}")
                logger.error(f"Erro no boot do DB: {e}")

    return app

app = create_app()


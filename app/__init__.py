import os
import logging
from flask import Flask, render_template, request, g, abort, redirect, url_for, flash
from flask_login import current_user, logout_user
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

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_permissions():
        from app.utils import has_permission
        return dict(has_permission=has_permission)

    # ==============================================================================
    # 🛡️ VORTICE SAAS: O PORTEIRO GLOBAL (MIDDLEWARE MULTI-TENANT)
    # ==============================================================================
    @app.before_request
    def blindagem_multi_tenant():
        if request.endpoint and request.endpoint.startswith('static'):
            return

        if current_user.is_authenticated:
            # 🚀 EXCEÇÃO VIP VORTICE: O dono da plataforma não é barrado no Control Plane
            if str(current_user.username) == '50097952800' and request.path.startswith('/vortice'):
                # Tenta carregar a empresa só para o layout base funcionar, mas não o bloqueia se não tiver
                if getattr(current_user, 'empresa_id', None):
                    from app.models import Empresa
                    g.empresa = Empresa.query.get(current_user.empresa_id)
                return # Deixa passar livremente para as rotas da Vortice

            # 🏢 Regras Normais para Inquilinos (Tenants)
            # Garante que o usuário tem um vínculo de empresa
            if getattr(current_user, 'empresa_id', None) is None:
                logout_user()
                abort(403)
            
            from app.models import Empresa
            empresa_atual = Empresa.query.get(current_user.empresa_id)
            
            # Se a empresa não existir ou estiver desativada, desconecta
            if not empresa_atual or not empresa_atual.ativa:
                logout_user()
                flash("Acesso negado: Empresa não encontrada ou desativada.", "error")
                return redirect(url_for('auth.login'))

            # Injeta a empresa no contexto global
            g.empresa = empresa_atual
            g.empresa_id = empresa_atual.id

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
        # Blueprints
        from app.auth.routes import auth_bp
        from app.admin.routes import admin_bp
        from app.admin.super_routes import super_admin_bp
        from app.ponto.routes import ponto_bp
        from app.estoque.routes import estoque_bp
        from app.documentos.routes import documentos_bp
        from app.main.routes import main_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(admin_bp)
        app.register_blueprint(super_admin_bp)
        app.register_blueprint(ponto_bp)
        app.register_blueprint(estoque_bp)
        app.register_blueprint(documentos_bp)
        app.register_blueprint(main_bp)

    return app

app = create_app()


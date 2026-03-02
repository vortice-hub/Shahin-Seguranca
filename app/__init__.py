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
        # 1. Ignora arquivos estáticos
        if request.endpoint and request.endpoint.startswith('static'):
            return

        # 2. Ignora rotas do painel de controle administrativo da Vortice
        if request.path.startswith('/vortice'):
            return

        # 3. DETECÇÃO INTELIGENTE DE DOMÍNIO (SaaS Produção vs Staging)
        host = request.host.lower()
        
        # Se NÃO estiver no ambiente de testes (.run.app ou localhost)
        if '.run.app' not in host and 'localhost' not in host and '127.0.0.1' not in host:
            # Exemplo: shahin.vortice.company
            partes = host.split('.')
            
            # Garante que há um subdomínio antes de vortice.company
            if len(partes) >= 3 and partes[-2] == 'vortice' and partes[-1] == 'company':
                subdominio = partes[0]
                
                if subdominio != 'www':
                    from app.models import Empresa
                    empresa_host = Empresa.query.filter_by(slug=subdominio).first()
                    
                    if not empresa_host or not empresa_host.ativa:
                        # Bloqueia se aceder a um subdomínio que não existe ou está inativo
                        abort(404)
                        
                    # Injeta a empresa do subdomínio globalmente na sessão
                    g.empresa = empresa_host
                    g.empresa_id = empresa_host.id

        # 4. VALIDAÇÃO DE USUÁRIO AUTENTICADO
        if current_user.is_authenticated:
            empresa_id = getattr(current_user, 'empresa_id', None)
            
            if empresa_id is None:
                logout_user()
                flash("Acesso interrompido: Utilizador sem vínculo empresarial. Faça login novamente.", "error")
                return redirect(url_for('auth.login'))
            
            from app.models import Empresa
            empresa_atual = Empresa.query.get(empresa_id)
            
            if not empresa_atual or not empresa_atual.ativa:
                logout_user()
                flash("Acesso negado: Empresa inativa ou não encontrada. Contacte o suporte.", "error")
                return redirect(url_for('auth.login'))

            # 5. PROTEÇÃO ANTI-VAZAMENTO CROSS-TENANT
            # Se o usuário digitou o subdomínio da empresa A, mas ele é da empresa B, desloga!
            if hasattr(g, 'empresa_id') and g.empresa_id != empresa_id:
                if current_user.username != '50097952800': # Apenas o Super Admin Vortice pode transitar livremente
                    logout_user()
                    flash("Tentativa de acesso a um ambiente não autorizado.", "error")
                    return redirect(url_for('auth.login'))

            # Garante que o contexto tem a empresa atual
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
        # Registo de Blueprints
        from app.auth.routes import auth_bp
        from app.admin.routes import admin_bp
        from app.admin.super_routes import super_admin_bp
        from app.ponto.routes import ponto_bp
        from app.estoque.routes import estoque_bp
        from app.documentos.routes import documentos_bp
        from app.main.routes import main_bp
        from app.recrutamento import recrutamento_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(admin_bp)
        app.register_blueprint(super_admin_bp)
        app.register_blueprint(ponto_bp)
        app.register_blueprint(estoque_bp)
        app.register_blueprint(documentos_bp)
        app.register_blueprint(main_bp)
        app.register_blueprint(recrutamento_bp)
        
        # ==============================================================================
        # 🚀 AUTO-MIGRAÇÃO DE BANCO DE DADOS
        # Cria fisicamente as tabelas que faltam no PostgreSQL (Vagas, Candidatos, etc)
        # ==============================================================================
        db.create_all()

    return app

app = create_app()


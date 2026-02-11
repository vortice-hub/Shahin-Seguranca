import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Instancias globais (sem app ainda)
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.secret_key = 'chave_v39_modular_secret'
    
    # Config DB
    db_url = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"
    # Fallback para ambiente de producao
    if os.environ.get('DATABASE_URL'):
        db_url = os.environ.get('DATABASE_URL')
        
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Inicializa Extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # Registra Blueprints (Rotas)
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.admin import admin_bp
    from app.routes.ponto import ponto_bp
    from app.routes.estoque import estoque_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ponto_bp)
    app.register_blueprint(estoque_bp)

    # Context Processor (Injeta funcoes nos templates)
    @app.context_processor
    def utility_processor():
        return dict()

    # Cria tabelas no boot
    with app.app_context():
        db.create_all()
        # Cria Master se nao existir
        from app.models import User
        if not User.query.filter_by(username='Thaynara').first():
            m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
            m.set_password('1855')
            db.session.add(m)
            db.session.commit()

    return app
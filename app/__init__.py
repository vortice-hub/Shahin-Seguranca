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
            
            # --- PATCH AUTOMÁTICO DE BANCO ---
            try:
                with db.engine.connect() as connection:
                    # Garante Tabela de Recibos e Campos de Usuario
                    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS razao_social_empregadora VARCHAR(150) DEFAULT 'LA SHAHIN SERVIÇOS DE SEGURANÇA E PRONTA RESPOSTA LTDA';"))
                    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cnpj_empregador VARCHAR(25) DEFAULT '50.537.235/0001-95';"))
                    
                    # Garante Campos de Jornada
                    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS carga_horaria INTEGER DEFAULT 528;"))
                    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS tempo_intervalo INTEGER DEFAULT 60;"))
                    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS inicio_jornada_ideal VARCHAR(5) DEFAULT '07:12';"))
                    
                    # Garante Campos de Pré-Cadastro
                    connection.execute(text("ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS razao_social VARCHAR(150) DEFAULT 'LA SHAHIN SERVIÇOS DE SEGURANÇA E PRONTA RESPOSTA LTDA';"))
                    connection.execute(text("ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS cnpj VARCHAR(25) DEFAULT '50.537.235/0001-95';"))
                    connection.execute(text("ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS carga_horaria INTEGER DEFAULT 528;"))
                    connection.execute(text("ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS tempo_intervalo INTEGER DEFAULT 60;"))
                    connection.execute(text("ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS inicio_jornada_ideal VARCHAR(5) DEFAULT '07:12';"))
                    
                    # A tabela espelho_ponto_docs é criada pelo db.create_all(), mas em alguns casos de migração
                    # complexa no Postgres pode precisar de empurrão se o DB já existir.
                    # Mas como é tabela nova, o SQLAlchemy costuma criar. Deixaremos sem SQL manual para ela por enquanto.
                    
                    connection.commit()
                logger.info(">>> PATCH DE BANCO DE DADOS APLICADO <<<")
            except Exception as e:
                logger.warning(f"Info Patch Banco: {e}")
            # -------------------------------------------------------------

            from app.models import User
            
            master = User.query.filter_by(username='Thaynara').first()
            if not master:
                m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
                m.set_password('1855')
                db.session.add(m)
            else:
                if master.role != 'Master': master.role = 'Master'

            term = User.query.filter_by(username='terminal').first()
            if not term:
                t = User(username='terminal', real_name='Terminal de Ponto', role='Terminal', is_first_access=False, cpf='00000000000', salario=0.0)
                t.set_password('terminal1234')
                db.session.add(t)
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Erro no boot do DB: {e}")

    return app

app = create_app()




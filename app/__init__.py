import os
import logging
from flask import Flask
from app.extensions import db, login_manager, csrf, migrate
from config import config_map
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import text  # Importação necessária para o patch

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
            
            # --- PATCH DE EMERGÊNCIA NEON/POSTGRES ---
            # Força a criação das colunas novas antes de qualquer consulta de usuário
            try:
                # Usa transação isolada para garantir execução
                with db.engine.connect() as connection:
                    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS razao_social_empregadora VARCHAR(150) DEFAULT 'LA SHAHIN SERVIÇOS DE SEGURANÇA E PRONTA RESPOSTA LTDA';"))
                    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cnpj_empregador VARCHAR(25) DEFAULT '50.537.235/0001-95';"))
                    connection.execute(text("ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS razao_social VARCHAR(150) DEFAULT 'LA SHAHIN SERVIÇOS DE SEGURANÇA E PRONTA RESPOSTA LTDA';"))
                    connection.execute(text("ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS cnpj VARCHAR(25) DEFAULT '50.537.235/0001-95';"))
                    connection.commit()
                logger.info(">>> PATCH DE BANCO DE DADOS APLICADO COM SUCESSO <<<")
            except Exception as e:
                # Se der erro (ex: sintaxe ou permissão), apenas loga. 
                # Se a coluna já existir, o IF NOT EXISTS cuida disso.
                logger.warning(f"Nota sobre Patch de Banco: {e}")
            # -----------------------------------------

            from app.models import User
            
            # Garante Master
            master = User.query.filter_by(username='Thaynara').first()
            if not master:
                m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
                m.set_password('1855')
                db.session.add(m)
            else:
                if master.role != 'Master': master.role = 'Master'

            # Garante Terminal
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




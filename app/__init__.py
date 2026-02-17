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
    
    # Configuração do Ambiente
    env_name = os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config_map[env_name])
    
    # Ajuste de URL para PostgreSQL (GCP/Heroku compatibility)
    db_url = app.config.get('SQLALCHEMY_DATABASE_URI')
    if db_url and db_url.startswith("postgres://"):
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://", 1)
    
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Inicialização das Extensões
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    
    login_manager.login_view = 'auth.login'

    # --- CORREÇÃO: USER LOADER (Indispensável para o Flask-Login) ---
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # --- INJEÇÃO DE PERMISSÕES PARA O HTML ---
    @app.context_processor
    def inject_permissions():
        from app.utils import has_permission
        return dict(has_permission=has_permission)

    with app.app_context():
        # Importação e Registo de Blueprints
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
            # Criação de tabelas novas
            db.create_all()
            
            # --- PATCH DE EMERGÊNCIA: SINCRONIZAÇÃO DE COLUNAS NO BANCO ---
            with db.engine.connect() as connection:
                # Adiciona colunas que podem estar faltando no PontoResumo
                cols_ponto = [
                    "minutos_trabalhados INTEGER DEFAULT 0",
                    "minutos_extras INTEGER DEFAULT 0",
                    "minutos_falta INTEGER DEFAULT 0",
                    "saldo_dia INTEGER DEFAULT 0",
                    "status_dia VARCHAR(20) DEFAULT 'OK'"
                ]
                for col in cols_ponto:
                    try:
                        col_name = col.split()[0]
                        connection.execute(text(f"ALTER TABLE ponto_resumos ADD COLUMN IF NOT EXISTS {col};"))
                        connection.commit()
                    except Exception:
                        pass # Ignora se a coluna já existir

                # Garante que a tabela PreCadastro exista no PostgreSQL
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS pre_cadastros (
                        id SERIAL PRIMARY KEY,
                        cpf VARCHAR(14) UNIQUE NOT NULL,
                        nome_previsto VARCHAR(120) NOT NULL,
                        cargo VARCHAR(80),
                        salario FLOAT DEFAULT 0.0,
                        razao_social VARCHAR(200),
                        cnpj VARCHAR(20),
                        carga_horaria INTEGER DEFAULT 528,
                        tempo_intervalo INTEGER DEFAULT 60,
                        inicio_jornada_ideal VARCHAR(5) DEFAULT '08:00',
                        escala VARCHAR(20) DEFAULT 'Livre',
                        data_inicio_escala DATE,
                        created_at TIMESTAMP
                    );
                """))
                connection.commit()
                
                # Patch de permissões na tabela users
                connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions VARCHAR(255) DEFAULT '';"))
                connection.commit()

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
                logger.info(f"Usuário Master {cpf_master} criado com sucesso.")
            else:
                if master.role != 'Master': master.role = 'Master'
                if not master.permissions: master.permissions = "ALL"

            # --- GARANTIR USUÁRIO TERMINAL ---
            term = User.query.filter_by(username='12345678900').first()
            if not term:
                t = User(
                    username='12345678900', 
                    real_name='Terminal de Ponto', 
                    role='Terminal', 
                    is_first_access=False, 
                    cpf='12345678900', 
                    salario=0.0
                )
                t.set_password('terminal1234')
                db.session.add(t)
            
            db.session.commit()
            logger.info(">>> BOOT DO SISTEMA CONCLUÍDO COM SUCESSO <<<")

        except Exception as e:
            logger.error(f"Erro no boot do DB: {e}")
            db.session.rollback()

    return app

app = create_app()


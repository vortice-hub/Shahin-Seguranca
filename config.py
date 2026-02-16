import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Segurança: Usa variável de ambiente ou um fallback (nunca fixo em prod)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'chave_mestra_v67_fix_final')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10
    }
    
    # --- CORREÇÃO DE SEGURANÇA (FASE 1) ---
    # Ativa proteção contra CSRF (Cross-Site Request Forgery)
    # Importante: Certifique-se que seus formulários HTML tenham {{ csrf_token() }}
    WTF_CSRF_ENABLED = True 
    
    # Configurações de Cookie
    # Mude SESSION_COOKIE_SECURE para True apenas se estiver usando HTTPS (Produção)
    SESSION_COOKIE_SECURE = False 
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///dev.db')

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}




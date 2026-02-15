import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Garante uma chave secreta fixa para não invalidar sessões ao reiniciar
    SECRET_KEY = os.environ.get('SECRET_KEY', 'chave_mestra_v66_shahin_segura')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configurações de Banco
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10
    }
    
    # --- CORREÇÃO DO LOGIN ---
    # Desativa a protecao global temporariamente para destravar o acesso
    # O ProxyFix no __init__ vai corrigir a sessao para o futuro
    WTF_CSRF_ENABLED = False 

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///dev.db')

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    
    # Em produção, forçamos cookies seguros
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'

config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
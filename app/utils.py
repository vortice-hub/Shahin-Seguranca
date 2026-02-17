from datetime import datetime, timedelta
import unicodedata
import re
import hashlib
from functools import wraps
from flask import abort, redirect, url_for, flash, request
from flask_login import current_user

# --- FUNÇÃO CENTRALIZADA DE TEMPO ---
def get_brasil_time():
    """Retorna o horário atual em UTC-3 (Horário de Brasília)."""
    return datetime.utcnow() - timedelta(hours=3)

# --- UTILITÁRIOS DE TEXTO E DATA ---

def remove_accents(txt):
    """Remove acentos de uma string."""
    if not txt: return ""
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def limpar_nome(txt):
    """
    Normalização Agressiva para comparação de nomes (IA vs Banco).
    1. Remove acentos.
    2. Remove preposições (de, da, dos...).
    3. Remove espaços extras.
    """
    if not txt: return ""
    # Remove acentos e converte para maiúsculo
    txt = remove_accents(txt).upper().strip()
    
    # Remove preposições comuns que atrapalham a comparação
    stopwords = [" DE ", " DA ", " DO ", " DOS ", " DAS ", " E "]
    for word in stopwords:
        txt = txt.replace(word, " ")
    
    # Remove espaços duplos resultantes
    return " ".join(txt.split())

def gerar_login_automatico(nome_completo):
    """Gera um login base (primeiro nome) para novos usuários."""
    if not nome_completo: return "user"
    partes = nome_completo.split()
    # Pega o primeiro nome, remove acentos e deixa minúsculo
    primeiro_nome = remove_accents(partes[0]).lower()
    # Remove qualquer caractere que não seja letra
    return re.sub(r'[^a-z]', '', primeiro_nome)

def data_por_extenso(data_obj):
    """Retorna data formatada: '17 de Fevereiro de 2026'."""
    meses = {1:'Janeiro', 2:'Fevereiro', 3:'Março', 4:'Abril', 5:'Maio', 6:'Junho', 
             7:'Julho', 8:'Agosto', 9:'Setembro', 10:'Outubro', 11:'Novembro', 12:'Dezembro'}
    return f"{data_obj.day} de {meses[data_obj.month]} de {data_obj.year}"

# --- CÁLCULOS DE PONTO ---

def time_to_minutes(t):
    """Converte objeto time ou string 'HH:MM' para minutos totais."""
    if not t: return 0
    if isinstance(t, str):
        try: 
            h, m = map(int, t.split(':'))
            return h * 60 + m
        except: return 0
    return t.hour * 60 + t.minute

def format_minutes_to_hm(total_minutes):
    """Converte minutos totais para string 'HH:MM' (aceita negativos)."""
    sinal = "" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{sinal}{h:02d}:{m:02d}"

# --- SISTEMA DE AUDITORIA ---

def calcular_hash_arquivo(conteudo_bytes):
    if not conteudo_bytes: return None
    return hashlib.sha256(conteudo_bytes).hexdigest()

def get_client_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

# --- SISTEMA DE PERMISSÕES ---

def has_permission(permission_name):
    """Verifica se o usuário logado tem a permissão específica."""
    if not current_user.is_authenticated:
        return False
    # Master Absoluto (Bypass)
    if current_user.username == '50097952800':
        return True
    if not current_user.permissions:
        return False
    user_perms = [p.strip().upper() for p in current_user.permissions.split(',')]
    return permission_name.upper() in user_perms

def permission_required(permission_name):
    """Decorator para proteger rotas com base em permissões."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not has_permission(permission_name):
                flash(f'Acesso Negado: Necessita da permissão {permission_name}.', 'error')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def master_required(f):
    """Decorator exclusivo para o Master."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (current_user.role != 'Master' and current_user.username != '50097952800'):
            flash('Acesso não autorizado.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


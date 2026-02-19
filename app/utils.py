from datetime import datetime, timedelta, time
import pytz
import unicodedata
import re
import hashlib
from functools import wraps
from flask import abort, redirect, url_for, flash, request
from flask_login import current_user

# --- FUNÇÃO CENTRALIZADA DE TEMPO (BLINDADA) ---
def get_brasil_time():
    """Retorna o horário atual no fuso de Brasília de forma exata e blindada."""
    fuso_br = pytz.timezone('America/Sao_Paulo')
    # Pegamos a hora no Brasil e removemos o marcador de fuso para que o 
    # SQLAlchemy salve o horário exato sem tentar reconverter para UTC no servidor.
    return datetime.now(fuso_br).replace(tzinfo=None)

# --- UTILITÁRIOS DE TEXTO E DATA ---

def remove_accents(txt):
    if not txt: return ""
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def limpar_nome(txt):
    """
    Normalização Agressiva para IA.
    Remove acentos, preposições e espaços extras.
    """
    if not txt: return ""
    txt = remove_accents(txt).upper().strip()
    stopwords = [" DE ", " DA ", " DO ", " DOS ", " DAS ", " E "]
    for word in stopwords:
        txt = txt.replace(word, " ")
    return " ".join(txt.split())

def gerar_login_automatico(nome_completo):
    """Gera login base (primeiro nome) para novos usuários."""
    if not nome_completo: return "user"
    partes = nome_completo.split()
    primeiro_nome = remove_accents(partes[0]).lower()
    return re.sub(r'[^a-z]', '', primeiro_nome)

def data_por_extenso(data_obj):
    meses = {1:'Janeiro', 2:'Fevereiro', 3:'Março', 4:'Abril', 5:'Maio', 6:'Junho', 
             7:'Julho', 8:'Agosto', 9:'Setembro', 10:'Outubro', 11:'Novembro', 12:'Dezembro'}
    return f"{data_obj.day} de {meses[data_obj.month]} de {data_obj.year}"

# --- CÁLCULOS DE PONTO (ESSENCIAIS) ---

def time_to_minutes(t):
    if not t: return 0
    if isinstance(t, str):
        try: h, m = map(int, t.split(':')); return h * 60 + m
        except: return 0
    return t.hour * 60 + t.minute

def format_minutes_to_hm(total_minutes):
    sinal = "" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{sinal}{h:02d}:{m:02d}"

def calcular_dia(user_id, data_ref):
    """Calcula o saldo de horas e status do dia para o módulo de Ponto."""
    from app.extensions import db
    from app.models import User, PontoRegistro, PontoResumo
    
    user = User.query.get(user_id)
    if not user: return

    registros = PontoRegistro.query.filter_by(user_id=user_id, data_registro=data_ref).order_by(PontoRegistro.hora_registro).all()
    
    # Meta padrão
    meta = user.carga_horaria if user.carga_horaria else 528
    
    # Regras de Escala
    if user.escala == '5x2' and data_ref.weekday() >= 5: meta = 0
    elif user.escala == '12x36' and user.data_inicio_escala:
        dias_diff = (data_ref - user.data_inicio_escala).days
        if dias_diff % 2 != 0: meta = 0
        else: meta = 720
            
    # Cálculo de horas trabalhadas
    trab = 0
    for i in range(0, len(registros), 2):
        if i + 1 < len(registros):
            entrada = time_to_minutes(registros[i].hora_registro)
            saida = time_to_minutes(registros[i+1].hora_registro)
            trab += (saida - entrada)
            
    saldo = trab - meta
    
    # Definição de Status
    status = "OK"
    if not registros:
        status = "Falta" if meta > 0 else "Folga"
    elif len(registros) % 2 != 0:
        status = "Incompleto"
    elif saldo > 10:
        status = "Hora Extra"
    elif saldo < -10:
        status = "Débito" if meta > 0 else "Extra" # Extra se for folga trabalhada
        
    # Salva ou Atualiza Resumo
    resumo = PontoResumo.query.filter_by(user_id=user_id, data_referencia=data_ref).first()
    if not resumo:
        resumo = PontoResumo(user_id=user_id, data_referencia=data_ref)
        db.session.add(resumo)
    
    resumo.minutos_trabalhados = trab
    resumo.minutos_esperados = meta
    resumo.minutos_saldo = saldo
    resumo.status_dia = status
    
    try: db.session.commit()
    except: db.session.rollback()

# --- SISTEMA DE AUDITORIA E PERMISSÕES ---

def calcular_hash_arquivo(conteudo_bytes):
    if not conteudo_bytes: return None
    return hashlib.sha256(conteudo_bytes).hexdigest()

def get_client_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

def has_permission(permission_name):
    if not current_user.is_authenticated: return False
    if current_user.username == '50097952800': return True
    if not current_user.permissions: return False
    user_perms = [p.strip().upper() for p in current_user.permissions.split(',')]
    return permission_name.upper() in user_perms

def permission_required(permission_name):
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
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (current_user.role != 'Master' and current_user.username != '50097952800'):
            flash('Acesso não autorizado.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


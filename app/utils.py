from datetime import datetime, timedelta, time
import unicodedata
import re
import hashlib
from functools import wraps
from flask import abort, redirect, url_for, flash, request
from flask_login import current_user

# --- FUNÇÃO CENTRALIZADA DE TEMPO ---
def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

# --- SISTEMA DE AUDITORIA ---
def calcular_hash_arquivo(conteudo_bytes):
    if not conteudo_bytes: return None
    return hashlib.sha256(conteudo_bytes).hexdigest()

def get_client_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

# --- SISTEMA DE PERMISSÕES (NOVO) ---

def has_permission(permission_name):
    """
    Verifica se o utilizador atual tem uma permissão específica.
    Bypass automático para o utilizador Master 'Thaynara'.
    """
    if not current_user.is_authenticated:
        return False
    
    # Master Absoluto
    if current_user.username == 'Thaynara':
        return True
    
    # Se o utilizador não tem nenhuma permissão atribuída
    if not current_user.permissions:
        return False
        
    # Verifica se a chave está na string separada por vírgulas
    user_perms = [p.strip().upper() for p in current_user.permissions.split(',')]
    return permission_name.upper() in user_perms

def permission_required(permission_name):
    """
    Decorator para proteger rotas baseado em permissões específicas.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not has_permission(permission_name):
                flash(f'Acesso Negado: Necessita da permissão {permission_name}.', 'error')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Manter master_required para compatibilidade (funciona como um super-acesso)
def master_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (current_user.role != 'Master' and current_user.username != 'Thaynara'):
            flash('Acesso não autorizado.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# (As outras funções utilitárias permanecem iguais)
def data_por_extenso(data_obj):
    meses = {1:'Janeiro', 2:'Fevereiro', 3:'Março', 4:'Abril', 5:'Maio', 6:'Junho', 7:'Julho', 8:'Agosto', 9:'Setembro', 10:'Outubro', 11:'Novembro', 12:'Dezembro'}
    return f"{data_obj.day} de {meses[data_obj.month]} de {data_obj.year}"

def remove_accents(txt):
    if not txt: return ""
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def gerar_login_automatico(nome_completo):
    if not nome_completo: return "user"
    partes = nome_completo.split()
    primeiro_nome = remove_accents(partes[0]).lower()
    return re.sub(r'[^a-z]', '', primeiro_nome)

def time_to_minutes(t):
    if not t: return 0
    if isinstance(t, str):
        try: h, m = map(int, t.split(':')); return h * 60 + m
        except: return 0
    return t.hour * 60 + t.minute

def format_minutes_to_hm(total_minutes):
    sinal = "" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    h = total_minutes // 60; m = total_minutes % 60
    return f"{sinal}{h:02d}:{m:02d}"

def calcular_dia(user_id, data_ref):
    from app.extensions import db
    from app.models import User, PontoRegistro, PontoResumo
    user = User.query.get(user_id)
    if not user: return
    registros = PontoRegistro.query.filter_by(user_id=user_id, data_registro=data_ref).order_by(PontoRegistro.hora_registro).all()
    meta = user.carga_horaria if user.carga_horaria else 528
    if user.escala == '5x2' and data_ref.weekday() >= 5: meta = 0
    elif user.escala == '12x36' and user.data_inicio_escala:
        if (data_ref - user.data_inicio_escala).days % 2 != 0: meta = 0
        else: meta = 720
    trab = 0
    for i in range(0, len(registros), 2):
        if i + 1 < len(registros): trab += (time_to_minutes(registros[i+1].hora_registro) - time_to_minutes(registros[i].hora_registro))
    saldo = trab - meta
    status = "OK"
    if not registros: status = "Falta" if meta > 0 else "Folga"
    elif len(registros) % 2 != 0: status = "Incompleto"
    elif saldo > 10: status = "Hora Extra"
    elif saldo < -10: status = "Débito" if meta > 0 else "Extra"
    resumo = PontoResumo.query.filter_by(user_id=user_id, data_referencia=data_ref).first()
    if not resumo: resumo = PontoResumo(user_id=user_id, data_referencia=data_ref); db.session.add(resumo)
    resumo.minutos_trabalhados = trab; resumo.minutos_esperados = meta; resumo.minutos_saldo = saldo; resumo.status_dia = status
    try: db.session.commit()
    except: db.session.rollback()



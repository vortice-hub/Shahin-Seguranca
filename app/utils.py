from datetime import datetime, timedelta, time
import pytz
import unicodedata
import re
import hashlib
import os
import json
from functools import wraps
from flask import abort, redirect, url_for, flash, request
from flask_login import current_user

# Tenta importar o motor Push
try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None

def get_brasil_time():
    fuso_br = pytz.timezone('America/Sao_Paulo')
    return datetime.now(fuso_br).replace(tzinfo=None)

def remove_accents(txt):
    if not txt: return ""
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def limpar_nome(txt):
    if not txt: return ""
    txt = remove_accents(txt).upper().strip()
    stopwords = [" DE ", " DA ", " DO ", " DOS ", " DAS ", " E "]
    for word in stopwords:
        txt = txt.replace(word, " ")
    return " ".join(txt.split())

def gerar_login_automatico(nome_completo):
    if not nome_completo: return "user"
    partes = nome_completo.split()
    primeiro_nome = remove_accents(partes[0]).lower()
    return re.sub(r'[^a-z]', '', primeiro_nome)

def data_por_extenso(data_obj):
    meses = {1:'Janeiro', 2:'Fevereiro', 3:'Março', 4:'Abril', 5:'Maio', 6:'Junho', 
             7:'Julho', 8:'Agosto', 9:'Setembro', 10:'Outubro', 11:'Novembro', 12:'Dezembro'}
    return f"{data_obj.day} de {meses[data_obj.month]} de {data_obj.year}"

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

def calcular_hash_arquivo(conteudo_bytes):
    if not conteudo_bytes: return None
    return hashlib.sha256(conteudo_bytes).hexdigest()

def get_client_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

# ==============================================================================
# 🔐 MOTOR DE PERMISSÕES INTELIGENTE (RBAC)
# ==============================================================================

def has_permission(permission_name):
    if not current_user.is_authenticated: 
        return False
    
    # O Master da Vortice tem acesso total
    if str(current_user.username) == '50097952800' or current_user.role == 'Master': 
        return True

    if hasattr(current_user, 'cargo') and current_user.cargo:
        for perm in current_user.cargo.permissions:
            if perm.codigo.upper() == permission_name.upper():
                return True

    if current_user.permissions:
        user_perms = [p.strip().upper() for p in current_user.permissions.split(',')]
        return permission_name.upper() in user_perms

    return False

def permission_required(permission_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not has_permission(permission_name):
                flash(f'Acesso Negado: Permissão {permission_name} necessária.', 'error')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def master_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (current_user.role != 'Master' and str(current_user.username) != '50097952800'):
            flash('Acesso não autorizado.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    """Apenas para o Dono da Plataforma Vortice"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        PLATFORM_OWNER = '50097952800' 
        if not current_user.is_authenticated or str(current_user.username) != PLATFORM_OWNER:
            flash("Acesso restrito ao Administrador Vortice.", "error")
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def enviar_notificacao(user_id, mensagem, link=None):
    from app.extensions import db
    from app.models import Notificacao, PushSubscription
    try:
        nova_notif = Notificacao(user_id=user_id, mensagem=mensagem, link=link, lida=False, data_criacao=get_brasil_time())
        db.session.add(nova_notif)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return False
    if not webpush: return True
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY')
    VAPID_CLAIM_EMAIL = 'mailto:contato@vortice.com.br' 
    if not VAPID_PRIVATE_KEY: return True
    subs = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subs: return True 
    payload = json.dumps({"title": "Vortice SaaS", "body": mensagem, "url": link or "/"})
    for sub in subs:
        try:
            sub_info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
            webpush(subscription_info=sub_info, data=payload, vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims={"sub": VAPID_CLAIM_EMAIL})
        except WebPushException as e:
            if e.response is not None and e.response.status_code == 410:
                db.session.delete(sub)
                db.session.commit()
    return True


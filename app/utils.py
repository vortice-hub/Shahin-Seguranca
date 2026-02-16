from datetime import datetime, timedelta, time
import unicodedata
import re
import hashlib
from functools import wraps
from flask import abort, redirect, url_for, flash, request
from flask_login import current_user

# --- FUNÇÃO CENTRALIZADA DE TEMPO ---
def get_brasil_time():
    """Retorna o horário atual em UTC-3 (Brasil)."""
    return datetime.utcnow() - timedelta(hours=3)

# --- FUNÇÕES DE AUDITORIA E SEGURANÇA (NOVAS) ---
def calcular_hash_arquivo(conteudo_bytes):
    """Gera uma assinatura única (SHA-256) para o arquivo."""
    if not conteudo_bytes: return None
    return hashlib.sha256(conteudo_bytes).hexdigest()

def get_client_ip():
    """
    Captura o IP real do usuário, mesmo atrás de proxies (Nginx/Render).
    """
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

# --- DECORATOR DE PERMISSÃO ---
def master_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'Master':
            flash('Acesso não autorizado.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def data_por_extenso(data_obj):
    meses = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
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
        try:
            h, m = map(int, t.split(':'))
            return h * 60 + m
        except: return 0
    return t.hour * 60 + t.minute

def format_minutes_to_hm(total_minutes):
    sinal = "" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{sinal}{h:02d}:{m:02d}"

def calcular_dia(user_id, data_ref):
    from app.extensions import db
    from app.models import User, PontoRegistro, PontoResumo
    
    user = User.query.get(user_id)
    if not user: return

    registros = PontoRegistro.query.filter_by(
        user_id=user_id, 
        data_registro=data_ref
    ).order_by(PontoRegistro.hora_registro).all()
    
    # Meta Flexível
    meta_minutos = user.carga_horaria if user.carga_horaria else 528
    
    if user.escala == '5x2' and data_ref.weekday() >= 5:
        meta_minutos = 0
    elif user.escala == '12x36' and user.data_inicio_escala:
        dias_diff = (data_ref - user.data_inicio_escala).days
        if dias_diff % 2 != 0: meta_minutos = 0
        else: meta_minutos = 720
    
    trabalhado_total = 0
    qtd_batidas = len(registros)
    
    for i in range(0, qtd_batidas, 2):
        if i + 1 < qtd_batidas:
            entrada = time_to_minutes(registros[i].hora_registro)
            saida = time_to_minutes(registros[i+1].hora_registro)
            trabalhado_total += (saida - entrada)

    saldo = trabalhado_total - meta_minutos
    
    status = "OK"
    if qtd_batidas == 0:
        status = "Falta" if meta_minutos > 0 else "Folga"
    elif qtd_batidas % 2 != 0:
        status = "Incompleto"
    elif saldo > 10:
        status = "Hora Extra"
    elif saldo < -10:
        status = "Débito" if meta_minutos > 0 else "Extra"
    
    resumo = PontoResumo.query.filter_by(user_id=user_id, data_referencia=data_ref).first()
    if not resumo:
        resumo = PontoResumo(user_id=user_id, data_referencia=data_ref)
        db.session.add(resumo)
    
    resumo.minutos_trabalhados = trabalhado_total
    resumo.minutos_esperados = meta_minutos
    resumo.minutos_saldo = saldo
    resumo.status_dia = status
    
    try:
        db.session.commit()
    except:
        db.session.rollback()




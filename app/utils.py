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

# Tenta importar o motor Push (se não estiver instalado, o sistema não quebra, apenas guarda no sininho)
try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None

# --- FUNÇÃO CENTRALIZADA DE TEMPO (BLINDADA) ---
def get_brasil_time():
    """Retorna o horário atual no fuso de Brasília de forma exata e blindada."""
    fuso_br = pytz.timezone('America/Sao_Paulo')
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
    
    meta = user.carga_horaria if user.carga_horaria else 528
    
    if user.escala == '5x2' and data_ref.weekday() >= 5: meta = 0
    elif user.escala == '12x36' and user.data_inicio_escala:
        dias_diff = (data_ref - user.data_inicio_escala).days
        if dias_diff % 2 != 0: meta = 0
        else: meta = 720
            
    trab = 0
    for i in range(0, len(registros), 2):
        if i + 1 < len(registros):
            entrada = time_to_minutes(registros[i].hora_registro)
            saida = time_to_minutes(registros[i+1].hora_registro)
            trab += (saida - entrada)
            
    saldo = trab - meta
    
    status = "OK"
    if not registros:
        status = "Falta" if meta > 0 else "Folga"
    elif len(registros) % 2 != 0:
        status = "Incompleto"
    elif saldo > 10:
        status = "Hora Extra"
    elif saldo < -10:
        status = "Débito" if meta > 0 else "Extra" 
        
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

# ============================================================================
# FASE 4: O MOTOR DE NOTIFICAÇÕES (SININHO + PUSH NATIVO NO ECRÃ)
# ============================================================================
def enviar_notificacao(user_id, mensagem, link=None):
    """Envia um alerta interno para o Sininho do utilizador e um Push para o telemóvel."""
    from app.extensions import db
    from app.models import Notificacao, PushSubscription
    
    # 1. Guarda a notificação na Caixa de Entrada (Sininho) do sistema
    try:
        nova_notif = Notificacao(
            user_id=user_id,
            mensagem=mensagem,
            link=link,
            lida=False,
            data_criacao=get_brasil_time()
        )
        db.session.add(nova_notif)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[Shahin Push] Erro ao salvar notificação no banco: {e}")
        return False

    # 2. Dispara o Push Nativo para acordar o telemóvel do funcionário
    if not webpush:
        print("[Shahin Push] Aviso: Biblioteca 'pywebpush' não instalada. Apenas notificação web gerada.")
        return True # Retorna True porque salvou no sininho com sucesso

    # Puxa a chave privada de segurança que vamos configurar no Cloud Run
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY')
    VAPID_CLAIM_EMAIL = 'mailto:contato@shahin.com.br' # Um email padrão obrigatório pelas regras da Web

    if not VAPID_PRIVATE_KEY:
        print("[Shahin Push] Aviso: VAPID_PRIVATE_KEY não configurada no ambiente. Push não disparado.")
        return True

    # Procura todos os telemóveis autorizados deste funcionário
    subs = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subs:
        return True # O utilizador ainda não clicou em "Ativar Alertas"

    payload = json.dumps({
        "title": "Shahin Gestão",
        "body": mensagem,
        "url": link or "/"
    })

    for sub in subs:
        try:
            sub_info = {
                "endpoint": sub.endpoint,
                "keys": {
                    "p256dh": sub.p256dh,
                    "auth": sub.auth
                }
            }
            # A Magia Acontece Aqui: Disparo encriptado!
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL}
            )
        except WebPushException as e:
            print(f"[Shahin Push] Falha ao enviar para telemóvel: {e}")
            # Se a Google/Apple disserem que o telemóvel desinstalou o app (Erro 410), nós limpamos a morada
            if e.response is not None and e.response.status_code == 410:
                db.session.delete(sub)
                db.session.commit()
        except Exception as e:
            print(f"[Shahin Push] Erro inesperado no disparo: {e}")

    return True


from datetime import datetime, timedelta, time
import unicodedata
import re
from functools import wraps
from flask import abort, redirect, url_for, flash
from flask_login import current_user

# --- FUNÇÃO CENTRALIZADA DE TEMPO ---
def get_brasil_time():
    """Retorna o horário atual em UTC-3 (Brasil)."""
    return datetime.utcnow() - timedelta(hours=3)

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
    """Converte objeto time ou string 'HH:MM' para minutos inteiros."""
    if not t: return 0
    if isinstance(t, str):
        try:
            h, m = map(int, t.split(':'))
            return h * 60 + m
        except: return 0
    return t.hour * 60 + t.minute

def format_minutes_to_hm(total_minutes):
    """Converte minutos inteiros para string 'HH:MM' ou '-HH:MM'."""
    sinal = "" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{sinal}{h:02d}:{m:02d}"

# --- NOVA LÓGICA DE CÁLCULO (JORNADA FLEXÍVEL) ---
def calcular_dia(user_id, data_ref):
    from app.extensions import db
    from app.models import User, PontoRegistro, PontoResumo
    
    user = User.query.get(user_id)
    if not user: return

    # 1. Busca todas as batidas do dia ordenadas
    registros = PontoRegistro.query.filter_by(
        user_id=user_id, 
        data_registro=data_ref
    ).order_by(PontoRegistro.hora_registro).all()
    
    # 2. Definição da Meta do Dia
    # Se for Fim de Semana e escala for 5x2, meta é 0.
    meta_minutos = user.carga_horaria if user.carga_horaria else 528 # Padrão 8h48
    
    if user.escala == '5x2' and data_ref.weekday() >= 5:
        meta_minutos = 0
    elif user.escala == '12x36':
        # Lógica simplificada para 12x36 (Dia sim/Dia não baseada na data de início)
        if user.data_inicio_escala:
            dias_diff = (data_ref - user.data_inicio_escala).days
            if dias_diff % 2 != 0: # Dia de folga
                meta_minutos = 0
            else:
                meta_minutos = 720 # 12 horas
    
    # 3. Cálculo do Tempo Trabalhado (Pares)
    trabalhado_total = 0
    qtd_batidas = len(registros)
    
    # Itera de 2 em 2 (Entrada -> Saída)
    for i in range(0, qtd_batidas, 2):
        if i + 1 < qtd_batidas:
            entrada = time_to_minutes(registros[i].hora_registro)
            saida = time_to_minutes(registros[i+1].hora_registro)
            trabalhado_total += (saida - entrada)

    # 4. Cálculo do Saldo
    saldo = trabalhado_total - meta_minutos
    
    # 5. Definição do Status
    status = "OK"
    
    if qtd_batidas == 0:
        status = "Falta" if meta_minutos > 0 else "Folga"
    elif qtd_batidas % 2 != 0:
        status = "Incompleto" # Esqueceu de bater a saída
    elif saldo > 10: # Tolerância de 10 min
        status = "Hora Extra"
    elif saldo < -10: # Tolerância de 10 min
        status = "Débito" if meta_minutos > 0 else "Extra (Folga)"
    
    # 6. Salva/Atualiza Resumo
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
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao calcular dia: {e}")




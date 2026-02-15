from datetime import datetime, timedelta, time
from app.models import db, PontoRegistro, PontoResumo, User
import unicodedata
import re

def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

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
    from app.models import User, PontoRegistro, PontoResumo
    user = User.query.get(user_id)
    if not user: return

    registros = PontoRegistro.query.filter_by(user_id=user_id, data_registro=data_ref).order_by(PontoRegistro.hora_registro).all()
    
    ent_prev = time_to_minutes(user.horario_entrada)
    sai_prev = time_to_minutes(user.horario_saida)
    alm_ini_prev = time_to_minutes(user.horario_almoco_inicio)
    alm_fim_prev = time_to_minutes(user.horario_almoco_fim)
    
    minutos_esperados = (sai_prev - ent_prev) - (alm_fim_prev - alm_ini_prev)
    if minutos_esperados < 0: minutos_esperados = 0
    
    if data_ref.weekday() >= 5 and user.escala != 'Livre':
        minutos_esperados = 0

    trabalhado_total = 0
    for i in range(0, len(registros), 2):
        if i + 1 < len(registros):
            inicio = time_to_minutes(registros[i].hora_registro)
            fim = time_to_minutes(registros[i+1].hora_registro)
            trabalhado_total += (fim - inicio)

    saldo = trabalhado_total - minutos_esperados
    
    status = "OK"
    if len(registros) == 0 and minutos_esperados > 0: status = "Falta"
    elif len(registros) % 2 != 0: status = "Incompleto"
    elif saldo > 0: status = "Hora Extra"
    elif saldo < 0: status = "Débito"

    resumo = PontoResumo.query.filter_by(user_id=user_id, data_referencia=data_ref).first()
    if not resumo:
        resumo = PontoResumo(user_id=user_id, data_referencia=data_ref)
        db.session.add(resumo)
    
    resumo.minutos_trabalhados = trabalhado_total
    resumo.minutos_esperados = minutos_esperados
    resumo.minutos_saldo = saldo
    resumo.status_dia = status
    
    try:
        db.session.commit()
    except:
        db.session.rollback()
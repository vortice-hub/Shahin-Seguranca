from datetime import datetime, timedelta, time
from app.models import db, PontoRegistro, PontoResumo, User
from app import logger

def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

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
    registros = PontoRegistro.query.filter_by(user_id=user_id, data_registro=data_ref).order_by(PontoRegistro.hora_registro).all()
    
    # Horários previstos em minutos
    ent_prev = time_to_minutes(user.horario_entrada)
    sai_prev = time_to_minutes(user.horario_saida)
    alm_ini_prev = time_to_minutes(user.horario_almoco_inicio)
    alm_fim_prev = time_to_minutes(user.horario_almoco_fim)
    
    minutos_esperados = (sai_prev - ent_prev) - (alm_fim_prev - alm_ini_prev)
    if minutos_esperados < 0: minutos_esperados = 0
    
    # Se for fim de semana e escala não for Livre/Final de Semana, esperado é 0
    if data_ref.weekday() >= 5 and user.escala != 'Livre':
        minutos_esperados = 0

    trabalhado_total = 0
    # Lógica de pares de batidas (Entrada 1 -> Saída 1, Entrada 2 -> Saída 2)
    for i in range(0, len(registros), 2):
        if i + 1 < len(registros):
            inicio = time_to_minutes(registros[i].hora_registro)
            fim = time_to_minutes(registros[i+1].hora_registro)
            trabalhado_total += (fim - inicio)

    saldo = trabalhado_total - minutos_esperados
    
    status = "OK"
    if len(registros) % 2 != 0: status = "Incompleto"
    elif trabalhado_total == 0 and minutos_esperados > 0: status = "Falta"
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
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao salvar resumo: {e}")

def remove_accents(txt):
    if not txt: return ""
    import unicodedata
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')
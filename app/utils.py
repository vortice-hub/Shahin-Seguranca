from datetime import datetime, timedelta, time
from app import db
from app.models import User, PontoRegistro, PontoResumo
import unicodedata
import random

def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

def data_por_extenso(data_obj):
    meses = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    return f"{data_obj.day} de {meses[data_obj.month]} de {data_obj.year}"

def remove_accents(input_str):
    if not input_str: return ""
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def gerar_login_automatico(nome_completo):
    try:
        clean_name = remove_accents(nome_completo).lower().strip()
        parts = clean_name.split()
        if not parts: return f"user.{random.randint(10,99)}"
        primeiro = parts[0]
        ultimo = parts[-1] if len(parts) > 1 else "colab"
        for _ in range(10): 
            num = random.randint(10, 99)
            login_candidato = f"{primeiro}.{ultimo}.{num}"
            if not User.query.filter_by(username=login_candidato).first():
                return login_candidato
        return f"{primeiro}.{random.randint(1000,9999)}"
    except:
        return f"user.{random.randint(1000,9999)}"

def time_to_min(t_input):
    if not t_input: return 0
    try:
        if isinstance(t_input, time): return t_input.hour * 60 + t_input.minute
        h, m = map(int, str(t_input).split(':')[:2]); return h * 60 + m
    except: return 0

def calcular_dia(user_id, data_ref):
    user = User.query.get(user_id)
    if not user: return
    
    dia_trabalho = True
    if user.escala == '5x2' and data_ref.weekday() >= 5: dia_trabalho = False
    elif user.escala == '12x36' and user.data_inicio_escala:
        if (data_ref - user.data_inicio_escala).days % 2 != 0: dia_trabalho = False
            
    if dia_trabalho:
        m_ent = time_to_min(user.horario_entrada)
        m_alm_ini = time_to_min(user.horario_almoco_inicio)
        m_alm_fim = time_to_min(user.horario_almoco_fim)
        m_sai = time_to_min(user.horario_saida)
        jornada_esperada = max(0, m_alm_ini - m_ent) + max(0, m_sai - m_alm_fim)
        if jornada_esperada <= 0: jornada_esperada = 480
    else: jornada_esperada = 0

    pontos = PontoRegistro.query.filter_by(user_id=user_id, data_registro=data_ref).order_by(PontoRegistro.hora_registro).all()
    trabalhado_minutos = 0
    status = "OK"
    saldo = 0
    
    if len(pontos) < 2:
        if len(pontos) == 0:
            if dia_trabalho: status = "Falta"; saldo = -jornada_esperada
            else: status = "Folga"; saldo = 0
    else:
        loops = len(pontos)
        if loops % 2 != 0: status = "Erro: Ímpar"; loops -= 1
        for i in range(0, loops, 2):
            p_ent = time_to_min(pontos[i].hora_registro)
            p_sai = time_to_min(pontos[i+1].hora_registro)
            trabalhado_minutos += (p_sai - p_ent)
        saldo = trabalhado_minutos - jornada_esperada
        if not dia_trabalho and trabalhado_minutos > 0: status = "Hora Extra (Folga)"; saldo = trabalhado_minutos
        else:
            if abs(saldo) <= 10: saldo = 0; status = "Normal"
            elif saldo > 0: status = "Hora Extra"
            elif saldo < 0: status = "Atraso/Débito"

    resumo = PontoResumo.query.filter_by(user_id=user_id, data_referencia=data_ref).first()
    if not resumo: resumo = PontoResumo(user_id=user_id, data_referencia=data_ref); db.session.add(resumo)
    resumo.minutos_trabalhados = trabalhado_minutos; resumo.minutos_esperados = jornada_esperada; resumo.minutos_saldo = saldo; resumo.status_dia = status
    db.session.commit()
import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V59: Fix ImportError - Restaurando gerar_login_automatico e estabilidade"

# --- 1. APP/UTILS.PY (COMPLETO E REVISADO) ---
FILE_UTILS = """
from datetime import datetime, timedelta, time
from app.models import db, PontoRegistro, PontoResumo, User
import unicodedata
import re

def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

def remove_accents(txt):
    if not txt: return ""
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def gerar_login_automatico(nome_completo):
    # Pega o primeiro nome, remove acentos e deixa minusculo
    partes = nome_completo.split()
    primeiro_nome = remove_accents(partes[0]).lower()
    # Remove caracteres especiais
    primeiro_nome = re.sub(r'[^a-z]', '', primeiro_nome)
    return primeiro_nome

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
    
    # Horários previstos
    ent_prev = time_to_minutes(user.horario_entrada)
    sai_prev = time_to_minutes(user.horario_saida)
    alm_ini_prev = time_to_minutes(user.horario_almoco_inicio)
    alm_fim_prev = time_to_minutes(user.horario_almoco_fim)
    
    minutos_esperados = (sai_prev - ent_prev) - (alm_fim_prev - alm_ini_prev)
    if minutos_esperados < 0: minutos_esperados = 0
    
    # Regra de Escala
    if data_ref.weekday() >= 5 and user.escala != 'Livre':
        minutos_esperados = 0

    trabalhado_total = 0
    # Cálculo por pares
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
"""

# --- FUNÇÕES DE SISTEMA ---
def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f: f.write(content.strip())
    print(f"Atualizado: {path}")

def git_update():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO V59! SISTEMA DE LOGIN RESTAURADO E DEPLOY LIBERADO <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V59 FIX: {PROJECT_NAME} ---")
    write_file("app/utils.py", FILE_UTILS)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



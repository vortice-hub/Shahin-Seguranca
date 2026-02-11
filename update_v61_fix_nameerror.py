import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V61: Fix NameError - Importando func do sqlalchemy em ponto.py"

# --- 1. APP/ROUTES/PONTO.PY (CORRIGIDO) ---
FILE_BP_PONTO = """
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import PontoRegistro, PontoResumo, User
from app.utils import get_brasil_time, calcular_dia, format_minutes_to_hm
from datetime import datetime, date
from sqlalchemy import func # IMPORTANTE: Adicionado para corrigir o erro 500

ponto_bp = Blueprint('ponto', __name__, url_prefix='/ponto')

@ponto_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    hoje = get_brasil_time().date()
    if request.method == 'POST':
        tipo = request.form.get('tipo')
        lat = request.form.get('lat'); lon = request.form.get('lon')
        novo = PontoRegistro(user_id=current_user.id, data_registro=hoje, tipo=tipo, latitude=lat, longitude=lon)
        db.session.add(novo); db.session.commit()
        calcular_dia(current_user.id, hoje)
        flash(f'Ponto de {tipo} registrado!')
        return redirect(url_for('main.dashboard'))
    registros = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).all()
    return render_template('registrar_ponto.html', registros=registros)

@ponto_bp.route('/espelho')
@login_required
def espelho_ponto():
    # Se for Master, pode passar user_id pela URL para auditar outros
    target_user_id = request.args.get('user_id', type=int) or current_user.id
    if target_user_id != current_user.id and current_user.role != 'Master':
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(target_user_id)
    mes_ref = request.args.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    try:
        ano, mes = map(int, mes_ref.split('-'))
    except:
        hoje = get_brasil_time()
        ano, mes = hoje.year, hoje.month
        mes_ref = hoje.strftime('%Y-%m')
    
    resumos = PontoResumo.query.filter(
        PontoResumo.user_id == target_user_id,
        func.extract('year', PontoResumo.data_referencia) == ano,
        func.extract('month', PontoResumo.data_referencia) == mes
    ).order_by(PontoResumo.data_referencia).all()
    
    # Detalhes de batidas para cada dia para o Master ver
    detalhes = {}
    for r in resumos:
        batidas = PontoRegistro.query.filter_by(user_id=target_user_id, data_registro=r.data_referencia).order_by(PontoRegistro.hora_registro).all()
        detalhes[r.id] = [b.hora_registro.strftime('%H:%M') for b in batidas]

    return render_template('ponto_espelho.html', resumos=resumos, user=user, detalhes=detalhes, format_hm=format_minutes_to_hm, mes_ref=mes_ref)

@ponto_bp.route('/solicitar-ajuste', methods=['GET', 'POST'])
@login_required
def solicitar_ajuste():
    # Rota básica para evitar erro de link quebrado, pode ser expandida depois
    return render_template('solicitar_ajuste.html')
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
        print("\n>>> SUCESSO V61! NAMEERROR CORRIGIDO <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V61 FIX: {PROJECT_NAME} ---")
    write_file("app/routes/ponto.py", FILE_BP_PONTO)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



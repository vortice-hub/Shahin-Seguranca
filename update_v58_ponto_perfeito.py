import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V58: Correcao do Calculo de Horas e Link de Auditoria no Relatorio"

# --- 1. APP/UTILS.PY (Lógica de Cálculo Refatorada) ---
FILE_UTILS = """
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
"""

# --- 2. APP/ROUTES/ADMIN.PY (Ajuste para receber user_id no espelho) ---
FILE_BP_ADMIN = """
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, PreCadastro, PontoResumo, PontoAjuste, PontoRegistro
from app.utils import calcular_dia, get_brasil_time, format_minutes_to_hm
import secrets
import csv
import io
from datetime import datetime, time
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/relatorio-folha', methods=['GET', 'POST'])
@login_required
def admin_relatorio_folha():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    mes_ref = request.form.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    try: ano, mes = map(int, mes_ref.split('-'))
    except: hoje = get_brasil_time(); ano, mes = hoje.year, hoje.month; mes_ref = hoje.strftime('%Y-%m')
    
    users = User.query.order_by(User.real_name).all()
    relatorio = []
    for u in users:
        resumos = PontoResumo.query.filter(
            PontoResumo.user_id == u.id, 
            func.extract('year', PontoResumo.data_referencia) == ano, 
            func.extract('month', PontoResumo.data_referencia) == mes
        ).all()
        total_saldo = sum(r.minutos_saldo for r in resumos)
        relatorio.append({
            'id': u.id,
            'nome': u.real_name,
            'cargo': u.role,
            'saldo_formatado': format_minutes_to_hm(total_saldo),
            'sinal': 'text-emerald-600' if total_saldo >= 0 else 'text-red-600'
        })
    return render_template('admin_relatorio_folha.html', relatorio=relatorio, mes_ref=mes_ref)

@admin_bp.route('/usuarios/importar-csv', methods=['GET', 'POST'])
@login_required
def importar_csv():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        file = request.files.get('arquivo_csv')
        if not file: return redirect(url_for('admin.importar_csv'))
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream, delimiter=';')
            count = 0
            for row in csv_reader:
                cpf_limpo = row.get('CPF', '').replace('.', '').replace('-', '').strip()
                if not cpf_limpo: continue
                if PreCadastro.query.filter_by(cpf=cpf_limpo).first() or User.query.filter_by(cpf=cpf_limpo).first(): continue
                pre = PreCadastro(
                    cpf=cpf_limpo,
                    nome_previsto=row.get('Nome', 'Funcionario'),
                    cargo=row.get('Cargo', 'Colaborador'),
                    salario=float(row.get('Salario', 0).replace(',', '.') or 0),
                    horario_entrada=row.get('Entrada', '07:12'),
                    horario_saida=row.get('Saida', '17:00'),
                    horario_almoco_inicio='12:00', horario_almoco_fim='13:00', escala='5x2'
                )
                db.session.add(pre); count += 1
            db.session.commit()
            flash(f'Importados {count} CPFs.')
        except Exception as e: flash(f'Erro: {e}')
    return render_template('admin_importar_csv.html')

@admin_bp.route('/usuarios')
@login_required
def gerenciar_usuarios():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    users = User.query.all(); pendentes = PreCadastro.query.all()
    return render_template('admin_usuarios.html', users=users, pendentes=pendentes)

@admin_bp.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        try:
            acao = request.form.get('acao')
            if acao == 'excluir':
                if user.username == 'Thaynara': flash('Erro.')
                else: 
                    PontoRegistro.query.filter_by(user_id=user.id).delete(); db.session.delete(user); db.session.commit()
                return redirect(url_for('admin.gerenciar_usuarios'))
            user.real_name = request.form.get('real_name'); user.role = request.form.get('role')
            user.salario = float(request.form.get('salario') or 0); user.horario_entrada = request.form.get('h_ent')
            user.horario_almoco_inicio = request.form.get('h_alm_ini'); user.horario_almoco_fim = request.form.get('h_alm_fim')
            user.horario_saida = request.form.get('h_sai'); user.escala = request.form.get('escala')
            db.session.commit(); flash('Salvo.'); return redirect(url_for('admin.gerenciar_usuarios'))
        except Exception as e: flash(f'Erro: {e}')
    return render_template('editar_usuario.html', user=user)

@admin_bp.route('/solicitacoes', methods=['GET', 'POST'])
@login_required
def admin_solicitacoes():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    pendentes = PontoAjuste.query.filter_by(status='Pendente').all()
    return render_template('admin_solicitacoes.html', solicitacoes=pendentes)
"""

# --- 3. APP/TEMPLATES/ADMIN_RELATORIO_FOLHA.HTML (Link no Nome) ---
FILE_TPL_RELATORIO = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6 flex justify-between items-center">
    <h2 class="text-2xl font-bold text-slate-800">Relatório de Folha</h2>
    <form action="/admin/relatorio-folha" method="POST" class="flex gap-2">
        <input type="month" name="mes_ref" value="{{ mes_ref }}" class="p-2 rounded-lg border border-slate-200 text-sm">
        <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded-lg font-bold text-sm">Filtrar</button>
    </form>
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <table class="w-full text-left text-sm">
        <thead class="bg-slate-50 text-slate-400 font-bold text-xs uppercase border-b border-slate-100">
            <tr>
                <th class="px-6 py-4">Funcionário</th>
                <th class="px-6 py-4">Cargo</th>
                <th class="px-6 py-4 text-center">Saldo do Mês</th>
                <th class="px-6 py-4 text-right">Ação</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
            {% for item in relatorio %}
            <tr class="hover:bg-slate-50 transition">
                <td class="px-6 py-4">
                    <!-- Drill-down: Link para o espelho do funcionario -->
                    <a href="/ponto/espelho?user_id={{ item.id }}&mes_ref={{ mes_ref }}" class="font-bold text-blue-600 hover:underline">
                        {{ item.nome }}
                    </a>
                </td>
                <td class="px-6 py-4 text-slate-500">{{ item.cargo }}</td>
                <td class="px-6 py-4 text-center font-mono font-bold {{ item.sinal }}">{{ item.saldo_formatado }}</td>
                <td class="px-6 py-4 text-right">
                    <a href="/ponto/espelho?user_id={{ item.id }}&mes_ref={{ mes_ref }}" class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-600 px-3 py-1 rounded-full transition">
                        Auditar Ponto
                    </a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""

# --- 4. APP/ROUTES/PONTO.PY (Ajuste para Espelho aceitar user_id) ---
FILE_BP_PONTO = """
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import PontoRegistro, PontoResumo, User
from app.utils import get_brasil_time, calcular_dia, format_minutes_to_hm
from datetime import datetime, date

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
    ano, mes = map(int, mes_ref.split('-'))
    
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
"""

# --- 5. APP/TEMPLATES/PONTO_ESPELHO.HTML (Melhoria Visual e Detalhes) ---
FILE_TPL_ESPELHO = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6 flex justify-between items-center">
    <div>
        <h2 class="text-2xl font-bold text-slate-800">Espelho de Ponto</h2>
        <p class="text-sm text-slate-500">Colaborador: <span class="font-bold text-slate-700">{{ user.real_name }}</span></p>
    </div>
    <div class="text-right">
        <span class="text-xs font-bold text-slate-400 uppercase">Período</span>
        <div class="font-bold text-slate-700">{{ mes_ref }}</div>
    </div>
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
            <thead class="bg-slate-50 text-slate-400 font-bold text-xs uppercase border-b border-slate-100">
                <tr>
                    <th class="px-4 py-4">Data</th>
                    <th class="px-4 py-4">Batidas Realizadas</th>
                    <th class="px-4 py-4 text-center">Trabalhado</th>
                    <th class="px-4 py-4 text-center">Saldo</th>
                    <th class="px-4 py-4 text-right">Status</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
                {% for r in resumos %}
                <tr class="hover:bg-slate-50 transition cursor-help" onclick="toggleDetails('det-{{ r.id }}')">
                    <td class="px-4 py-4 font-medium text-slate-700">{{ r.data_referencia.strftime('%d/%m (%a)') }}</td>
                    <td class="px-4 py-4">
                        <div class="flex flex-wrap gap-1">
                            {% for b in detalhes[r.id] %}
                            <span class="bg-slate-100 text-slate-600 px-2 py-0.5 rounded text-[10px] font-bold border border-slate-200">{{ b }}</span>
                            {% endfor %}
                        </div>
                    </td>
                    <td class="px-4 py-4 text-center font-mono">{{ format_hm(r.minutos_trabalhados) }}</td>
                    <td class="px-4 py-4 text-center font-mono font-bold {% if r.minutos_saldo >= 0 %} text-emerald-600 {% else %} text-red-500 {% endif %}">
                        {{ format_hm(r.minutos_saldo) }}
                    </td>
                    <td class="px-4 py-4 text-right">
                        <span class="text-[10px] font-bold uppercase px-2 py-1 rounded-full 
                            {% if r.status_dia == 'OK' %} bg-emerald-50 text-emerald-600 
                            {% elif r.status_dia == 'Incompleto' %} bg-amber-50 text-amber-600 
                            {% elif r.status_dia == 'Falta' %} bg-red-50 text-red-600 
                            {% else %} bg-blue-50 text-blue-600 {% endif %}">
                            {{ r.status_dia }}
                        </span>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
<div class="mt-4 text-center text-xs text-slate-400">
    <i class="fas fa-info-circle mr-1"></i> Batidas ímpares são marcadas como "Incompleto" e não somam horas.
</div>
{% endblock %}
"""

# --- FUNÇÕES ---
def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f: f.write(content.strip())
    print(f"Atualizado: {path}")

def git_update():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO V58! PONTO PRECISO E DRILL-DOWN ATIVADO <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V58 PRECISAO: {PROJECT_NAME} ---")
    write_file("app/utils.py", FILE_UTILS)
    write_file("app/routes/admin.py", FILE_BP_ADMIN)
    write_file("app/routes/ponto.py", FILE_BP_PONTO)
    write_file("app/templates/admin_relatorio_folha.html", FILE_TPL_RELATORIO)
    write_file("app/templates/ponto_espelho.html", FILE_TPL_ESPELHO)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V68: Fix Variavel Hoje no Ponto e Menu Exclusivo para Terminal"

# --- 1. APP/ROUTES/PONTO.PY (Corrigindo envio da variável 'hoje') ---
FILE_BP_PONTO = """
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import PontoRegistro, PontoResumo, User, PontoAjuste
from app.utils import get_brasil_time, calcular_dia, format_minutes_to_hm, data_por_extenso
from datetime import datetime, date
from sqlalchemy import func
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

ponto_bp = Blueprint('ponto', __name__, url_prefix='/ponto')

# --- API QR CODE ---
@ponto_bp.route('/api/gerar-token', methods=['GET'])
@login_required
def gerar_token_qrcode():
    if current_user.role == 'Terminal': return jsonify({'error': 'Terminal não gera token'}), 403
    s = URLSafeTimedSerializer(current_app.secret_key)
    token = s.dumps({'user_id': current_user.id, 'timestamp': get_brasil_time().timestamp()})
    return jsonify({'token': token})

@ponto_bp.route('/api/registrar-leitura', methods=['POST'])
@login_required
def registrar_leitura_terminal():
    if current_user.role != 'Terminal' and current_user.role != 'Master': return jsonify({'error': 'Acesso negado.'}), 403
    data = request.json
    token = data.get('token')
    if not token: return jsonify({'error': 'Token vazio'}), 400
    s = URLSafeTimedSerializer(current_app.secret_key)
    try:
        dados = s.loads(token, max_age=35)
        user_alvo = User.query.get(dados['user_id'])
        if not user_alvo: return jsonify({'error': 'Usuário inválido'}), 404
        
        hoje = get_brasil_time().date()
        pontos_hoje = PontoRegistro.query.filter_by(user_id=user_alvo.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
        proxima = "Entrada"
        if len(pontos_hoje) == 1: proxima = "Ida Almoço"
        elif len(pontos_hoje) == 2: proxima = "Volta Almoço"
        elif len(pontos_hoje) == 3: proxima = "Saída"
        elif len(pontos_hoje) >= 4: proxima = "Extra"
        
        novo = PontoRegistro(user_id=user_alvo.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=proxima, latitude='QR-Code', longitude='Presencial')
        db.session.add(novo); db.session.commit(); calcular_dia(user_alvo.id, hoje)
        return jsonify({'success': True, 'message': f'Ponto registrado: {proxima}', 'funcionario': user_alvo.real_name, 'hora': novo.hora_registro.strftime('%H:%M')})
    except SignatureExpired: return jsonify({'error': 'QR Code expirado.'}), 400
    except BadSignature: return jsonify({'error': 'QR Code inválido.'}), 400
    except Exception as e: return jsonify({'error': f'Erro interno: {str(e)}'}), 500

# --- ROTAS DE INTERFACE ---

@ponto_bp.route('/scanner')
@login_required
def terminal_scanner():
    if current_user.role != 'Terminal' and current_user.role != 'Master':
        flash('Acesso restrito.')
        return redirect(url_for('main.dashboard'))
    return render_template('ponto/terminal_leitura.html')

@ponto_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    if current_user.role == 'Terminal': return redirect(url_for('ponto.terminal_scanner'))

    hoje = get_brasil_time().date()
    hoje_extenso = data_por_extenso(hoje)
    
    bloqueado = False; motivo = ""
    if current_user.escala == '5x2' and hoje.weekday() >= 5: bloqueado = True; motivo = "Não é possível realizar a marcação de ponto."
    elif current_user.escala == '12x36' and current_user.data_inicio_escala:
        if (hoje - current_user.data_inicio_escala).days % 2 != 0: bloqueado = True; motivo = "Não é possível realizar a marcação de ponto."

    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
    prox = "Entrada"
    if len(pontos) == 1: prox = "Ida Almoço"
    elif len(pontos) == 2: prox = "Volta Almoço"
    elif len(pontos) == 3: prox = "Saída"
    elif len(pontos) >= 4: prox = "Extra"

    if request.method == 'POST':
        if bloqueado: flash('Bloqueado'); return redirect(url_for('main.dashboard'))
        db.session.add(PontoRegistro(user_id=current_user.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=prox, latitude=request.form.get('latitude'), longitude=request.form.get('longitude')))
        db.session.commit(); calcular_dia(current_user.id, hoje)
        return redirect(url_for('main.dashboard'))
    
    # CORREÇÃO: Passando 'hoje' explicitamente para o template
    return render_template('ponto/registro.html', proxima_acao=prox, hoje_extenso=hoje_extenso, pontos=pontos, bloqueado=bloqueado, motivo=motivo, hoje=hoje)

@ponto_bp.route('/espelho')
@login_required
def espelho_ponto():
    target_user_id = request.args.get('user_id', type=int) or current_user.id
    if target_user_id != current_user.id and current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    user = User.query.get_or_404(target_user_id)
    mes_ref = request.args.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    try: ano, mes = map(int, mes_ref.split('-'))
    except: hoje = get_brasil_time(); ano, mes = hoje.year, hoje.month; mes_ref = hoje.strftime('%Y-%m')
    
    resumos = PontoResumo.query.filter(PontoResumo.user_id == target_user_id, func.extract('year', PontoResumo.data_referencia) == ano, func.extract('month', PontoResumo.data_referencia) == mes).order_by(PontoResumo.data_referencia).all()
    detalhes = {}
    for r in resumos:
        batidas = PontoRegistro.query.filter_by(user_id=target_user_id, data_registro=r.data_referencia).order_by(PontoRegistro.hora_registro).all()
        detalhes[r.id] = [b.hora_registro.strftime('%H:%M') for b in batidas]
    dias_semana = {0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex', 5: 'Sáb', 6: 'Dom'}
    return render_template('ponto/ponto_espelho.html', resumos=resumos, user=user, detalhes=detalhes, format_hm=format_minutes_to_hm, mes_ref=mes_ref, dias_semana=dias_semana)

@ponto_bp.route('/solicitar-ajuste', methods=['GET', 'POST'])
@login_required
def solicitar_ajuste():
    pontos_dia = []; data_selecionada = None
    meus_ajustes = PontoAjuste.query.filter_by(user_id=current_user.id).order_by(PontoAjuste.created_at.desc()).limit(20).all()
    if request.method == 'POST':
        if request.form.get('acao') == 'buscar':
            try: data_selecionada = datetime.strptime(request.form.get('data_busca'), '%Y-%m-%d').date(); pontos_dia = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=data_selecionada).order_by(PontoRegistro.hora_registro).all()
            except: flash('Data inválida')
        elif request.form.get('acao') == 'enviar':
            try:
                dt_obj = datetime.strptime(request.form.get('data_ref'), '%Y-%m-%d').date()
                p_id = int(request.form.get('ponto_id')) if request.form.get('ponto_id') else None
                solic = PontoAjuste(user_id=current_user.id, data_referencia=dt_obj, ponto_original_id=p_id, novo_horario=request.form.get('novo_horario'), tipo_batida=request.form.get('tipo_batida'), tipo_solicitacao=request.form.get('tipo_solicitacao'), justificativa=request.form.get('justificativa'))
                db.session.add(solic); db.session.commit(); flash('Enviado!')
                return redirect(url_for('ponto.solicitar_ajuste'))
            except: pass
    dados_extras = {}
    for p in meus_ajustes:
        if p.ponto_original_id:
            original = PontoRegistro.query.get(p.ponto_original_id)
            if original: dados_extras[p.id] = original.hora_registro.strftime('%H:%M')
    return render_template('ponto/solicitar_ajuste.html', pontos=pontos_dia, data_sel=data_selecionada, meus_ajustes=meus_ajustes, extras=dados_extras)
"""

# --- 2. TEMPLATES/BASE.HTML (Lógica de Menu Terminal) ---
FILE_BASE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shahin Gestão</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/toastify-js/src/toastify.min.css">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <style>body { font-family: 'Inter', sans-serif; } .sidebar { transition: transform 0.3s ease-in-out; }</style>
    <script>
        function toggleSidebar() {
            const sb = document.getElementById('sidebar');
            const ov = document.getElementById('overlay');
            if (sb.classList.contains('-translate-x-full')) { sb.classList.remove('-translate-x-full'); ov.classList.remove('hidden'); }
            else { sb.classList.add('-translate-x-full'); ov.classList.add('hidden'); }
        }
    </script>
</head>
<body class="bg-slate-50 text-slate-800">
    {% if current_user.is_authenticated and not current_user.is_first_access %}
    <div class="md:hidden bg-white border-b border-slate-200 p-4 flex justify-between items-center sticky top-0 z-40">
        <button onclick="toggleSidebar()" class="text-slate-600 focus:outline-none"><i class="fas fa-bars text-xl"></i></button>
        <span class="font-bold text-lg text-slate-800">Shahin</span>
        <div class="w-8"></div>
    </div>
    <div id="overlay" onclick="toggleSidebar()" class="fixed inset-0 bg-black bg-opacity-50 z-40 hidden md:hidden"></div>
    {% endif %}
    <div class="{% if current_user.is_authenticated and not current_user.is_first_access %}flex h-screen overflow-hidden{% endif %}">
        {% if current_user.is_authenticated and not current_user.is_first_access %}
        <aside id="sidebar" class="sidebar fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-slate-300 transform -translate-x-full md:translate-x-0 md:static md:flex-shrink-0 flex flex-col shadow-2xl h-full">
            <div class="h-16 flex items-center px-6 bg-slate-950 border-b border-slate-800">
                <div class="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-lg mr-3">S</div>
                <span class="font-bold text-xl text-white tracking-tight">Shahin</span>
            </div>
            <div class="p-6 border-b border-slate-800">
                <div class="text-xs font-bold text-slate-500 uppercase mb-1">Olá,</div>
                <div class="text-sm font-bold text-white truncate">{{ current_user.real_name }}</div>
            </div>
            <nav class="flex-1 overflow-y-auto py-4">
                <ul class="space-y-1">
                    
                    {% if current_user.role == 'Terminal' %}
                        <!-- MENU EXCLUSIVO TERMINAL -->
                         <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Terminal Fixo</li>
                         <li><a href="/ponto/scanner" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-qrcode w-6 text-center mr-2 text-blue-500"></i><span class="font-medium">Abrir Leitor</span></a></li>
                         <li><a href="/logout" class="flex items-center px-6 py-3 hover:bg-red-900/20 hover:text-red-400 transition group mt-8"><i class="fas fa-sign-out-alt w-6 text-center mr-2 text-slate-500 group-hover:text-red-400"></i><span class="font-medium">Sair</span></a></li>
                    
                    {% else %}
                        <!-- MENU PADRAO (MASTER E COLABORADOR) -->
                        <li><a href="/" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-home w-6 text-center mr-2 text-slate-500 group-hover:text-blue-500"></i><span class="font-medium">Início</span></a></li>
                        
                        <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Ponto Eletrônico</li>
                        <li><a href="/ponto/registrar" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-fingerprint w-6 text-center mr-2 text-slate-500 group-hover:text-purple-500"></i><span class="font-medium">Registrar Ponto</span></a></li>
                        <li><a href="/ponto/espelho" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-calendar-alt w-6 text-center mr-2 text-slate-500"></i><span class="font-medium">Espelho de Ponto</span></a></li>
                        <li><a href="/holerites/meus-documentos" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-folder w-6 text-center mr-2 text-slate-500 group-hover:text-yellow-400"></i><span class="font-medium">Meus Holerites</span></a></li>
                        <li><a href="/ponto/solicitar-ajuste" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-edit w-6 text-center mr-2 text-slate-500"></i><span class="font-medium">Solicitar Ajuste</span></a></li>
                        
                        {% if current_user.role == 'Master' %}
                        <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Administração</li>
                        <li><a href="/holerites/admin/importar" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-file-upload w-6 text-center mr-2 text-slate-500 group-hover:text-blue-400"></i><span class="font-medium">Importar Holerites</span></a></li>
                        <li><a href="/admin/relatorio-folha" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-file-invoice-dollar w-6 text-center mr-2 text-slate-500 group-hover:text-emerald-400"></i><span class="font-medium">Relatório de Folha</span></a></li>
                        <li><a href="/controle-uniforme" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-tshirt w-6 text-center mr-2 text-slate-500 group-hover:text-yellow-500"></i><span class="font-medium">Controle de Uniforme</span></a></li>
                        <li><a href="/admin/solicitacoes" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-check-double w-6 text-center mr-2 text-slate-500 group-hover:text-emerald-500"></i><span class="font-medium">Solicitações de Ponto</span></a></li>
                        <li><a href="/admin/usuarios" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-users-cog w-6 text-center mr-2 text-blue-400"></i><span class="font-medium">Funcionários</span></a></li>
                        {% endif %}
                        
                        <li><a href="/logout" class="flex items-center px-6 py-3 hover:bg-red-900/20 hover:text-red-400 transition group mt-8"><i class="fas fa-sign-out-alt w-6 text-center mr-2 text-slate-500 group-hover:text-red-400"></i><span class="font-medium">Sair</span></a></li>
                    {% endif %}
                </ul>
            </nav>
        </aside>
        {% endif %}
        
        <div class="flex-1 h-full overflow-y-auto bg-slate-50 relative w-full">
            <div class="max-w-5xl mx-auto p-4 md:p-8 pb-20">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="hidden" id="flask-msg-{{ loop.index }}" data-cat="{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                {% block content %}{% endblock %}
            </div>
            {% if current_user.is_authenticated and not current_user.is_first_access %}
            <footer class="py-6 text-center text-xs text-slate-400">&copy; 2026 Vortice Company</footer>
            {% endif %}
        </div>
    </div>
    
    <script type="text/javascript" src="https://cdn.jsdelivr.net/npm/toastify-js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Processa mensagens flash escondidas
            document.querySelectorAll('[id^="flask-msg-"]').forEach(el => {
                const msg = el.innerText;
                const cat = el.getAttribute('data-cat');
                Toastify({
                    text: msg,
                    duration: 4000,
                    close: true,
                    gravity: "top", 
                    position: "right", 
                    style: {
                        background: cat === 'error' ? "linear-gradient(to right, #ef4444, #b91c1c)" : "linear-gradient(to right, #059669, #047857)",
                        borderRadius: "8px",
                        boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
                        fontSize: "14px"
                    },
                }).showToast();
            });
        });
    </script>
</body>
</html>
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
        print("\n>>> SUCESSO V68! ERROS DE MENU E PONTO CORRIGIDOS <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V68: {PROJECT_NAME} ---")
    write_file("app/routes/ponto.py", FILE_BP_PONTO)
    write_file("app/templates/base.html", FILE_BASE)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



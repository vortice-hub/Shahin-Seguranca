import os
import shutil
import subprocess
from datetime import datetime

# ================= CONFIGURAÇÕES =================
PROJECT_DIR = os.getcwd()
BACKUP_ROOT = os.path.join(PROJECT_DIR, "backups_auto")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
CURRENT_BACKUP_DIR = os.path.join(BACKUP_ROOT, f"bkp_fix_ux_{TIMESTAMP}")

# Caminhos corrigidos baseados na estrutura de Blueprints
FILES_TO_MODIFY = [
    "app/templates/base.html",           # Template Global
    "app/main/routes.py",                # Rota do Blueprint Main
    "app/main/templates/main/dashboard.html" # Caminho correto do Template Local
]

def log(msg):
    print(f"\033[96m[FIX-SCRIPT]\033[0m {msg}")

def ensure_dir_exists(file_path):
    """Cria o diretório pai se não existir para evitar FileNotFoundError"""
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)
        log(f"Diretório criado: {directory}")

def create_backup():
    log("Criando backup de segurança...")
    if not os.path.exists(CURRENT_BACKUP_DIR):
        os.makedirs(CURRENT_BACKUP_DIR)
    
    for file_path in FILES_TO_MODIFY:
        full_path = os.path.join(PROJECT_DIR, file_path)
        if os.path.exists(full_path):
            dest_path = os.path.join(CURRENT_BACKUP_DIR, file_path)
            ensure_dir_exists(dest_path)
            shutil.copy2(full_path, dest_path)
        else:
            log(f"Arquivo não encontrado para backup (será criado): {file_path}")

def apply_fixes():
    log("Aplicando correções de UX no caminho correto...")

    # ---------------------------------------------------------
    # 1. BASE.HTML (Toastify e UI)
    # ---------------------------------------------------------
    content_base = """<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shahin Gestão</title>
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- FontAwesome -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <!-- Toastify CSS -->
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/toastify-js/src/toastify.min.css">
    
    <style>
        body { font-family: 'Inter', sans-serif; } 
        .sidebar { transition: transform 0.3s ease-in-out; } 
        .animate-fade-in { animation: fadeIn 0.5s ease-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    </style>
    
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
                    <li><a href="/" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-home w-6 text-center mr-2 text-slate-500 group-hover:text-blue-500"></i><span class="font-medium">Início</span></a></li>
                    
                    <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Funcionário</li>
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
                </ul>
            </nav>
        </aside>
        {% endif %}
        
        <div class="flex-1 h-full overflow-y-auto bg-slate-50 relative w-full">
            <div class="max-w-5xl mx-auto p-4 md:p-8 pb-20">
                {% block content %}{% endblock %}
            </div>
            {% if current_user.is_authenticated and not current_user.is_first_access %}
            <footer class="py-6 text-center text-xs text-slate-400">&copy; 2026 Vortice Company</footer>
            {% endif %}
        </div>
    </div>

    <!-- Toastify JS -->
    <script type="text/javascript" src="https://cdn.jsdelivr.net/npm/toastify-js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        Toastify({
                            text: "{{ message }}",
                            duration: 4000,
                            close: true,
                            gravity: "top", 
                            position: "right", 
                            stopOnFocus: true, 
                            style: {
                                background: "{% if category == 'error' %}linear-gradient(to right, #ef4444, #b91c1c){% else %}linear-gradient(to right, #059669, #047857){% endif %}",
                                borderRadius: "8px",
                                boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
                                fontWeight: "bold",
                                fontSize: "14px"
                            },
                        }).showToast();
                    {% endfor %}
                {% endif %}
            {% endwith %}
        });
    </script>
</body>
</html>
"""
    fpath_base = os.path.join(PROJECT_DIR, "app/templates/base.html")
    ensure_dir_exists(fpath_base)
    with open(fpath_base, "w", encoding="utf-8") as f:
        f.write(content_base)

    # ---------------------------------------------------------
    # 2. MAIN ROUTES (Lógica de Gráficos)
    # ---------------------------------------------------------
    content_routes = """from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import PontoRegistro, ItemEstoque, PontoResumo
from app.utils import get_brasil_time
from sqlalchemy import func, extract

main_bp = Blueprint('main', __name__, template_folder='templates')

@main_bp.route('/')
@login_required
def dashboard():
    hoje = get_brasil_time()
    hoje_date = hoje.date()
    
    # Lógica Padrão
    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje_date).count()
    status = "Não Iniciado"
    if pontos == 1: status = "Trabalhando"
    elif pontos == 2: status = "Almoço"
    elif pontos == 3: status = "Trabalhando (Tarde)"
    elif pontos >= 4: status = "Dia Finalizado"

    # Lógica Master (Gráficos)
    dados_graficos = None
    
    if current_user.role == 'Master':
        estoque_critico = ItemEstoque.query.filter(
            ItemEstoque.quantidade <= ItemEstoque.estoque_minimo
        ).order_by(ItemEstoque.quantidade).limit(5).all()
        
        resumos_mes = db_resumos_mes(hoje.year, hoje.month)
        
        dados_graficos = {
            'estoque_labels': [i.nome for i in estoque_critico],
            'estoque_data': [i.quantidade for i in estoque_critico],
            'ponto_status': resumos_mes
        }

    return render_template('main/dashboard.html', status_ponto=status, dados_graficos=dados_graficos)

def db_resumos_mes(ano, mes):
    stats = PontoResumo.query.with_entities(
        PontoResumo.status_dia, func.count(PontoResumo.id)
    ).filter(
        extract('year', PontoResumo.data_referencia) == ano,
        extract('month', PontoResumo.data_referencia) == mes
    ).group_by(PontoResumo.status_dia).all()
    
    resultado = {'OK': 0, 'Falta': 0, 'Incompleto': 0, 'Hora Extra': 0, 'Débito': 0}
    for s, qtd in stats:
        if s in resultado:
            resultado[s] = qtd
        else:
            resultado['Incompleto'] += qtd
            
    return resultado
"""
    fpath_routes = os.path.join(PROJECT_DIR, "app/main/routes.py")
    ensure_dir_exists(fpath_routes)
    with open(fpath_routes, "w", encoding="utf-8") as f:
        f.write(content_routes)

    # ---------------------------------------------------------
    # 3. DASHBOARD.HTML (Chart.js no Caminho Correto)
    # ---------------------------------------------------------
    content_dashboard = """{% extends 'base.html' %}
{% block content %}

<!-- Widget de Ponto -->
<div class="bg-gradient-to-r from-blue-900 to-slate-900 rounded-2xl p-6 text-white shadow-xl mb-8 flex justify-between items-center relative overflow-hidden transition transform hover:scale-[1.01]">
    <div class="absolute top-0 right-0 -mr-4 -mt-4 w-24 h-24 bg-white opacity-10 rounded-full blur-xl"></div>
    <div>
        <p class="text-xs font-bold text-blue-300 uppercase tracking-widest mb-1">Status Hoje</p>
        <h2 class="text-2xl font-bold mb-1">{{ status_ponto }}</h2>
        <p class="text-xs opacity-70">{{ current_user.real_name }}</p>
    </div>
    <a href="/ponto/registrar" class="bg-white text-blue-900 hover:bg-blue-50 font-bold py-3 px-6 rounded-full shadow-lg transition transform hover:scale-105 flex items-center gap-2 z-10">
        <i class="fas fa-fingerprint"></i> <span>REGISTRAR</span>
    </a>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
    <div class="bg-white p-6 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition">
        <h3 class="font-bold text-slate-700 mb-2"><i class="fas fa-bolt text-yellow-500 mr-2"></i>Acesso Rápido</h3>
        <div class="flex flex-col gap-2 mt-4">
             <a href="/ponto/espelho" class="text-sm text-slate-600 hover:text-blue-600 flex items-center gap-2"><i class="fas fa-calendar-alt w-5"></i> Ver meu Espelho</a>
             <a href="/holerites/meus-documentos" class="text-sm text-slate-600 hover:text-blue-600 flex items-center gap-2"><i class="fas fa-file-invoice w-5"></i> Meus Holerites</a>
             <a href="/ponto/solicitar-ajuste" class="text-sm text-slate-600 hover:text-blue-600 flex items-center gap-2"><i class="fas fa-exclamation-circle w-5"></i> Ajustar Ponto</a>
        </div>
    </div>
    
    {% if current_user.role != 'Master' %}
    <div class="bg-blue-50 p-6 rounded-xl border border-blue-100 shadow-sm flex items-center justify-center text-center">
        <div>
            <div class="text-blue-200 text-4xl mb-2"><i class="fas fa-quote-left"></i></div>
            <p class="text-blue-800 font-medium italic text-sm">"O sucesso é a soma de pequenos esforços repetidos dia após dia."</p>
        </div>
    </div>
    {% endif %}

    {% if current_user.role == 'Master' %}
    <div class="bg-white p-6 rounded-xl border border-slate-200 shadow-sm border-l-4 border-l-purple-500 hover:shadow-md transition">
        <h3 class="font-bold text-slate-700 mb-2"><i class="fas fa-crown text-purple-500 mr-2"></i>Área Master</h3>
        <div class="grid grid-cols-2 gap-2 mt-4">
            <a href="/admin/usuarios" class="bg-slate-50 hover:bg-slate-100 p-2 rounded text-center text-xs font-bold text-slate-600 border border-slate-200">Funcionários</a>
            <a href="/admin/solicitacoes" class="bg-slate-50 hover:bg-slate-100 p-2 rounded text-center text-xs font-bold text-slate-600 border border-slate-200">Solicitações</a>
        </div>
    </div>
    {% endif %}
</div>

<!-- GRÁFICOS MASTER -->
{% if current_user.role == 'Master' and dados_graficos %}
<h3 class="text-lg font-bold text-slate-800 mb-4 px-2">Visão Geral</h3>
<div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
    <!-- Gráfico 1 -->
    <div class="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <h4 class="text-xs font-bold text-red-500 uppercase mb-4">Estoque Crítico</h4>
        {% if dados_graficos.estoque_labels %}
            <canvas id="chartEstoque"></canvas>
        {% else %}
            <div class="h-40 flex items-center justify-center text-slate-400 text-sm">Estoque saudável.</div>
        {% endif %}
    </div>

    <!-- Gráfico 2 -->
    <div class="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <h4 class="text-xs font-bold text-blue-500 uppercase mb-4">Pontualidade (Mês)</h4>
        <div class="h-48">
            <canvas id="chartPonto"></canvas>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
    {% if dados_graficos.estoque_labels %}
    const ctxEstoque = document.getElementById('chartEstoque');
    new Chart(ctxEstoque, {
        type: 'bar',
        data: {
            labels: {{ dados_graficos.estoque_labels | tojson }},
            datasets: [{
                label: 'Qtd Atual',
                data: {{ dados_graficos.estoque_data | tojson }},
                backgroundColor: '#ef4444',
                borderRadius: 4
            }]
        },
        options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
    });
    {% endif %}

    const ctxPonto = document.getElementById('chartPonto');
    const dadosPonto = {{ dados_graficos.ponto_status | tojson }};
    new Chart(ctxPonto, {
        type: 'doughnut',
        data: {
            labels: ['OK', 'Falta', 'Hora Extra', 'Débito'],
            datasets: [{
                data: [dadosPonto['OK'], dadosPonto['Falta'], dadosPonto['Hora Extra'], dadosPonto['Débito']],
                backgroundColor: ['#10b981', '#ef4444', '#3b82f6', '#f59e0b'],
                borderWidth: 0
            }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { boxWidth: 10 } } } }
    });
</script>
{% endif %}

{% endblock %}
"""
    # FIX: Caminho correto app/main/templates/main/dashboard.html
    fpath_dashboard = os.path.join(PROJECT_DIR, "app/main/templates/main/dashboard.html")
    ensure_dir_exists(fpath_dashboard)
    with open(fpath_dashboard, "w", encoding="utf-8") as f:
        f.write(content_dashboard)

    log("Arquivos criados/atualizados com sucesso.")

def git_operations():
    log("Enviando alterações para o Git...")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "UX Upgrade: Fix path for dashboard and add charts"], check=True)
        subprocess.run(["git", "push"], check=True)
        log("Código enviado.")
    except subprocess.CalledProcessError as e:
        log(f"\033[91mErro no Git: {e}\033[0m")

def self_destruct():
    log("Auto-destruindo script...")
    try:
        os.remove(__file__)
        log("Limpo.")
    except:
        pass

if __name__ == "__main__":
    create_backup()
    apply_fixes()
    git_operations()
    self_destruct()



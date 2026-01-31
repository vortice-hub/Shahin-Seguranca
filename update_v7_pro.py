import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Thay RH"
COMMIT_MSG = "V7: Visual Pro, Timezone BR, Qtd Saida e Ajuste Tamanhos"
# URL do banco (Hardcoded para seguranca contra falha de env)
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""

FILE_REQ = """flask
flask-sqlalchemy
psycopg2-binary
gunicorn
"""

FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Lógica Atualizada) ---
FILE_APP = f"""
import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta # Importando timedelta para o fuso
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'chave_v7_pro_secret'

# --- BANCO DE DADOS ---
db_url = "{DB_URL_FIXA}"
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app, engine_options={{
    "pool_pre_ping": True,
    "pool_size": 10,
    "pool_recycle": 300,
}})

# --- UTILITÁRIOS ---
def get_brasil_time():
    # Retorna hora UTC - 3 horas
    return datetime.utcnow() - timedelta(hours=3)

# --- MODELOS ---
class ItemEstoque(db.Model):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), default='Uniforme') # Default fixo
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20)) 
    quantidade = db.Column(db.Integer, default=0)
    data_atualizacao = db.Column(db.DateTime, default=get_brasil_time)

class HistoricoEntrada(db.Model):
    __tablename__ = 'historico_entrada'
    id = db.Column(db.Integer, primary_key=True)
    item_nome = db.Column(db.String(150))
    quantidade = db.Column(db.Integer)
    data_hora = db.Column(db.DateTime, default=get_brasil_time)

class HistoricoSaida(db.Model):
    __tablename__ = 'historico_saida'
    id = db.Column(db.Integer, primary_key=True)
    coordenador = db.Column(db.String(100))
    colaborador = db.Column(db.String(100))
    item_nome = db.Column(db.String(100))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20))
    quantidade = db.Column(db.Integer)
    data_entrega = db.Column(db.DateTime, default=get_brasil_time)

# --- BOOT ---
try:
    with app.app_context():
        db.create_all()
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS genero VARCHAR(20)"))
                conn.commit()
        except: pass
except Exception: pass

# --- ROTAS ---
@app.route('/')
def dashboard():
    try:
        itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
        # Calculo de totais para os Cards do Dashboard
        total_pecas = sum(i.quantidade for i in itens)
        total_itens = len(itens)
        return render_template('dashboard.html', itens=itens, total_pecas=total_pecas, total_itens=total_itens)
    except Exception as e:
        return f"Erro DB: {{e}}", 500

@app.route('/entrada', methods=['GET', 'POST'])
def entrada():
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            # Categoria removida do form, fixamos no codigo
            categoria = "Uniforme"
            tamanho = request.form.get('tamanho')
            genero = request.form.get('genero')
            quantidade = int(request.form.get('quantidade') or 1)
            
            item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
            if item:
                item.quantidade += quantidade
                item.data_atualizacao = get_brasil_time()
                flash(f'Estoque atualizado: {{nome}}')
            else:
                novo = ItemEstoque(nome=nome, categoria=categoria, tamanho=tamanho, genero=genero, quantidade=quantidade)
                novo.data_atualizacao = get_brasil_time()
                db.session.add(novo)
                flash(f'Novo item: {{nome}}')
            
            log = HistoricoEntrada(item_nome=f"{{nome}} ({{genero}}-{{tamanho}})", quantidade=quantidade)
            log.data_hora = get_brasil_time()
            db.session.add(log)
            
            db.session.commit()
            return redirect(url_for('entrada'))
        except Exception as e:
            db.session.rollback()
            return f"Erro: {{e}}", 500
    return render_template('entrada.html')

@app.route('/saida', methods=['GET', 'POST'])
def saida():
    try:
        if request.method == 'POST':
            item_id = request.form.get('item_id')
            qtd_saida = int(request.form.get('quantidade') or 1) # Nova logica de quantidade
            data_input = request.form.get('data')
            
            item = ItemEstoque.query.get(item_id)
            
            if not item:
                flash("Erro: Item não encontrado.")
                return redirect(url_for('saida'))

            # Validação de Estoque
            if item.quantidade >= qtd_saida:
                item.quantidade -= qtd_saida
                item.data_atualizacao = get_brasil_time()
                
                try:
                    dt = datetime.strptime(data_input, '%Y-%m-%d')
                except:
                    dt = get_brasil_time()
                
                log = HistoricoSaida(
                    coordenador=request.form.get('coordenador'),
                    colaborador=request.form.get('colaborador'),
                    item_nome=item.nome,
                    tamanho=item.tamanho,
                    genero=item.genero,
                    quantidade=qtd_saida, # Registra a qtd exata que saiu
                    data_entrega=dt
                )
                db.session.add(log)
                db.session.commit()
                flash(f'Saída de {{qtd_saida}} unidade(s) registrada!')
                return redirect(url_for('dashboard'))
            else:
                flash(f'Erro: Estoque insuficiente. Disponível: {{item.quantidade}}')
                return redirect(url_for('saida'))
        
        itens = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).order_by(ItemEstoque.nome).all()
        return render_template('saida.html', itens=itens)
    except Exception as e:
        return f"Erro: {{e}}", 500

@app.route('/historico/entrada')
def view_historico_entrada():
    logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all()
    return render_template('historico_entrada.html', logs=logs)

@app.route('/historico/saida')
def view_historico_saida():
    logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all()
    return render_template('historico_saida.html', logs=logs)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
"""

# --- TEMPLATES PROFISSIONAIS ---

FILE_BASE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Thay RH | Enterprise</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
    </style>
</head>
<body class="bg-slate-50 text-slate-800">
    <!-- Navbar Pro -->
    <nav class="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div class="max-w-4xl mx-auto px-4">
            <div class="flex justify-between items-center h-16">
                <a href="/" class="flex items-center gap-2 text-slate-800 hover:text-blue-600 transition">
                    <div class="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-lg">T</div>
                    <span class="font-bold text-xl tracking-tight">Thay RH</span>
                </a>
                <div class="flex items-center gap-4">
                    <a href="/" class="text-sm font-medium text-slate-500 hover:text-blue-600">Dashboard</a>
                    <div class="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500">
                        <i class="fas fa-user text-xs"></i>
                    </div>
                </div>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <main class="max-w-4xl mx-auto p-4 md:p-6 pb-20">
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="mb-4 p-4 rounded-lg bg-blue-50 border border-blue-100 text-blue-700 text-sm font-medium shadow-sm flex items-center gap-2 animate-fade-in">
                        <i class="fas fa-check-circle"></i> {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>
    
    <!-- Footer Mobile Style -->
    <footer class="mt-8 text-center text-xs text-slate-400 pb-8">
        &copy; 2026 Thay RH System. Versão 7.0 Pro
    </footer>
</body>
</html>
"""

FILE_DASHBOARD = """
{% extends 'base.html' %}
{% block content %}
<!-- KPI Cards -->
<div class="grid grid-cols-2 gap-4 mb-8">
    <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Total Peças</div>
        <div class="text-3xl font-bold text-slate-800">{{ total_pecas }}</div>
    </div>
    <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Tipos de Item</div>
        <div class="text-3xl font-bold text-slate-800">{{ total_itens }}</div>
    </div>
</div>

<!-- Action Buttons -->
<div class="grid grid-cols-2 gap-4 mb-8">
    <a href="/entrada" class="group relative bg-white border border-slate-200 hover:border-emerald-500 p-6 rounded-xl shadow-sm hover:shadow-md transition-all duration-300 flex flex-col items-center justify-center">
        <div class="w-12 h-12 bg-emerald-50 rounded-full flex items-center justify-center text-emerald-600 mb-3 group-hover:scale-110 transition">
            <i class="fas fa-arrow-down"></i>
        </div>
        <span class="font-bold text-slate-700 group-hover:text-emerald-700">Entrada</span>
    </a>
    <a href="/saida" class="group relative bg-white border border-slate-200 hover:border-blue-500 p-6 rounded-xl shadow-sm hover:shadow-md transition-all duration-300 flex flex-col items-center justify-center">
        <div class="w-12 h-12 bg-blue-50 rounded-full flex items-center justify-center text-blue-600 mb-3 group-hover:scale-110 transition">
            <i class="fas fa-arrow-up"></i>
        </div>
        <span class="font-bold text-slate-700 group-hover:text-blue-700">Saída</span>
    </a>
</div>

<!-- Inventory List -->
<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <div class="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
        <h2 class="font-semibold text-slate-800">Inventário</h2>
        <span class="text-xs font-medium bg-slate-200 text-slate-600 px-2 py-1 rounded-md">Live</span>
    </div>
    
    <div class="divide-y divide-slate-100">
        {% for item in itens %}
        <div class="px-6 py-4 flex items-center justify-between hover:bg-slate-50 transition">
            <div class="flex items-center gap-4">
                <div class="w-10 h-10 rounded-full flex items-center justify-center text-slate-500 bg-slate-100 font-bold text-xs border border-slate-200">
                    {{ item.tamanho }}
                </div>
                <div>
                    <div class="font-semibold text-slate-800 text-sm">{{ item.nome }}</div>
                    <div class="text-xs text-slate-500 flex items-center gap-1">
                        {% if item.genero == 'Masculino' %}
                            <i class="fas fa-mars text-blue-400"></i>
                        {% elif item.genero == 'Feminino' %}
                            <i class="fas fa-venus text-rose-400"></i>
                        {% else %}
                            <i class="fas fa-genderless text-slate-400"></i>
                        {% endif %}
                        {{ item.genero }}
                    </div>
                </div>
            </div>
            
            <div class="text-right">
                <div class="text-lg font-bold {% if item.quantidade < 5 %}text-red-500{% else %}text-emerald-600{% endif %}">
                    {{ item.quantidade }}
                </div>
                <div class="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Estoque</div>
            </div>
        </div>
        {% else %}
        <div class="p-12 text-center">
            <div class="text-slate-300 text-4xl mb-3"><i class="fas fa-box-open"></i></div>
            <p class="text-slate-500">Nenhum item registrado.</p>
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
"""

FILE_ENTRADA = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center justify-between mb-6">
    <h2 class="text-lg font-bold text-slate-800">Nova Entrada</h2>
    <a href="/historico/entrada" class="text-xs font-medium text-blue-600 hover:underline">Ver Histórico</a>
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <form action="/entrada" method="POST" class="p-6 space-y-5">
        
        <!-- Input Group -->
        <div>
            <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Item</label>
            <input type="text" name="nome" list="sugestoes" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-slate-800 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition" placeholder="Ex: Camisa Polo" required>
            <datalist id="sugestoes">
                <option value="Camisa Polo">
                <option value="Calça Brim">
                <option value="Bota de Segurança">
                <option value="Jaleco">
            </datalist>
        </div>

        <div class="grid grid-cols-2 gap-4">
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Tamanho</label>
                <select name="tamanho" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500" required>
                    <option value="P">P</option>
                    <option value="M">M</option>
                    <option value="G">G</option>
                    <option value="GG">GG</option>
                    <option value="XG">XG</option>
                </select>
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Gênero</label>
                <select name="genero" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500" required>
                    <option value="Masculino">Masculino</option>
                    <option value="Feminino">Feminino</option>
                    <option value="Unissex">Unissex</option>
                </select>
            </div>
        </div>

        <div>
            <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Quantidade</label>
            <div class="relative">
                <input type="number" name="quantidade" min="1" value="1" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-emerald-600 font-bold text-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:bg-white transition" required>
                <div class="absolute right-4 top-4 text-xs text-slate-400 font-bold">UN</div>
            </div>
        </div>

        <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-4 rounded-lg shadow-md hover:shadow-lg transition-all transform active:scale-[0.98]">
            ADICIONAR AO ESTOQUE
        </button>
    </form>
</div>
{% endblock %}
"""

FILE_SAIDA = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center justify-between mb-6">
    <h2 class="text-lg font-bold text-slate-800">Registrar Saída</h2>
    <a href="/historico/saida" class="text-xs font-medium text-blue-600 hover:underline">Ver Histórico</a>
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <form action="/saida" method="POST" class="p-6 space-y-5">
        
        <div>
            <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Selecionar Item</label>
            <div class="relative">
                <select name="item_id" class="w-full appearance-none bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-slate-800 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition" required>
                    <option value="" disabled selected>Escolha o uniforme...</option>
                    {% for item in itens %}
                    <option value="{{ item.id }}">{{ item.nome }} - {{ item.tamanho }} ({{ item.genero }}) | Saldo: {{ item.quantidade }}</option>
                    {% endfor %}
                </select>
                <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-slate-500">
                    <i class="fas fa-chevron-down text-xs"></i>
                </div>
            </div>
        </div>

        <!-- Nova Funcionalidade: Quantidade de Saida -->
        <div>
            <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Quantidade a Retirar</label>
            <input type="number" name="quantidade" min="1" value="1" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-blue-600 font-bold text-lg focus:outline-none focus:ring-2 focus:ring-blue-500" required>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Coordenador</label>
                <input type="text" name="coordenador" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Quem autorizou" required>
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Colaborador</label>
                <input type="text" name="colaborador" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Quem recebeu" required>
            </div>
        </div>

        <div>
            <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Data da Entrega</label>
            <input type="date" name="data" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500" required>
        </div>

        <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-lg shadow-md hover:shadow-lg transition-all transform active:scale-[0.98]">
            CONFIRMAR ENTREGA
        </button>
    </form>
</div>
{% endblock %}
"""

FILE_HIST_ENTRADA = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6">
    <a href="/entrada" class="text-xs font-bold text-slate-400 hover:text-slate-600 mb-2 inline-block"><i class="fas fa-arrow-left mr-1"></i> VOLTAR</a>
    <h2 class="text-lg font-bold text-slate-800">Log de Entradas</h2>
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <table class="w-full text-left text-sm text-slate-600">
        <thead class="bg-slate-50 text-xs uppercase text-slate-400 font-bold">
            <tr>
                <th class="px-6 py-3">Data</th>
                <th class="px-6 py-3">Item</th>
                <th class="px-6 py-3 text-right">Qtd</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
            {% for log in logs %}
            <tr class="hover:bg-slate-50 transition">
                <td class="px-6 py-4 whitespace-nowrap text-xs font-medium">{{ log.data_hora.strftime('%d/%m %H:%M') }}</td>
                <td class="px-6 py-4 font-medium text-slate-800">{{ log.item_nome }}</td>
                <td class="px-6 py-4 text-right font-bold text-emerald-600">+{{ log.quantidade }}</td>
            </tr>
            {% else %}
            <tr><td colspan="3" class="px-6 py-8 text-center text-slate-400">Sem registros.</td></tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""

FILE_HIST_SAIDA = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6">
    <a href="/saida" class="text-xs font-bold text-slate-400 hover:text-slate-600 mb-2 inline-block"><i class="fas fa-arrow-left mr-1"></i> VOLTAR</a>
    <h2 class="text-lg font-bold text-slate-800">Log de Entregas</h2>
</div>

<div class="space-y-3">
    {% for log in logs %}
    <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition">
        <div class="flex justify-between items-start mb-2">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wide">
                {{ log.data_entrega.strftime('%d/%m/%Y') }}
            </div>
            <div class="bg-blue-50 text-blue-700 text-xs px-2 py-1 rounded font-bold">
                -{{ log.quantidade }} UN
            </div>
        </div>
        
        <div class="flex items-center gap-3 mb-3">
             <div class="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 font-bold text-xs">
                 {{ log.colaborador[:1] }}
             </div>
             <div>
                 <div class="font-bold text-slate-800">{{ log.colaborador }}</div>
                 <div class="text-xs text-slate-500">Autorizado por: {{ log.coordenador }}</div>
             </div>
        </div>
        
        <div class="pt-3 border-t border-slate-100 text-sm text-slate-700 flex items-center gap-2">
            <i class="fas fa-tshirt text-slate-400"></i>
            {{ log.item_nome }} <span class="text-slate-400">|</span> {{ log.tamanho }} <span class="text-slate-400">|</span> {{ log.genero }}
        </div>
    </div>
    {% else %}
    <div class="text-center py-10 text-slate-400">Nenhuma entrega registrada.</div>
    {% endfor %}
</div>
{% endblock %}
"""

# --- FUNÇÕES ---

def create_backup():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join("backup", timestamp)
    
    files = ["app.py", "requirements.txt", "Procfile", "runtime.txt"]
    for root, dirs, f_names in os.walk("templates"):
        for f in f_names:
            files.append(os.path.join(root, f))
            
    for f in files:
        if os.path.exists(f):
            dest = os.path.join(backup_dir, f)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(f, dest)

def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())
    print(f"Atualizado: {path}")

def git_update():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO! Visual Pro + Fuso Horário Enviados. <<<")
    except Exception as e:
        print(f"Git Error: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V7: {PROJECT_NAME} PRO ---")
    create_backup()
    
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP) # App com Fuso e Lógica nova
    
    # Templates com Visual Novo (SaaS Style)
    write_file("templates/base.html", FILE_BASE)
    write_file("templates/dashboard.html", FILE_DASHBOARD)
    write_file("templates/entrada.html", FILE_ENTRADA)
    write_file("templates/saida.html", FILE_SAIDA)
    write_file("templates/historico_entrada.html", FILE_HIST_ENTRADA)
    write_file("templates/historico_saida.html", FILE_HIST_SAIDA)
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



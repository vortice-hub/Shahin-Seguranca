import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V14: Correção Layout Desktop (Sidebar Lado a Lado)"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""
FILE_REQ = """flask\nflask-sqlalchemy\npsycopg2-binary\ngunicorn\nflask-login\nwerkzeug"""
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Mantido igual V13) ---
FILE_APP = f"""
import os
import logging
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'chave_v14_layout_fix'

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

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

# --- MODELOS ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    real_name = db.Column(db.String(100))
    role = db.Column(db.String(50)) 
    is_first_access = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_brasil_time)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class ItemEstoque(db.Model):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), default='Uniforme')
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20)) 
    quantidade = db.Column(db.Integer, default=0)
    estoque_minimo = db.Column(db.Integer, default=5)
    estoque_ideal = db.Column(db.Integer, default=20)
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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- BOOT ---
try:
    with app.app_context():
        db.create_all()
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS genero VARCHAR(20)"))
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS estoque_minimo INTEGER DEFAULT 5"))
                conn.commit()
        except: pass
        
        if not User.query.filter_by(username='Thaynara').first():
            master = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
            master.set_password('1855')
            db.session.add(master)
            db.session.commit()
except Exception: pass

# --- ROTAS ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user)
            if user.is_first_access: return redirect(url_for('primeiro_acesso'))
            return redirect(url_for('dashboard'))
        flash('Credenciais inválidas.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/primeiro-acesso', methods=['GET', 'POST'])
@login_required
def primeiro_acesso():
    if not current_user.is_first_access: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        if request.form.get('nova_senha') == request.form.get('confirmacao'):
            current_user.set_password(request.form.get('nova_senha'))
            current_user.is_first_access = False
            db.session.commit()
            return redirect(url_for('dashboard'))
        flash('Senhas não conferem.')
    return render_template('primeiro_acesso.html')

@app.route('/admin/usuarios')
@login_required
def gerenciar_usuarios():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    users = User.query.all()
    return render_template('admin_usuarios.html', users=users)

@app.route('/admin/usuarios/novo', methods=['GET', 'POST'])
@login_required
def novo_usuario():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        if User.query.filter_by(username=username).first():
            flash('Erro: Usuário já existe.')
        else:
            senha_temp = secrets.token_hex(3)
            novo = User(username=username, 
                       real_name=request.form.get('real_name'), 
                       role=request.form.get('role'), 
                       is_first_access=True)
            novo.set_password(senha_temp)
            db.session.add(novo)
            db.session.commit()
            return render_template('sucesso_usuario.html', novo_user=username, senha_gerada=senha_temp)
            
    return render_template('novo_usuario.html')

@app.route('/admin/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            if user.username == 'Thaynara': flash('Não pode excluir o Master.')
            else:
                db.session.delete(user)
                db.session.commit()
                flash('Excluído.')
            return redirect(url_for('gerenciar_usuarios'))
        elif acao == 'resetar_senha':
            nova = secrets.token_hex(3)
            user.set_password(nova)
            user.is_first_access = True
            db.session.commit()
            flash(f'Senha resetada: {{nova}}')
            return redirect(url_for('editar_usuario', id=id))
        else:
            user.real_name = request.form.get('real_name')
            user.username = request.form.get('username')
            if user.username != 'Thaynara': 
                user.role = request.form.get('role') 
            db.session.commit()
            flash('Atualizado.')
            return redirect(url_for('gerenciar_usuarios'))
    return render_template('editar_usuario.html', user=user)

@app.route('/')
@login_required
def dashboard():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    try:
        itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
        return render_template('dashboard.html', itens=itens)
    except: return "Erro DB", 500

@app.route('/entrada', methods=['GET', 'POST'])
@login_required
def entrada():
    if request.method == 'POST':
        try:
            nome_select = request.form.get('nome_select')
            nome = request.form.get('nome_outros') if nome_select == 'Outros' else nome_select
            tamanho = request.form.get('tamanho')
            genero = request.form.get('genero')
            qtd = int(request.form.get('quantidade') or 1)
            
            item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
            if item:
                item.quantidade += qtd
                item.estoque_minimo = int(request.form.get('estoque_minimo') or 5)
                item.estoque_ideal = int(request.form.get('estoque_ideal') or 20)
                item.data_atualizacao = get_brasil_time()
                flash(f'Estoque atualizado: {{nome}}')
            else:
                novo = ItemEstoque(nome=nome, tamanho=tamanho, genero=genero, quantidade=qtd, 
                                 estoque_minimo=int(request.form.get('estoque_minimo') or 5),
                                 estoque_ideal=int(request.form.get('estoque_ideal') or 20))
                novo.data_atualizacao = get_brasil_time()
                db.session.add(novo)
            
            db.session.add(HistoricoEntrada(item_nome=f"{{nome}} ({{genero}}-{{tamanho}})", quantidade=qtd, data_hora=get_brasil_time()))
            db.session.commit()
            return redirect(url_for('entrada'))
        except: db.session.rollback()
    return render_template('entrada.html')

@app.route('/saida', methods=['GET', 'POST'])
@login_required
def saida():
    if request.method == 'POST':
        item = ItemEstoque.query.get(request.form.get('item_id'))
        qtd = int(request.form.get('quantidade') or 1)
        if item and item.quantidade >= qtd:
            item.quantidade -= qtd
            item.data_atualizacao = get_brasil_time()
            try: dt = datetime.strptime(request.form.get('data'), '%Y-%m-%d')
            except: dt = get_brasil_time()
            db.session.add(HistoricoSaida(
                coordenador=request.form.get('coordenador'), 
                colaborador=request.form.get('colaborador'),
                item_nome=item.nome, 
                tamanho=item.tamanho, 
                genero=item.genero, 
                quantidade=qtd, 
                data_entrega=dt
            ))
            db.session.commit()
            flash('Saída registrada.')
            return redirect(url_for('dashboard'))
        flash('Erro estoque.')
    itens = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).order_by(ItemEstoque.nome).all()
    return render_template('saida.html', itens=itens)

@app.route('/gerenciar/selecao', methods=['GET', 'POST'])
@login_required
def selecionar_edicao():
    if request.method == 'POST': return redirect(url_for('editar_item', id=request.form.get('item_id')))
    return render_template('selecionar_edicao.html', itens=ItemEstoque.query.order_by(ItemEstoque.nome).all())

@app.route('/gerenciar/item/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_item(id):
    item = ItemEstoque.query.get_or_404(id)
    if request.method == 'POST':
        if request.form.get('acao') == 'excluir':
            db.session.delete(item); db.session.commit(); return redirect(url_for('dashboard'))
        item.nome = request.form.get('nome')
        item.quantidade = int(request.form.get('quantidade'))
        item.estoque_minimo = int(request.form.get('estoque_minimo'))
        item.estoque_ideal = int(request.form.get('estoque_ideal'))
        db.session.commit(); return redirect(url_for('dashboard'))
    return render_template('editar_item.html', item=item)

@app.route('/historico/entrada')
@login_required
def view_historico_entrada():
    return render_template('historico_entrada.html', logs=HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all())

@app.route('/historico/saida')
@login_required
def view_historico_saida():
    return render_template('historico_saida.html', logs=HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all())

@app.route('/historico/entrada/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_historico_entrada(id):
    log = HistoricoEntrada.query.get_or_404(id)
    if request.method == 'POST':
        if request.form.get('acao') == 'excluir':
            db.session.delete(log); db.session.commit(); return redirect(url_for('view_historico_entrada'))
        log.item_nome = request.form.get('item_nome')
        log.quantidade = int(request.form.get('quantidade'))
        db.session.commit(); return redirect(url_for('view_historico_entrada'))
    return render_template('editar_log_entrada.html', log=log)

@app.route('/historico/saida/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_historico_saida(id):
    log = HistoricoSaida.query.get_or_404(id)
    if request.method == 'POST':
        if request.form.get('acao') == 'excluir':
            db.session.delete(log); db.session.commit(); return redirect(url_for('view_historico_saida'))
        log.colaborador = request.form.get('colaborador')
        log.quantidade = int(request.form.get('quantidade'))
        db.session.commit(); return redirect(url_for('view_historico_saida'))
    return render_template('editar_log_saida.html', log=log)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
"""

# --- TEMPLATE BASE CORRIGIDO (LAYOUT LADO A LADO) ---
FILE_BASE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TdS Gestão de RH</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .sidebar { transition: transform 0.3s ease-in-out; }
    </style>
    <script>
        function toggleSidebar() {
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('overlay');
            if (sidebar.classList.contains('-translate-x-full')) {
                sidebar.classList.remove('-translate-x-full');
                overlay.classList.remove('hidden');
            } else {
                sidebar.classList.add('-translate-x-full');
                overlay.classList.add('hidden');
            }
        }
    </script>
</head>
<body class="bg-slate-50 text-slate-800">
    <!-- Mobile Header (Fora do Flex) -->
    {% if current_user.is_authenticated and not current_user.is_first_access %}
    <div class="md:hidden bg-white border-b border-slate-200 p-4 flex justify-between items-center sticky top-0 z-40">
        <button onclick="toggleSidebar()" class="text-slate-600 focus:outline-none"><i class="fas fa-bars text-xl"></i></button>
        <span class="font-bold text-lg text-slate-800">TdS Gestão</span>
        <div class="w-8"></div>
    </div>
    <div id="overlay" onclick="toggleSidebar()" class="fixed inset-0 bg-black bg-opacity-50 z-40 hidden md:hidden"></div>
    {% endif %}

    <!-- Wrapper Principal (Flex Row) -->
    <div class="{% if current_user.is_authenticated and not current_user.is_first_access %}flex h-screen overflow-hidden{% endif %}">
        
        <!-- Sidebar (Dentro do Flex) -->
        {% if current_user.is_authenticated and not current_user.is_first_access %}
        <aside id="sidebar" class="sidebar fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-slate-300 transform -translate-x-full md:translate-x-0 md:static md:flex-shrink-0 flex flex-col shadow-2xl h-full">
            <div class="h-16 flex items-center px-6 bg-slate-950 border-b border-slate-800">
                <div class="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-lg mr-3">T</div>
                <span class="font-bold text-xl text-white tracking-tight">TdS Gestão</span>
            </div>
            <div class="p-6 border-b border-slate-800">
                <div class="text-xs font-bold text-slate-500 uppercase mb-1">Olá,</div>
                <div class="text-sm font-bold text-white truncate">{{ current_user.real_name }}</div>
            </div>
            <nav class="flex-1 overflow-y-auto py-4">
                <ul class="space-y-1">
                    <li><a href="/" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-home w-6 text-center mr-2 text-slate-500 group-hover:text-blue-500"></i><span class="font-medium">Início</span></a></li>
                    
                    {% if current_user.role == 'Master' %}
                    <li><a href="/admin/usuarios" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-users w-6 text-center mr-2 text-slate-500 group-hover:text-blue-500"></i><span class="font-medium">Funcionários</span></a></li>
                    {% endif %}
                    
                    <li><a href="/logout" class="flex items-center px-6 py-3 hover:bg-red-900/20 hover:text-red-400 transition group mt-8"><i class="fas fa-sign-out-alt w-6 text-center mr-2 text-slate-500 group-hover:text-red-400"></i><span class="font-medium">Sair</span></a></li>
                </ul>
            </nav>
        </aside>
        {% endif %}

        <!-- Conteúdo Principal (Dentro do Flex, ocupa o resto) -->
        <div class="flex-1 h-full overflow-y-auto bg-slate-50 relative w-full">
            <div class="max-w-5xl mx-auto p-4 md:p-8 pb-20">
                {% with messages = get_flashed_messages() %}
                    {% if messages %}
                        {% for message in messages %}
                            <div class="mb-6 p-4 rounded-lg bg-blue-50 border border-blue-100 text-blue-700 text-sm font-medium shadow-sm flex items-center gap-3"><i class="fas fa-info-circle text-lg"></i> {{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                {% block content %}{% endblock %}
            </div>
            
            {% if current_user.is_authenticated and not current_user.is_first_access %}
            <footer class="py-6 text-center text-xs text-slate-400">&copy; 2026 TdS Gestão de RH</footer>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

# --- RECRIAÇÃO DOS TEMPLATES PRINCIPAIS (GARANTIA) ---
FILE_DASHBOARD = """
{% extends 'base.html' %}
{% block content %}
<div class="flex flex-col gap-4 mb-8">
    <div class="grid grid-cols-2 gap-4">
        <a href="/entrada" class="bg-emerald-600 hover:bg-emerald-700 text-white p-4 rounded-full shadow-lg flex items-center justify-center gap-2 transition transform active:scale-95 text-center">
            <i class="fas fa-arrow-down"></i> <span class="font-bold">ENTRADA</span>
        </a>
        <a href="/saida" class="bg-red-600 hover:bg-red-700 text-white p-4 rounded-full shadow-lg flex items-center justify-center gap-2 transition transform active:scale-95 text-center">
            <i class="fas fa-arrow-up"></i> <span class="font-bold">SAÍDA</span>
        </a>
    </div>
    <a href="/gerenciar/selecao" class="bg-slate-700 hover:bg-slate-800 text-white p-3 rounded-full shadow-md flex items-center justify-center gap-2 transition transform active:scale-95 text-sm font-semibold w-full md:w-1/2 mx-auto">
        <i class="fas fa-pencil-alt"></i> <span>EDITAR / GERENCIAR ITENS</span>
    </a>
</div>
<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <div class="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
        <h2 class="font-semibold text-slate-800">Inventário</h2>
        <div class="flex gap-2 text-[10px] font-bold uppercase">
            <span class="text-emerald-600"><i class="fas fa-circle text-[6px]"></i> Bom</span>
            <span class="text-yellow-600"><i class="fas fa-circle text-[6px]"></i> Médio</span>
            <span class="text-red-600"><i class="fas fa-circle text-[6px]"></i> Ruim</span>
        </div>
    </div>
    <div class="divide-y divide-slate-100">
        {% for item in itens %}
        <div class="px-6 py-4 flex items-center justify-between hover:bg-slate-50 transition">
            <div class="flex items-center gap-4">
                <div class="w-10 h-10 rounded-full flex items-center justify-center text-slate-500 bg-slate-100 font-bold text-xs border border-slate-200">{{ item.tamanho }}</div>
                <div><div class="font-semibold text-slate-800 text-sm">{{ item.nome }}</div><div class="text-xs text-slate-500 flex items-center gap-1">{{ item.genero }}</div></div>
            </div>
            <div class="text-right">
                <div class="text-lg font-bold {% if item.quantidade <= item.estoque_minimo %} text-red-600 {% elif item.quantidade >= item.estoque_ideal %} text-emerald-600 {% else %} text-yellow-600 {% endif %}">{{ item.quantidade }}</div>
                <div class="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Estoque</div>
            </div>
        </div>
        {% else %}
        <div class="p-12 text-center text-slate-400">Nenhum item registrado.</div>
        {% endfor %}
    </div>
</div>
{% endblock %}
"""

# --- FUNÇÕES ---
def create_backup():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = os.path.join("backup", ts)
    files = ["app.py", "requirements.txt", "Procfile", "runtime.txt"]
    for root, _, fs in os.walk("templates"):
        for f in fs: files.append(os.path.join(root, f))
    for f in files:
        if os.path.exists(f):
            dest = os.path.join(backup, f)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(f, dest)

def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f: f.write(content.strip())
    print(f"Atualizado: {path}")

def git_update():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO V14 LAYOUT! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V14 (LAYOUT FIX): {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    write_file("templates/base.html", FILE_BASE) # Correção Crítica Aqui
    write_file("templates/dashboard.html", FILE_DASHBOARD)
    
    # Mantem os outros templates necessarios
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



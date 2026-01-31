import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Thay RH"
COMMIT_MSG = "V12: Sidebar, Entrada Pre-Definida, Historico Detalhado e Gestao Users"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""
FILE_REQ = """flask\nflask-sqlalchemy\npsycopg2-binary\ngunicorn\nflask-login\nwerkzeug"""
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Lógica atualizada para Entrada 'Outros' e Rotas V11) ---
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
app.secret_key = 'chave_v12_master_secret'

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
        # Garante colunas
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS genero VARCHAR(20)"))
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS estoque_minimo INTEGER DEFAULT 5"))
                conn.commit()
        except: pass
        # Garante Master
        if not User.query.filter_by(username='Thaynara').first():
            master = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
            master.set_password('1855')
            db.session.add(master)
            db.session.commit()
except Exception: pass

# --- ROTAS DE AUTENTICAÇÃO ---

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

# --- ROTAS DE ADMINISTRAÇÃO (V11) ---

@app.route('/admin/usuarios', methods=['GET', 'POST'])
@login_required
def gerenciar_usuarios():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    
    senha_gerada = None
    novo_user_nome = None
    
    if request.method == 'POST':
        username = request.form.get('username')
        if User.query.filter_by(username=username).first():
            flash('Usuário já existe.')
        else:
            senha_temp = secrets.token_hex(3)
            novo = User(username=username, real_name=request.form.get('real_name'), role=request.form.get('role'), is_first_access=True)
            novo.set_password(senha_temp)
            db.session.add(novo)
            db.session.commit()
            senha_gerada = senha_temp
            novo_user_nome = username
            flash('Usuário criado.')
            
    users = User.query.all()
    return render_template('admin_usuarios.html', users=users, senha_gerada=senha_gerada, novo_user=novo_user_nome)

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
            if user.username != 'Thaynara': user.role = request.form.get('role')
            db.session.commit()
            flash('Atualizado.')
            return redirect(url_for('gerenciar_usuarios'))
    return render_template('editar_usuario.html', user=user)

# --- ROTAS PRINCIPAIS ---

@app.route('/')
@login_required
def dashboard():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    try:
        itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
        return render_template('dashboard.html', itens=itens, total_pecas=sum(i.quantidade for i in itens), total_itens=len(itens))
    except: return "Erro DB", 500

@app.route('/entrada', methods=['GET', 'POST'])
@login_required
def entrada():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    if request.method == 'POST':
        try:
            # Lógica para "Outros"
            nome_select = request.form.get('nome_select')
            if nome_select == 'Outros':
                nome = request.form.get('nome_outros')
            else:
                nome = nome_select

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
                flash(f'Novo item cadastrado: {{nome}}')
            
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
            db.session.delete(item)
            db.session.commit()
            return redirect(url_for('dashboard'))
        item.nome = request.form.get('nome')
        item.quantidade = int(request.form.get('quantidade'))
        item.estoque_minimo = int(request.form.get('estoque_minimo'))
        item.estoque_ideal = int(request.form.get('estoque_ideal'))
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('editar_item.html', item=item)

@app.route('/historico/entrada')
@login_required
def view_historico_entrada():
    return render_template('historico_entrada.html', logs=HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all())

@app.route('/historico/saida')
@login_required
def view_historico_saida():
    return render_template('historico_saida.html', logs=HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all())

# Rotas de edição de histórico (mantidas)
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

# --- TEMPLATE BASE (V11 SIDEBAR) ---
FILE_BASE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Thay RH</title>
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
    {% if current_user.is_authenticated and not current_user.is_first_access %}
    <div class="md:hidden bg-white border-b border-slate-200 p-4 flex justify-between items-center sticky top-0 z-40">
        <button onclick="toggleSidebar()" class="text-slate-600 focus:outline-none"><i class="fas fa-bars text-xl"></i></button>
        <span class="font-bold text-lg text-slate-800">Thay RH</span>
        <div class="w-8"></div>
    </div>
    <div id="overlay" onclick="toggleSidebar()" class="fixed inset-0 bg-black bg-opacity-50 z-40 hidden md:hidden"></div>
    <aside id="sidebar" class="sidebar fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-slate-300 transform -translate-x-full md:translate-x-0 md:static md:h-screen md:flex-shrink-0 flex flex-col shadow-2xl">
        <div class="h-16 flex items-center px-6 bg-slate-950 border-b border-slate-800">
            <div class="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-lg mr-3">T</div>
            <span class="font-bold text-xl text-white tracking-tight">Thay RH</span>
        </div>
        <div class="p-6 border-b border-slate-800">
            <div class="text-xs font-bold text-slate-500 uppercase mb-1">Logado como</div>
            <div class="text-sm font-bold text-white">{{ current_user.real_name }}</div>
            <div class="text-xs text-blue-400 mt-1">{{ current_user.role }}</div>
        </div>
        <nav class="flex-1 overflow-y-auto py-4">
            <ul class="space-y-1">
                <li><a href="/" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-home w-6 text-center mr-2 text-slate-500 group-hover:text-blue-500"></i><span class="font-medium">Início</span></a></li>
                <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Operacional</li>
                <li><a href="/entrada" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-arrow-down w-6 text-center mr-2 text-slate-500 group-hover:text-emerald-500"></i><span class="font-medium">Entrada</span></a></li>
                <li><a href="/saida" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-arrow-up w-6 text-center mr-2 text-slate-500 group-hover:text-red-500"></i><span class="font-medium">Saída</span></a></li>
                <li><a href="/gerenciar/selecao" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-boxes w-6 text-center mr-2 text-slate-500 group-hover:text-yellow-500"></i><span class="font-medium">Inventário</span></a></li>
                <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Relatórios</li>
                <li><a href="/historico/entrada" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-history w-6 text-center mr-2 text-slate-500"></i><span class="font-medium">Hist. Entradas</span></a></li>
                <li><a href="/historico/saida" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-clipboard-list w-6 text-center mr-2 text-slate-500"></i><span class="font-medium">Hist. Saídas</span></a></li>
                {% if current_user.role == 'Master' %}
                <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Administração</li>
                <li><a href="/admin/usuarios" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group border-l-4 border-transparent hover:border-blue-500 bg-slate-800/50"><i class="fas fa-users-cog w-6 text-center mr-2 text-blue-400"></i><span class="font-medium text-blue-100">Funcionários</span></a></li>
                {% endif %}
            </ul>
        </nav>
        <div class="p-4 border-t border-slate-800">
            <a href="/logout" class="flex items-center justify-center w-full bg-slate-800 hover:bg-red-900/50 text-slate-300 hover:text-red-400 py-3 rounded-lg transition font-bold text-sm"><i class="fas fa-sign-out-alt mr-2"></i> Sair</a>
        </div>
    </aside>
    {% endif %}
    <div class="{% if current_user.is_authenticated and not current_user.is_first_access %}md:flex md:flex-row h-screen overflow-hidden{% endif %}">
        <div class="flex-1 h-full overflow-y-auto bg-slate-50">
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
            <footer class="py-6 text-center text-xs text-slate-400">&copy; 2026 Thay RH System. Enterprise V12</footer>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

# --- TEMPLATE ENTRADA ATUALIZADO (SELECT PRÉ-DEFINIDO) ---
FILE_ENTRADA = """
{% extends 'base.html' %}
{% block content %}
<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <div class="bg-emerald-50 px-6 py-4 border-b border-emerald-100">
        <h2 class="text-lg font-bold text-emerald-800">Nova Entrada</h2>
        <p class="text-xs text-emerald-600">Adicione itens pré-definidos ou crie novos.</p>
    </div>
    <form action="/entrada" method="POST" class="p-6 space-y-5">
        <div>
            <label class="label-pro">Item / Uniforme</label>
            <select name="nome_select" id="nome_select" class="input-pro" onchange="verificarOutros(this)">
                <option value="Camisa Tático">Camisa Tático</option>
                <option value="Calça Tático">Calça Tático</option>
                <option value="Camisa Portaria">Camisa Portaria</option>
                <option value="Calça Portaria">Calça Portaria</option>
                <option value="Blazer Portaria">Blazer Portaria</option>
                <option value="Camisa Limpeza">Camisa Limpeza</option>
                <option value="Calça Limpeza">Calça Limpeza</option>
                <option value="Outros">Outros...</option>
            </select>
        </div>

        <!-- Campo Oculto para Outros -->
        <div id="div_outros" class="hidden animate-fade-in">
            <label class="label-pro text-blue-600">Digite o nome do Item</label>
            <input type="text" name="nome_outros" id="nome_outros" class="input-pro border-blue-300 bg-blue-50" placeholder="Ex: Sapato Social">
        </div>

        <div class="grid grid-cols-2 gap-4">
            <div><label class="label-pro">Tamanho</label><select name="tamanho" class="input-pro"><option value="P">P</option><option value="M">M</option><option value="G">G</option><option value="GG">GG</option><option value="XG">XG</option></select></div>
            <div><label class="label-pro">Gênero</label><select name="genero" class="input-pro"><option value="Masculino">Masculino</option><option value="Feminino">Feminino</option><option value="Unissex">Unissex</option></select></div>
        </div>
        <div>
            <label class="label-pro text-emerald-600">Quantidade</label>
            <input type="number" name="quantidade" min="1" value="1" class="input-pro font-bold text-lg text-emerald-700" required>
        </div>
        
        <div class="pt-4 border-t border-slate-100">
            <p class="text-xs font-bold text-slate-400 uppercase mb-3">Definição de Níveis (Opcional)</p>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="label-pro text-red-400">Mínimo (Ruim)</label><input type="number" name="estoque_minimo" value="5" class="input-pro text-xs"></div>
                <div><label class="label-pro text-emerald-400">Ideal (Bom)</label><input type="number" name="estoque_ideal" value="20" class="input-pro text-xs"></div>
            </div>
        </div>

        <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-4 rounded-lg shadow-md hover:shadow-lg transition">ADICIONAR</button>
    </form>
</div>
<script>
    function verificarOutros(select) {
        const div = document.getElementById('div_outros');
        const input = document.getElementById('nome_outros');
        if (select.value === 'Outros') {
            div.classList.remove('hidden');
            input.required = true;
            input.focus();
        } else {
            div.classList.add('hidden');
            input.required = false;
        }
    }
</script>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; color: #1e293b; font-weight: 500; outline: none; }</style>
{% endblock %}
"""

# --- TEMPLATE HISTÓRICO SAÍDA ATUALIZADO (REGISTRO DE ENTREGAS) ---
FILE_HIST_SAIDA = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6"><h2 class="text-lg font-bold text-slate-800">Registro de Entregas</h2></div>
<div class="space-y-3">
    {% for log in logs %}
    <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition relative group">
        <a href="/historico/saida/editar/{{ log.id }}" class="absolute top-4 right-4 text-slate-300 hover:text-blue-500 p-2"><i class="fas fa-pencil-alt"></i></a>
        <div class="flex justify-between items-start mb-2">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wide">{{ log.data_entrega.strftime('%d/%m/%Y') }}</div>
            <div class="bg-blue-50 text-blue-700 text-xs px-2 py-1 rounded font-bold mr-8">-{{ log.quantidade }} UN</div>
        </div>
        <div class="flex items-center gap-3 mb-3">
             <div class="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 font-bold text-xs">{{ log.colaborador[:1] }}</div>
             <div><div class="font-bold text-slate-800">{{ log.colaborador }}</div><div class="text-xs text-slate-500">Autorizado por: {{ log.coordenador }}</div></div>
        </div>
        <!-- Detalhes de Tamanho e Genero -->
        <div class="pt-3 border-t border-slate-100 text-sm text-slate-700 flex items-center gap-2">
            <i class="fas fa-tshirt text-slate-400"></i> 
            <span class="font-semibold">{{ log.item_nome }}</span>
            <span class="text-slate-300">|</span>
            <span class="bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded text-xs font-bold">{{ log.tamanho }}</span>
            <span class="text-slate-300">|</span>
            <span class="text-xs text-slate-500">{{ log.genero }}</span>
        </div>
    </div>
    {% else %}
    <div class="text-center py-10 text-slate-400">Nenhuma entrega registrada.</div>
    {% endfor %}
</div>
{% endblock %}
"""

# --- TEMPLATE ADMIN USUARIOS (V11) ---
FILE_ADMIN_USUARIOS = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center justify-between mb-8">
    <div><h2 class="text-2xl font-bold text-slate-800">Funcionários</h2><p class="text-sm text-slate-500">Gestão de acesso.</p></div>
</div>
{% if senha_gerada %}
<div class="bg-green-50 border border-green-200 p-6 rounded-xl mb-8 flex flex-col items-center justify-center text-center shadow-sm">
    <div class="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center text-green-600 mb-3"><i class="fas fa-check"></i></div>
    <h3 class="text-lg font-bold text-green-800 mb-1">Usuário Criado!</h3>
    <p class="text-sm text-green-700 mb-4">Entregue as credenciais para <strong>{{ novo_user }}</strong>.</p>
    <div class="bg-white px-6 py-3 rounded-lg border border-green-200 font-mono text-xl font-bold text-slate-800 shadow-inner">{{ senha_gerada }}</div>
</div>
{% endif %}
<div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
    <div class="lg:col-span-2">
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div class="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center"><h3 class="font-bold text-slate-700">Equipe</h3><span class="text-xs bg-slate-200 text-slate-600 px-2 py-1 rounded-full font-bold">{{ users|length }}</span></div>
            <div class="divide-y divide-slate-100">
                {% for u in users %}
                <div class="px-6 py-4 flex items-center justify-between hover:bg-slate-50 transition group">
                    <div class="flex items-center gap-4">
                        <div class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm bg-blue-100 text-blue-600">{{ u.real_name[:2].upper() }}</div>
                        <div><div class="font-bold text-slate-800">{{ u.real_name }}</div><div class="text-xs text-slate-500">{{ u.role }}</div></div>
                    </div>
                    <div class="flex items-center gap-3">
                        {% if u.is_first_access %}<span class="px-2 py-1 bg-yellow-100 text-yellow-700 text-[10px] font-bold uppercase rounded">Pendente</span>{% else %}<span class="px-2 py-1 bg-emerald-100 text-emerald-700 text-[10px] font-bold uppercase rounded">Ativo</span>{% endif %}
                        <a href="/admin/usuarios/editar/{{ u.id }}" class="w-8 h-8 flex items-center justify-center rounded-full text-slate-300 hover:bg-white hover:text-blue-600 hover:shadow border border-transparent hover:border-slate-200 transition"><i class="fas fa-pencil-alt text-xs"></i></a>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
    <div class="lg:col-span-1">
        <div class="bg-slate-800 rounded-xl shadow-lg p-6 text-white sticky top-6">
            <h3 class="font-bold text-lg mb-1">Novo Funcionário</h3>
            <form action="/admin/usuarios" method="POST" class="space-y-4 mt-4">
                <div><label class="block text-xs font-bold text-slate-400 uppercase mb-2">Nome</label><input type="text" name="real_name" class="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-3 text-sm" required></div>
                <div><label class="block text-xs font-bold text-slate-400 uppercase mb-2">Login</label><input type="text" name="username" class="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-3 text-sm" required></div>
                <div><label class="block text-xs font-bold text-slate-400 uppercase mb-2">Cargo</label><select name="role" class="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-3 text-sm"><option value="Colaborador">Colaborador</option><option value="Master">Master</option></select></div>
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-lg shadow-md transition mt-2">Criar Acesso</button>
            </form>
        </div>
    </div>
</div>
{% endblock %}
"""

# --- TEMPLATE EDITAR USUARIO (V11) ---
FILE_EDITAR_USUARIO = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-lg mx-auto">
    <div class="flex items-center justify-between mb-6"><h2 class="text-lg font-bold text-slate-800">Editar Funcionário</h2><a href="/admin/usuarios" class="text-xs font-medium text-slate-500 hover:text-slate-800">Cancelar</a></div>
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <form action="/admin/usuarios/editar/{{ user.id }}" method="POST" class="p-8 space-y-6">
            <div class="flex flex-col items-center mb-6"><div class="w-20 h-20 bg-slate-100 rounded-full flex items-center justify-center text-2xl font-bold text-slate-400 mb-3">{{ user.real_name[:2].upper() }}</div><div class="text-sm font-mono text-slate-400">ID: {{ user.id }}</div></div>
            <div class="space-y-4">
                <div><label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Nome</label><input type="text" name="real_name" value="{{ user.real_name }}" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-slate-800 font-bold"></div>
                <div><label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Login</label><input type="text" name="username" value="{{ user.username }}" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-slate-800" {% if user.username == 'Thaynara' %}readonly{% endif %}></div>
                <div><label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Cargo</label><select name="role" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-slate-800" {% if user.username == 'Thaynara' %}disabled{% endif %}><option value="Colaborador" {% if user.role == 'Colaborador' %}selected{% endif %}>Colaborador</option><option value="Master" {% if user.role == 'Master' %}selected{% endif %}>Master</option></select></div>
            </div>
            <div class="pt-6 border-t border-slate-100 flex flex-col gap-3">
                <button type="submit" name="acao" value="salvar" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-lg shadow transition">SALVAR</button>
                <div class="grid grid-cols-2 gap-3">
                    <button type="submit" name="acao" value="resetar_senha" class="bg-yellow-50 hover:bg-yellow-100 text-yellow-700 font-bold py-3 rounded-lg text-xs border border-yellow-200">RESETAR SENHA</button>
                    {% if user.username != 'Thaynara' %}<button type="submit" name="acao" value="excluir" class="bg-red-50 hover:bg-red-100 text-red-600 font-bold py-3 rounded-lg text-xs border border-red-200" onclick="return confirm('Excluir?')">EXCLUIR</button>{% endif %}
                </div>
            </div>
        </form>
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
        print("\n>>> SUCESSO V12 COMPLETA! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V12 COMPLETA: {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    
    write_file("templates/base.html", FILE_BASE)
    write_file("templates/entrada.html", FILE_ENTRADA)
    write_file("templates/historico_saida.html", FILE_HIST_SAIDA)
    write_file("templates/admin_usuarios.html", FILE_ADMIN_USUARIOS)
    write_file("templates/editar_usuario.html", FILE_EDITAR_USUARIO)
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



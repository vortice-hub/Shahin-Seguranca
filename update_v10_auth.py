import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Thay RH"
COMMIT_MSG = "V10: Sistema de Login, Master User e Primeiro Acesso"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""

# Adicionado Flask-Login e Werkzeug
FILE_REQ = """flask
flask-sqlalchemy
psycopg2-binary
gunicorn
flask-login
werkzeug
"""

FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Com Autenticação) ---
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
app.secret_key = 'chave_v10_auth_super_secreta'

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

# --- CONFIGURAÇÃO DE LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Se não estiver logado, manda pra cá

def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

# --- MODELOS ---

# Novo Modelo de Usuário
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    real_name = db.Column(db.String(100))
    role = db.Column(db.String(50)) # Ex: Master, Almoxarife, RH
    is_first_access = db.Column(db.Boolean, default=True) # Obriga troca de senha
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

# --- BOOT & GENESIS (Criação do Master) ---
try:
    with app.app_context():
        db.create_all()
        # Verifica se o Master existe, se não, cria.
        if not User.query.filter_by(username='Thaynara').first():
            master = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
            master.set_password('1855')
            db.session.add(master)
            db.session.commit()
            logger.info("Usuario Master Thaynara criado.")
except Exception as e: 
    logger.error(f"Erro Boot: {{e}}")

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            # Se for primeiro acesso, força troca de senha
            if user.is_first_access:
                return redirect(url_for('primeiro_acesso'))
            return redirect(url_for('dashboard'))
        else:
            flash('Usuário ou senha incorretos.')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.')
    return redirect(url_for('login'))

@app.route('/primeiro-acesso', methods=['GET', 'POST'])
@login_required
def primeiro_acesso():
    if not current_user.is_first_access:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        confirmacao = request.form.get('confirmacao')
        
        if nova_senha == confirmacao:
            current_user.set_password(nova_senha)
            current_user.is_first_access = False
            db.session.commit()
            flash('Senha atualizada com sucesso! Bem-vindo.')
            return redirect(url_for('dashboard'))
        else:
            flash('As senhas não coincidem.')
            
    return render_template('primeiro_acesso.html')

# --- ROTAS DE GESTÃO DE USUÁRIOS (MASTER) ---

@app.route('/admin/usuarios', methods=['GET', 'POST'])
@login_required
def gerenciar_usuarios():
    # Apenas Master (Thaynara) ou quem tiver role Master pode acessar
    if current_user.role != 'Master':
        flash('Acesso negado. Apenas Master.')
        return redirect(url_for('dashboard'))
        
    senha_gerada = None
    novo_usuario_nome = None
    
    if request.method == 'POST':
        # Criar novo usuário
        username = request.form.get('username')
        real_name = request.form.get('real_name')
        role = request.form.get('role')
        
        if User.query.filter_by(username=username).first():
            flash('Erro: Nome de usuário já existe.')
        else:
            # Gera senha aleatoria de 6 digitos
            senha_temp = secrets.token_hex(3) 
            
            novo_user = User(username=username, real_name=real_name, role=role, is_first_access=True)
            novo_user.set_password(senha_temp)
            db.session.add(novo_user)
            db.session.commit()
            
            senha_gerada = senha_temp
            novo_usuario_nome = username
            flash(f'Usuário criado!')

    users = User.query.all()
    return render_template('admin_usuarios.html', users=users, senha_gerada=senha_gerada, novo_user=novo_usuario_nome)

# --- ROTAS PRINCIPAIS (PROTEGIDAS) ---

@app.route('/')
@login_required
def dashboard():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    
    try:
        itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
        total_pecas = sum(i.quantidade for i in itens)
        total_itens = len(itens)
        return render_template('dashboard.html', itens=itens, total_pecas=total_pecas, total_itens=total_itens)
    except Exception as e:
        return f"Erro DB: {{e}}", 500

@app.route('/entrada', methods=['GET', 'POST'])
@login_required
def entrada():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            tamanho = request.form.get('tamanho')
            genero = request.form.get('genero')
            quantidade = int(request.form.get('quantidade') or 1)
            est_min = int(request.form.get('estoque_minimo') or 5)
            est_ideal = int(request.form.get('estoque_ideal') or 20)
            
            item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
            if item:
                item.quantidade += quantidade
                item.estoque_minimo = est_min
                item.estoque_ideal = est_ideal
                item.data_atualizacao = get_brasil_time()
                flash(f'Estoque atualizado: {{nome}}')
            else:
                novo = ItemEstoque(nome=nome, tamanho=tamanho, genero=genero, quantidade=quantidade, estoque_minimo=est_min, estoque_ideal=est_ideal)
                novo.data_atualizacao = get_brasil_time()
                db.session.add(novo)
                flash(f'Novo item cadastrado: {{nome}}')
            
            log = HistoricoEntrada(item_nome=f"{{nome}} ({{genero}}-{{tamanho}})", quantidade=quantidade)
            db.session.add(log)
            db.session.commit()
            return redirect(url_for('entrada'))
        except Exception as e:
            db.session.rollback()
            return f"Erro: {{e}}", 500
    return render_template('entrada.html')

@app.route('/saida', methods=['GET', 'POST'])
@login_required
def saida():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    try:
        if request.method == 'POST':
            item_id = request.form.get('item_id')
            qtd_saida = int(request.form.get('quantidade') or 1)
            data_input = request.form.get('data')
            
            item = ItemEstoque.query.get(item_id)
            if not item: return redirect(url_for('saida'))

            if item.quantidade >= qtd_saida:
                item.quantidade -= qtd_saida
                item.data_atualizacao = get_brasil_time()
                try: dt = datetime.strptime(data_input, '%Y-%m-%d')
                except: dt = get_brasil_time()
                
                log = HistoricoSaida(
                    coordenador=request.form.get('coordenador'),
                    colaborador=request.form.get('colaborador'),
                    item_nome=item.nome,
                    tamanho=item.tamanho,
                    genero=item.genero,
                    quantidade=qtd_saida,
                    data_entrega=dt
                )
                db.session.add(log)
                db.session.commit()
                flash(f'Saída registrada!')
                return redirect(url_for('dashboard'))
            else:
                flash(f'Erro: Estoque insuficiente.')
                return redirect(url_for('saida'))
        
        itens = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).order_by(ItemEstoque.nome).all()
        return render_template('saida.html', itens=itens)
    except Exception as e:
        return f"Erro: {{e}}", 500

@app.route('/gerenciar/selecao', methods=['GET', 'POST'])
@login_required
def selecionar_edicao():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        if item_id: return redirect(url_for('editar_item', id=item_id))
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('selecionar_edicao.html', itens=itens)

@app.route('/gerenciar/item/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_item(id):
    item = ItemEstoque.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            db.session.delete(item)
            db.session.commit()
            flash('Item excluído.')
            return redirect(url_for('dashboard'))
        item.nome = request.form.get('nome')
        item.tamanho = request.form.get('tamanho')
        item.genero = request.form.get('genero')
        item.quantidade = int(request.form.get('quantidade'))
        item.estoque_minimo = int(request.form.get('estoque_minimo'))
        item.estoque_ideal = int(request.form.get('estoque_ideal'))
        item.data_atualizacao = get_brasil_time()
        db.session.commit()
        flash('Item atualizado.')
        return redirect(url_for('dashboard'))
    return render_template('editar_item.html', item=item)

@app.route('/historico/entrada')
@login_required
def view_historico_entrada():
    logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all()
    return render_template('historico_entrada.html', logs=logs)

@app.route('/historico/entrada/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_historico_entrada(id):
    log = HistoricoEntrada.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            db.session.delete(log)
            db.session.commit()
            flash('Registro excluído.')
            return redirect(url_for('view_historico_entrada'))
        log.item_nome = request.form.get('item_nome')
        log.quantidade = int(request.form.get('quantidade'))
        try: log.data_hora = datetime.strptime(request.form.get('data'), '%Y-%m-%dT%H:%M')
        except: pass
        db.session.commit()
        flash('Registro corrigido.')
        return redirect(url_for('view_historico_entrada'))
    return render_template('editar_log_entrada.html', log=log)

@app.route('/historico/saida')
@login_required
def view_historico_saida():
    logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all()
    return render_template('historico_saida.html', logs=logs)

@app.route('/historico/saida/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_historico_saida(id):
    log = HistoricoSaida.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            db.session.delete(log)
            db.session.commit()
            flash('Registro excluído.')
            return redirect(url_for('view_historico_saida'))
        log.coordenador = request.form.get('coordenador')
        log.colaborador = request.form.get('colaborador')
        log.item_nome = request.form.get('item_nome')
        log.quantidade = int(request.form.get('quantidade'))
        try: log.data_entrega = datetime.strptime(request.form.get('data'), '%Y-%m-%d')
        except: pass
        db.session.commit()
        flash('Registro corrigido.')
        return redirect(url_for('view_historico_saida'))
    return render_template('editar_log_saida.html', log=log)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
"""

# --- TEMPLATES ---

FILE_BASE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Thay RH | Secure</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>body { font-family: 'Inter', sans-serif; }</style>
</head>
<body class="bg-slate-50 text-slate-800">
    {% if current_user.is_authenticated and not current_user.is_first_access %}
    <nav class="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div class="max-w-4xl mx-auto px-4">
            <div class="flex justify-between items-center h-16">
                <a href="/" class="flex items-center gap-2 text-slate-800 hover:text-blue-600 transition">
                    <div class="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-lg">T</div>
                    <span class="font-bold text-xl tracking-tight">Thay RH</span>
                </a>
                <div class="flex items-center gap-3">
                    {% if current_user.role == 'Master' %}
                    <a href="/admin/usuarios" class="text-xs font-bold text-slate-500 hover:text-blue-600"><i class="fas fa-users-cog"></i> USERS</a>
                    {% endif %}
                    <a href="/logout" class="text-xs font-bold text-red-400 hover:text-red-600 ml-2"><i class="fas fa-sign-out-alt"></i> SAIR</a>
                </div>
            </div>
        </div>
    </nav>
    {% endif %}
    
    <main class="max-w-4xl mx-auto p-4 md:p-6 pb-20">
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="mb-4 p-4 rounded-lg bg-blue-50 border border-blue-100 text-blue-700 text-sm font-medium shadow-sm flex items-center gap-2">
                        <i class="fas fa-info-circle"></i> {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>
    <footer class="mt-8 text-center text-xs text-slate-400 pb-8">&copy; 2026 Thay RH System. V10 Auth</footer>
</body>
</html>
"""

FILE_LOGIN = """
{% extends 'base.html' %}
{% block content %}
<div class="flex flex-col items-center justify-center min-h-[60vh]">
    <div class="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center text-white font-bold text-3xl mb-6 shadow-lg shadow-blue-200">T</div>
    <div class="bg-white p-8 rounded-2xl shadow-xl border border-slate-100 w-full max-w-sm">
        <h2 class="text-xl font-bold text-center text-slate-800 mb-6">Acesso Restrito</h2>
        <form action="/login" method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-400 uppercase mb-2">Usuário</label>
                <input type="text" name="username" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500" placeholder="Seu usuário" required>
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 uppercase mb-2">Senha</label>
                <input type="password" name="password" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500" placeholder="••••••" required>
            </div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-lg shadow-lg transition">ENTRAR NO SISTEMA</button>
        </form>
    </div>
    <p class="text-xs text-slate-400 mt-6">Sistema Interno Thay RH &copy; 2026</p>
</div>
{% endblock %}
"""

FILE_PRIMEIRO_ACESSO = """
{% extends 'base.html' %}
{% block content %}
<div class="flex flex-col items-center justify-center min-h-[60vh]">
    <div class="bg-white p-8 rounded-2xl shadow-xl border-l-4 border-yellow-400 w-full max-w-sm">
        <h2 class="text-xl font-bold text-slate-800 mb-2">Primeiro Acesso</h2>
        <p class="text-sm text-slate-500 mb-6">Por segurança, você deve definir uma nova senha pessoal.</p>
        <form action="/primeiro-acesso" method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-400 uppercase mb-2">Nova Senha</label>
                <input type="password" name="nova_senha" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 focus:outline-none focus:border-yellow-500" required>
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 uppercase mb-2">Confirmar Senha</label>
                <input type="password" name="confirmacao" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 focus:outline-none focus:border-yellow-500" required>
            </div>
            <button type="submit" class="w-full bg-yellow-500 hover:bg-yellow-600 text-white font-bold py-4 rounded-lg shadow-lg transition">SALVAR E ACESSAR</button>
        </form>
    </div>
</div>
{% endblock %}
"""

FILE_ADMIN_USUARIOS = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center justify-between mb-6">
    <h2 class="text-lg font-bold text-slate-800">Gestão de Usuários</h2>
    <a href="/" class="text-xs font-bold text-slate-400 hover:text-slate-600">VOLTAR</a>
</div>

{% if senha_gerada %}
<div class="bg-green-100 border border-green-200 text-green-800 p-6 rounded-xl mb-6 text-center">
    <p class="text-sm font-bold uppercase tracking-wide text-green-600 mb-2">Usuário Criado com Sucesso</p>
    <div class="text-lg mb-1">Usuário: <strong>{{ novo_user }}</strong></div>
    <div class="text-2xl font-mono bg-white inline-block px-4 py-2 rounded border border-green-300 shadow-sm mt-2">{{ senha_gerada }}</div>
    <p class="text-xs mt-3 text-green-700">Anote esta senha temporária e entregue ao usuário.<br>Ela será válida apenas para o primeiro login.</p>
</div>
{% endif %}

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mb-8">
    <div class="bg-slate-50 px-6 py-4 border-b border-slate-100 font-bold text-slate-700">Novo Cadastro</div>
    <form action="/admin/usuarios" method="POST" class="p-6 space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div><label class="label-pro">Usuário (Login)</label><input type="text" name="username" class="input-pro" placeholder="ex: joao.silva" required></div>
            <div><label class="label-pro">Nome Completo</label><input type="text" name="real_name" class="input-pro" placeholder="João da Silva" required></div>
        </div>
        <div>
            <label class="label-pro">Função / Cargo</label>
            <select name="role" class="input-pro">
                <option value="Colaborador">Colaborador</option>
                <option value="RH">RH</option>
                <option value="Almoxarife">Almoxarife</option>
                <option value="Master">Master (Admin)</option>
            </select>
        </div>
        <button type="submit" class="w-full bg-slate-800 hover:bg-slate-900 text-white font-bold py-3 rounded-lg">CRIAR USUÁRIO</button>
    </form>
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <table class="w-full text-left text-sm text-slate-600">
        <thead class="bg-slate-50 text-xs uppercase text-slate-400 font-bold">
            <tr><th class="px-6 py-3">Nome</th><th class="px-6 py-3">Login</th><th class="px-6 py-3">Função</th><th class="px-6 py-3">Status</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
            {% for u in users %}
            <tr class="hover:bg-slate-50">
                <td class="px-6 py-4 font-medium text-slate-800">{{ u.real_name }}</td>
                <td class="px-6 py-4">{{ u.username }}</td>
                <td class="px-6 py-4"><span class="bg-slate-100 text-slate-600 px-2 py-1 rounded text-xs font-bold">{{ u.role }}</span></td>
                <td class="px-6 py-4">
                    {% if u.is_first_access %}
                    <span class="text-yellow-600 text-xs font-bold"><i class="fas fa-clock"></i> Pendente</span>
                    {% else %}
                    <span class="text-emerald-600 text-xs font-bold"><i class="fas fa-check"></i> Ativo</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; }</style>
{% endblock %}
"""

# Re-escrevendo Dashboard para ter Link correto de Inicio
FILE_DASHBOARD = """
{% extends 'base.html' %}
{% block content %}
<div class="grid grid-cols-2 gap-4 mb-8">
    <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Total Peças</div>
        <div class="text-3xl font-bold text-slate-800">{{ total_pecas }}</div>
    </div>
    <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Tipos</div>
        <div class="text-3xl font-bold text-slate-800">{{ total_itens }}</div>
    </div>
</div>

<div class="grid grid-cols-3 gap-4 mb-8">
    <a href="/entrada" class="col-span-1 bg-white border border-slate-200 hover:border-emerald-500 p-4 rounded-xl shadow-sm hover:shadow-md transition flex flex-col items-center justify-center">
        <i class="fas fa-arrow-down text-2xl text-emerald-600 mb-2"></i>
        <span class="font-bold text-xs text-slate-700">Entrada</span>
    </a>
    <a href="/saida" class="col-span-1 bg-white border border-slate-200 hover:border-red-500 p-4 rounded-xl shadow-sm hover:shadow-md transition flex flex-col items-center justify-center">
        <i class="fas fa-arrow-up text-2xl text-red-600 mb-2"></i>
        <span class="font-bold text-xs text-slate-700">Saída</span>
    </a>
    <a href="/gerenciar/selecao" class="col-span-1 bg-slate-800 hover:bg-slate-700 p-4 rounded-xl shadow-sm hover:shadow-md transition flex flex-col items-center justify-center">
        <i class="fas fa-cogs text-2xl text-white mb-2"></i>
        <span class="font-bold text-xs text-white">Gerenciar</span>
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
                <div>
                    <div class="font-semibold text-slate-800 text-sm">{{ item.nome }}</div>
                    <div class="text-xs text-slate-500 flex items-center gap-1">{{ item.genero }}</div>
                </div>
            </div>
            <div class="text-right">
                <div class="text-lg font-bold 
                    {% if item.quantidade <= item.estoque_minimo %} text-red-600
                    {% elif item.quantidade >= item.estoque_ideal %} text-emerald-600
                    {% else %} text-yellow-600 {% endif %}">
                    {{ item.quantidade }}
                </div>
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
        print("\n>>> SUCESSO V10 AUTH! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V10 AUTH: {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    
    # Templates
    write_file("templates/base.html", FILE_BASE)
    write_file("templates/login.html", FILE_LOGIN) # Novo
    write_file("templates/primeiro_acesso.html", FILE_PRIMEIRO_ACESSO) # Novo
    write_file("templates/admin_usuarios.html", FILE_ADMIN_USUARIOS) # Novo
    write_file("templates/dashboard.html", FILE_DASHBOARD) # Atualizado (remover duplicacao se houver)
    
    # Mantendo os antigos necessarios
    # O script não apaga os que não citei, então Entrada, Saida, Historicos continuam lá
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



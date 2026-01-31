import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Thay RH"
REPO_URL = "https://github.com/AppMotoristaPro/Thay-RH.git"
COMMIT_MSG = "Setup Inicial: Estrutura Flask + Modulo Estoque (Correção)"
DB_URL = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONTEÚDO DOS ARQUIVOS (Mantido para garantir integridade) ---

FILE_REQ = """flask
flask-sqlalchemy
psycopg2-binary
gunicorn
"""

FILE_PROCFILE = """web: gunicorn app:app"""

FILE_APP = f"""
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'chave_secreta_thay_rh'

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', '{DB_URL}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class ItemEstoque(db.Model):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50))
    tamanho = db.Column(db.String(10))
    quantidade = db.Column(db.Integer, default=0)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('estoque.html', itens=itens)

@app.route('/adicionar', methods=['POST'])
def adicionar():
    nome = request.form.get('nome')
    categoria = request.form.get('categoria')
    tamanho = request.form.get('tamanho')
    quantidade = request.form.get('quantidade')
    
    novo_item = ItemEstoque(nome=nome, categoria=categoria, tamanho=tamanho, quantidade=quantidade)
    db.session.add(novo_item)
    db.session.commit()
    flash('Item adicionado com sucesso!')
    return redirect(url_for('index'))

@app.route('/atualizar/<int:id>', methods=['POST'])
def atualizar(id):
    item = ItemEstoque.query.get_or_404(id)
    operacao = request.form.get('operacao')
    qtd = int(request.form.get('quantidade_mov', 0))
    
    if operacao == 'entrada':
        item.quantidade += qtd
    elif operacao == 'saida':
        item.quantidade -= qtd
        if item.quantidade < 0: item.quantidade = 0
        
    item.data_atualizacao = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/deletar/<int:id>')
def deletar(id):
    item = ItemEstoque.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
"""

FILE_HTML_BASE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Thay RH - Gestão</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100 text-gray-800">
    <nav class="bg-blue-900 text-white p-4 shadow-lg">
        <div class="container mx-auto flex justify-between items-center">
            <h1 class="text-xl font-bold"><i class="fas fa-users-cog mr-2"></i>Thay RH</h1>
            <span class="text-sm bg-blue-700 px-2 py-1 rounded">Admin</span>
        </div>
    </nav>
    <main class="container mx-auto p-4 pb-20">
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="bg-green-100 border-l-4 border-green-500 text-green-700 p-4 mb-4" role="alert">
                        <p>{{ message }}</p>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>
    <footer class="fixed bottom-0 w-full bg-white border-t border-gray-200 p-2 text-center text-xs text-gray-500">
        Sistema Thay RH &copy; 2024
    </footer>
</body>
</html>
"""

FILE_HTML_ESTOQUE = """
{% extends 'base.html' %}
{% block content %}
<div class="bg-white rounded-lg shadow p-6 mb-6">
    <h2 class="text-lg font-bold mb-4 text-blue-900 border-b pb-2">Novo Item</h2>
    <form action="/adicionar" method="POST" class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <input type="text" name="nome" placeholder="Nome do Item (ex: Camisa Polo)" class="p-3 border rounded w-full" required>
        <div class="flex gap-2">
            <select name="categoria" class="p-3 border rounded w-full">
                <option value="Uniforme">Uniforme</option>
                <option value="EPI">EPI</option>
                <option value="Escritorio">Escritório</option>
                <option value="Outros">Outros</option>
            </select>
            <input type="text" name="tamanho" placeholder="Tam." class="p-3 border rounded w-1/4">
        </div>
        <input type="number" name="quantidade" placeholder="Qtd Inicial" class="p-3 border rounded w-full" required>
        <button type="submit" class="bg-green-600 text-white font-bold p-3 rounded hover:bg-green-700 md:col-span-2">
            <i class="fas fa-plus mr-2"></i>Cadastrar
        </button>
    </form>
</div>
<div class="grid grid-cols-1 gap-4">
    {% for item in itens %}
    <div class="bg-white rounded-lg shadow-md p-4 border-l-4 border-blue-500 flex flex-col">
        <div class="flex justify-between items-start mb-2">
            <div>
                <h3 class="font-bold text-lg">{{ item.nome }}</h3>
                <p class="text-sm text-gray-500">{{ item.categoria }} {% if item.tamanho %}- {{ item.tamanho }}{% endif %}</p>
            </div>
            <div class="text-2xl font-bold {% if item.quantidade < 5 %}text-red-500{% else %}text-blue-600{% endif %}">
                {{ item.quantidade }}
            </div>
        </div>
        <div class="mt-2 pt-2 border-t flex items-center justify-between">
            <form action="/atualizar/{{ item.id }}" method="POST" class="flex items-center gap-2">
                <button type="submit" name="operacao" value="saida" class="bg-red-100 text-red-600 p-2 rounded hover:bg-red-200"><i class="fas fa-minus"></i></button>
                <input type="number" name="quantidade_mov" value="1" min="1" class="w-12 text-center border rounded p-1">
                <button type="submit" name="operacao" value="entrada" class="bg-green-100 text-green-600 p-2 rounded hover:bg-green-200"><i class="fas fa-plus"></i></button>
            </form>
            <a href="/deletar/{{ item.id }}" class="text-gray-400 hover:text-red-500" onclick="return confirm('Tem certeza?')"><i class="fas fa-trash"></i></a>
        </div>
    </div>
    {% else %}
    <p class="text-center text-gray-500 py-10">Nenhum item no estoque.</p>
    {% endfor %}
</div>
{% endblock %}
"""

# --- FUNÇÕES ---

def create_backup():
    """Backup simples para garantir segurança."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join("backup", timestamp)
    files_to_check = ["app.py", "requirements.txt", "Procfile", "templates/base.html", "templates/estoque.html"]
    
    created_backup = False
    for file_path in files_to_check:
        if os.path.exists(file_path):
            if not created_backup:
                os.makedirs(backup_dir, exist_ok=True)
                created_backup = True
            dest = os.path.join(backup_dir, file_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(file_path, dest)

def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())
    print(f"Arquivo verificado: {path}")

def git_configure_and_push():
    """Configura Git do zero se necessário e faz o push."""
    try:
        # 1. Verifica se é um repo git
        if not os.path.exists('.git'):
            print("Git não inicializado. Inicializando agora...")
            subprocess.run(["git", "init"], check=True)
            subprocess.run(["git", "branch", "-M", "main"], check=True)
            print(f"Adicionando remoto: {REPO_URL}")
            subprocess.run(["git", "remote", "add", "origin", REPO_URL], check=False)
        else:
            print("Repositório Git já existe. Verificando remoto...")
            # Garante que o remoto está correto
            subprocess.run(["git", "remote", "set-url", "origin", REPO_URL], check=False)

        # 2. Add e Commit
        print("Executando Git Add...")
        subprocess.run(["git", "add", "."], check=True)
        
        print("Executando Git Commit...")
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        
        # 3. Push
        print("Executando Git Push (Isso pode pedir sua senha/token)...")
        # Tenta push simples, se falhar por conflito, tenta set-upstream
        try:
            subprocess.run(["git", "push", "-u", "origin", "main"], check=True)
        except subprocess.CalledProcessError:
            print("Push falhou (talvez conflito remoto). Tentando pull rebase...")
            subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=False)
            subprocess.run(["git", "push", "-u", "origin", "main"], check=True)
            
        print("\n>>> SUCESSO! Código enviado para o GitHub. O Render deve iniciar o deploy automaticamente. <<<")

    except subprocess.CalledProcessError as e:
        print(f"\nERRO CRÍTICO NO GIT: {e}")
        print("Dica: Se pedir senha, use seu Personal Access Token (PAT) do GitHub, não sua senha de login.")

def self_destruct():
    try:
        script_path = os.path.abspath(__file__)
        os.remove(script_path)
        print(f"Script auto-removido: {script_path}")
    except:
        pass

def main():
    print(f"--- REPARO E DEPLOY: {PROJECT_NAME} ---")
    create_backup()
    
    # Recria arquivos para garantir integridade
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    write_file("templates/base.html", FILE_HTML_BASE)
    write_file("templates/estoque.html", FILE_HTML_ESTOQUE)
    
    git_configure_and_push()
    self_destruct()

if __name__ == "__main__":
    main()



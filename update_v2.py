import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Thay RH"
COMMIT_MSG = "Update V2: Fluxo Entrada/Saida, Genero e Historicos"

# --- CONTEÚDO DOS ARQUIVOS ---

# Mantemos requirements e Procfile iguais, mas garantimos que estao la
FILE_REQ = """flask
flask-sqlalchemy
psycopg2-binary
gunicorn
"""

FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (TOTALMENTE REESCRITO PARA V2) ---
FILE_APP = """
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'chave_secreta_thay_rh'

# Configuração DB
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELOS ---
class ItemEstoque(db.Model):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20)) # Novo campo
    quantidade = db.Column(db.Integer, default=0)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow)

class HistoricoEntrada(db.Model):
    __tablename__ = 'historico_entrada'
    id = db.Column(db.Integer, primary_key=True)
    item_nome = db.Column(db.String(150)) # Guardamos o nome caso o item seja deletado
    quantidade = db.Column(db.Integer)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)

class HistoricoSaida(db.Model):
    __tablename__ = 'historico_saida'
    id = db.Column(db.Integer, primary_key=True)
    coordenador = db.Column(db.String(100))
    colaborador = db.Column(db.String(100))
    item_nome = db.Column(db.String(100))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20))
    quantidade = db.Column(db.Integer)
    data_entrega = db.Column(db.DateTime, default=datetime.utcnow)

# --- MIGRACAO AUTOMATICA SIMPLES ---
def update_db_schema():
    with app.app_context():
        # Tenta criar tabelas que nao existem
        db.create_all()
        
        # Tenta adicionar coluna genero se nao existir (Migracao Manual)
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS genero VARCHAR(20)"))
                conn.commit()
        except Exception as e:
            print(f"Aviso DB: {e}")

update_db_schema()

# --- ROTAS ---

@app.route('/')
def dashboard():
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('dashboard.html', itens=itens)

# --- FLUXO DE ENTRADA ---
@app.route('/entrada', methods=['GET', 'POST'])
def entrada():
    if request.method == 'POST':
        nome = request.form.get('nome')
        categoria = request.form.get('categoria')
        tamanho = request.form.get('tamanho')
        genero = request.form.get('genero')
        quantidade = int(request.form.get('quantidade'))
        
        # Verifica se item ja existe (mesmo nome, tamanho e genero)
        item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
        
        if item:
            item.quantidade += quantidade
            item.data_atualizacao = datetime.utcnow()
            flash(f'Adicionado +{quantidade} ao estoque de {nome}.')
        else:
            novo_item = ItemEstoque(nome=nome, categoria=categoria, tamanho=tamanho, genero=genero, quantidade=quantidade)
            db.session.add(novo_item)
            flash(f'Novo item {nome} criado com sucesso.')
            
        # Log Historico
        log = HistoricoEntrada(item_nome=f"{nome} ({genero} - {tamanho})", quantidade=quantidade)
        db.session.add(log)
        
        db.session.commit()
        return redirect(url_for('entrada'))
        
    # GET: Lista itens existentes para facilitar preenchimento (opcional, ou apenas form limpo)
    return render_template('entrada.html')

@app.route('/historico/entrada')
def view_historico_entrada():
    logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all()
    return render_template('historico_entrada.html', logs=logs)

# --- FLUXO DE SAIDA ---
@app.route('/saida', methods=['GET', 'POST'])
def saida():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        coordenador = request.form.get('coordenador')
        colaborador = request.form.get('colaborador')
        data_input = request.form.get('data')
        
        item = ItemEstoque.query.get(item_id)
        
        if item and item.quantidade > 0:
            item.quantidade -= 1 # Assume saida unitaria ou adicionar campo qtd
            item.data_atualizacao = datetime.utcnow()
            
            # Log Historico
            # Converte string data input para datetime se necessario, ou usa data atual se vazio
            data_final = datetime.strptime(data_input, '%Y-%m-%d') if data_input else datetime.utcnow()
            
            log = HistoricoSaida(
                coordenador=coordenador,
                colaborador=colaborador,
                item_nome=item.nome,
                tamanho=item.tamanho,
                genero=item.genero,
                quantidade=1,
                data_entrega=data_final
            )
            db.session.add(log)
            db.session.commit()
            flash('Entrega registrada com sucesso!')
            return redirect(url_for('dashboard'))
        else:
            flash('Erro: Item não encontrado ou estoque zerado.')
            
    itens_disponiveis = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).order_by(ItemEstoque.nome).all()
    return render_template('saida.html', itens=itens_disponiveis)

@app.route('/historico/saida')
def view_historico_saida():
    logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all()
    return render_template('historico_saida.html', logs=logs)

if __name__ == '__main__':
    app.run(debug=True)
"""

# --- TEMPLATES ---

FILE_BASE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Thay RH</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body class="bg-gray-50 text-gray-800 font-sans">
    <nav class="bg-blue-900 text-white p-4 shadow-lg sticky top-0 z-50">
        <div class="container mx-auto flex justify-between items-center">
            <a href="/" class="text-xl font-bold flex items-center gap-2">
                <i class="fas fa-id-card-alt"></i> Thay RH
            </a>
            <div>
                <a href="/" class="px-3 py-1 hover:bg-blue-800 rounded">Dash</a>
            </div>
        </div>
    </nav>
    <main class="container mx-auto p-4 max-w-2xl">
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="bg-blue-100 border-l-4 border-blue-500 text-blue-700 p-4 mb-4 rounded shadow-sm">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>
</body>
</html>
"""

FILE_DASHBOARD = """
{% extends 'base.html' %}
{% block content %}

<!-- Botões de Ação Principais -->
<div class="grid grid-cols-2 gap-4 mb-6">
    <a href="/entrada" class="bg-green-600 hover:bg-green-700 text-white p-6 rounded-xl shadow-lg flex flex-col items-center justify-center transition transform hover:scale-105">
        <i class="fas fa-box-open text-3xl mb-2"></i>
        <span class="font-bold text-lg">ENTRADA</span>
        <span class="text-xs opacity-75">Atualização de Estoque</span>
    </a>
    <a href="/saida" class="bg-blue-600 hover:bg-blue-700 text-white p-6 rounded-xl shadow-lg flex flex-col items-center justify-center transition transform hover:scale-105">
        <i class="fas fa-hand-holding-heart text-3xl mb-2"></i>
        <span class="font-bold text-lg">SAÍDA</span>
        <span class="text-xs opacity-75">Entrega de Uniforme</span>
    </a>
</div>

<!-- Lista de Estoque -->
<div class="bg-white rounded-lg shadow overflow-hidden">
    <div class="p-4 bg-gray-100 border-b flex justify-between items-center">
        <h2 class="font-bold text-gray-700"><i class="fas fa-list mr-2"></i>Estoque Atual</h2>
        <span class="text-xs bg-gray-200 px-2 py-1 rounded text-gray-600">{{ itens|length }} itens</span>
    </div>
    
    <div class="divide-y divide-gray-100">
        {% for item in itens %}
        <div class="p-4 flex justify-between items-center hover:bg-gray-50">
            <div>
                <div class="font-bold text-gray-800">{{ item.nome }}</div>
                <div class="text-sm text-gray-500">
                    <span class="mr-2"><i class="fas fa-ruler-combined"></i> {{ item.tamanho }}</span>
                    <span>
                        {% if item.genero == 'Masculino' %}
                            <i class="fas fa-mars text-blue-500"></i>
                        {% elif item.genero == 'Feminino' %}
                            <i class="fas fa-venus text-pink-500"></i>
                        {% else %}
                            <i class="fas fa-genderless"></i>
                        {% endif %}
                        {{ item.genero }}
                    </span>
                </div>
                <div class="text-xs text-gray-400 mt-1">{{ item.categoria }}</div>
            </div>
            <div class="flex flex-col items-end">
                <span class="text-2xl font-bold {% if item.quantidade < 5 %}text-red-500{% else %}text-green-600{% endif %}">
                    {{ item.quantidade }}
                </span>
                <span class="text-xs text-gray-400">unidades</span>
            </div>
        </div>
        {% else %}
        <div class="p-8 text-center text-gray-400">
            Nenhum item cadastrado. Use o botão ENTRADA.
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
"""

FILE_ENTRADA = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-4 flex justify-between items-center">
    <h2 class="text-xl font-bold text-green-700"><i class="fas fa-box-open mr-2"></i>Atualização de Estoque</h2>
    <a href="/historico/entrada" class="text-sm bg-gray-200 hover:bg-gray-300 px-3 py-1 rounded text-gray-700">
        <i class="fas fa-history mr-1"></i>Histórico
    </a>
</div>

<div class="bg-white rounded-lg shadow-lg p-6">
    <form action="/entrada" method="POST" class="space-y-4">
        
        <!-- Nome do Uniforme -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Nome do Item/Uniforme</label>
            <input type="text" name="nome" list="nomes_sugestao" class="w-full p-3 border rounded-lg focus:ring-2 focus:ring-green-500 outline-none" placeholder="Ex: Camisa Polo, Calça Brim..." required>
        </div>

        <div class="grid grid-cols-2 gap-4">
            <!-- Tamanho -->
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Tamanho</label>
                <select name="tamanho" class="w-full p-3 border rounded-lg bg-white">
                    <option value="P">P</option>
                    <option value="M">M</option>
                    <option value="G">G</option>
                    <option value="GG">GG</option>
                    <option value="XG">XG</option>
                    <option value="Unico">Único</option>
                </select>
            </div>
            
            <!-- Genero -->
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Gênero</label>
                <select name="genero" class="w-full p-3 border rounded-lg bg-white">
                    <option value="Masculino">Masculino</option>
                    <option value="Feminino">Feminino</option>
                    <option value="Unissex">Unissex</option>
                </select>
            </div>
        </div>

        <!-- Categoria -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Categoria</label>
            <select name="categoria" class="w-full p-3 border rounded-lg bg-white">
                <option value="Uniforme">Uniforme</option>
                <option value="EPI">EPI</option>
                <option value="Escritorio">Escritório</option>
            </select>
        </div>

        <!-- Quantidade -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Quantidade a Adicionar</label>
            <input type="number" name="quantidade" min="1" value="1" class="w-full p-3 border rounded-lg font-bold text-lg text-green-700" required>
        </div>

        <button type="submit" class="w-full bg-green-600 hover:bg-green-700 text-white font-bold p-4 rounded-lg shadow transition">
            CONFIRMAR ENTRADA
        </button>
    </form>
</div>
{% endblock %}
"""

FILE_SAIDA = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-4 flex justify-between items-center">
    <h2 class="text-xl font-bold text-blue-700"><i class="fas fa-hand-holding-heart mr-2"></i>Entrega de Uniforme</h2>
    <a href="/historico/saida" class="text-sm bg-gray-200 hover:bg-gray-300 px-3 py-1 rounded text-gray-700">
        <i class="fas fa-history mr-1"></i>Histórico
    </a>
</div>

<div class="bg-white rounded-lg shadow-lg p-6">
    <form action="/saida" method="POST" class="space-y-4">
        
        <!-- Selecao do Item -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Selecione o Uniforme (Estoque Disponível)</label>
            <select name="item_id" class="w-full p-3 border rounded-lg bg-white" required>
                <option value="" disabled selected>Escolha o item...</option>
                {% for item in itens %}
                <option value="{{ item.id }}">
                    {{ item.nome }} | {{ item.genero }} | Tam: {{ item.tamanho }} (Qtd: {{ item.quantidade }})
                </option>
                {% endfor %}
            </select>
        </div>

        <!-- Coordenador -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Nome do Coordenador</label>
            <input type="text" name="coordenador" class="w-full p-3 border rounded-lg" placeholder="Quem está entregando?" required>
        </div>

        <!-- Colaborador -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Nome do Colaborador</label>
            <input type="text" name="colaborador" class="w-full p-3 border rounded-lg" placeholder="Quem recebeu?" required>
        </div>

        <!-- Data -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Data da Entrega</label>
            <input type="date" name="data" class="w-full p-3 border rounded-lg" required>
        </div>

        <div class="bg-yellow-50 p-3 rounded text-sm text-yellow-700 border border-yellow-200">
            <i class="fas fa-info-circle"></i> Ao salvar, será descontada 1 unidade do estoque.
        </div>

        <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold p-4 rounded-lg shadow transition">
            REGISTRAR SAÍDA
        </button>
    </form>
</div>
{% endblock %}
"""

FILE_HIST_ENTRADA = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center gap-2 mb-4">
    <a href="/entrada" class="text-gray-500 hover:text-gray-700"><i class="fas fa-arrow-left"></i> Voltar</a>
    <h2 class="text-xl font-bold">Histórico de Entradas</h2>
</div>

<div class="bg-white rounded shadow overflow-hidden">
    <table class="min-w-full text-sm text-left text-gray-500">
        <thead class="text-xs text-gray-700 uppercase bg-gray-50">
            <tr>
                <th class="px-4 py-3">Data/Hora</th>
                <th class="px-4 py-3">Item</th>
                <th class="px-4 py-3 text-right">Qtd</th>
            </tr>
        </thead>
        <tbody>
            {% for log in logs %}
            <tr class="border-b hover:bg-gray-50">
                <td class="px-4 py-3 font-medium text-gray-900 whitespace-nowrap">
                    {{ log.data_hora.strftime('%d/%m/%Y %H:%M') }}
                </td>
                <td class="px-4 py-3">{{ log.item_nome }}</td>
                <td class="px-4 py-3 text-right font-bold text-green-600">+{{ log.quantidade }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""

FILE_HIST_SAIDA = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center gap-2 mb-4">
    <a href="/saida" class="text-gray-500 hover:text-gray-700"><i class="fas fa-arrow-left"></i> Voltar</a>
    <h2 class="text-xl font-bold">Histórico de Entregas</h2>
</div>

<div class="space-y-4">
    {% for log in logs %}
    <div class="bg-white rounded shadow p-4 border-l-4 border-blue-500">
        <div class="flex justify-between items-start">
            <div>
                <p class="text-xs text-gray-400 mb-1"><i class="far fa-calendar-alt"></i> {{ log.data_entrega.strftime('%d/%m/%Y') }}</p>
                <h3 class="font-bold text-gray-800">{{ log.colaborador }}</h3>
                <p class="text-sm text-gray-600">Recebeu: <span class="font-medium">{{ log.item_nome }} ({{ log.tamanho }}) - {{ log.genero }}</span></p>
            </div>
            <div class="text-right">
                <span class="block text-xs text-gray-400">Coord.</span>
                <span class="text-sm font-medium text-blue-900">{{ log.coordenador }}</span>
            </div>
        </div>
    </div>
    {% else %}
    <p class="text-center text-gray-500 mt-10">Nenhuma entrega registrada ainda.</p>
    {% endfor %}
</div>
{% endblock %}
"""

# --- FUNÇÕES ---

def create_backup():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join("backup", timestamp)
    
    # Lista expandida de arquivos para backup
    files_to_check = ["app.py", "requirements.txt", "Procfile"]
    for root, dirs, files in os.walk("templates"):
        for file in files:
            files_to_check.append(os.path.join(root, file))
            
    created_backup = False
    for file_path in files_to_check:
        if os.path.exists(file_path):
            if not created_backup:
                os.makedirs(backup_dir, exist_ok=True)
                created_backup = True
            dest = os.path.join(backup_dir, file_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(file_path, dest)
    print(f"Backup V1 salvo em: {backup_dir}")

def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())
    print(f"Gerado: {path}")

def git_update():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        print("Enviando atualizações...")
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO! V2 Enviada para o Render. <<<")
    except subprocess.CalledProcessError as e:
        print(f"Erro no Git: {e}")

def self_destruct():
    try:
        os.remove(os.path.abspath(__file__))
    except:
        pass

def main():
    print(f"--- ATUALIZANDO {PROJECT_NAME} PARA V2 ---")
    
    create_backup()
    
    # Core
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    
    # Templates
    write_file("templates/base.html", FILE_BASE)
    write_file("templates/dashboard.html", FILE_DASHBOARD)
    write_file("templates/entrada.html", FILE_ENTRADA)
    write_file("templates/saida.html", FILE_SAIDA)
    write_file("templates/historico_entrada.html", FILE_HIST_ENTRADA)
    write_file("templates/historico_saida.html", FILE_HIST_SAIDA)
    
    # Remover arquivo antigo se existir (estoque.html foi substituido por dashboard.html)
    if os.path.exists("templates/estoque.html"):
        os.remove("templates/estoque.html")
        print("Removido arquivo obsoleto: templates/estoque.html")
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



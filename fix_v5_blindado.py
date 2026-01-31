import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Thay RH"
COMMIT_MSG = "V5: Fix Critical Boot Error & Port Timeout"
# URL Fixa para garantir que nao seja problema de variavel de ambiente
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- ARQUIVOS DE CONFIGURAÇÃO ---

FILE_REQ = """flask
flask-sqlalchemy
psycopg2-binary
gunicorn
"""

# Forçando o Gunicorn a ouvir em 0.0.0.0 (Necessário para o Render achar a porta)
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (A prova de falhas na inicialização) ---
FILE_APP = f"""
import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import text

# Configuração de Logs para ver erros no Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'chave_de_emergencia_v5'

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
# Força o uso da string direta.
db_url = "{DB_URL_FIXA}"

# Correção para SQLAlchemy moderno (exige postgresql:// em vez de postgres://)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configurações agressivas para manter a conexão viva
db = SQLAlchemy(app, engine_options={{
    "pool_pre_ping": True,    # Testa conexão antes de usar
    "pool_size": 10,          # Mantém conexões abertas
    "pool_recycle": 300,      # Renova conexões a cada 5 min
    "connect_args": {{
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
    }}
}})

# --- MODELOS ---
class ItemEstoque(db.Model):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20)) 
    quantidade = db.Column(db.Integer, default=0)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow)

class HistoricoEntrada(db.Model):
    __tablename__ = 'historico_entrada'
    id = db.Column(db.Integer, primary_key=True)
    item_nome = db.Column(db.String(150))
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

# --- INICIALIZAÇÃO SEGURA (Evita Port Timeout) ---
# Envolvemos a criação do banco num try/except.
# Se o banco falhar no boot, o app SOBE mesmo assim, permitindo o Render detectar a porta.
try:
    with app.app_context():
        db.create_all()
        # Tenta update de coluna
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS genero VARCHAR(20)"))
                conn.commit()
        except:
            pass
        logger.info("Banco de dados inicializado com sucesso.")
except Exception as e:
    logger.error(f"ERRO CRITICO NO BOOT DO BANCO: {{e}}")
    # Não damos 'raise' aqui para não matar o servidor

# --- ROTAS ---

@app.route('/')
def dashboard():
    try:
        itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
        return render_template('dashboard.html', itens=itens)
    except Exception as e:
        logger.error(f"Erro ao carregar dashboard: {{e}}")
        return f"Erro de conexão com o banco de dados: {{str(e)}}. Tente recarregar.", 500

@app.route('/entrada', methods=['GET', 'POST'])
def entrada():
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            categoria = request.form.get('categoria')
            tamanho = request.form.get('tamanho')
            genero = request.form.get('genero')
            try:
                quantidade = int(request.form.get('quantidade'))
            except:
                quantidade = 1
            
            item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
            
            if item:
                item.quantidade += quantidade
                item.data_atualizacao = datetime.utcnow()
                flash(f'Estoque atualizado: {{nome}} (+{{quantidade}})')
            else:
                novo_item = ItemEstoque(nome=nome, categoria=categoria, tamanho=tamanho, genero=genero, quantidade=quantidade)
                db.session.add(novo_item)
                flash(f'Novo item cadastrado: {{nome}}')
                
            log = HistoricoEntrada(item_nome=f"{{nome}} ({{genero}} - {{tamanho}})", quantidade=quantidade)
            db.session.add(log)
            db.session.commit()
            return redirect(url_for('entrada'))
        except Exception as e:
            db.session.rollback()
            return f"Erro ao salvar entrada: {{e}}", 500
            
    return render_template('entrada.html')

@app.route('/historico/entrada')
def view_historico_entrada():
    try:
        logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all()
        return render_template('historico_entrada.html', logs=logs)
    except:
        return "Erro ao carregar histórico", 500

@app.route('/saida', methods=['GET', 'POST'])
def saida():
    try:
        if request.method == 'POST':
            item_id = request.form.get('item_id')
            coordenador = request.form.get('coordenador')
            colaborador = request.form.get('colaborador')
            data_input = request.form.get('data')
            
            if not item_id:
                flash("Erro: Selecione um item.")
                return redirect(url_for('saida'))

            item = ItemEstoque.query.get(item_id)
            
            if item and item.quantidade > 0:
                item.quantidade -= 1
                item.data_atualizacao = datetime.utcnow()
                
                try:
                    data_final = datetime.strptime(data_input, '%Y-%m-%d')
                except:
                    data_final = datetime.utcnow()
                
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
                return redirect(url_for('saida'))
                
        itens_disponiveis = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).order_by(ItemEstoque.nome).all()
        return render_template('saida.html', itens=itens_disponiveis)
    except Exception as e:
        logger.error(f"Erro na saida: {{e}}")
        return f"Erro de sistema: {{e}}", 500

@app.route('/historico/saida')
def view_historico_saida():
    try:
        logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all()
        return render_template('historico_saida.html', logs=logs)
    except:
        return "Erro histórico saida", 500

if __name__ == '__main__':
    # Garante que roda na porta correta localmente ou no servidor
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
"""

# --- TEMPLATES (V2) ---

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
        <div class="p-8 text-center text-gray-400">Nenhum item cadastrado.</div>
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
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Nome do Item/Uniforme</label>
            <input type="text" name="nome" list="nomes_sugestao" class="w-full p-3 border rounded-lg focus:ring-2 focus:ring-green-500 outline-none" required>
            <datalist id="nomes_sugestao">
                <option value="Camisa Polo">
                <option value="Calça Brim">
                <option value="Bota de Segurança">
                <option value="Capacete">
            </datalist>
        </div>
        <div class="grid grid-cols-2 gap-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Tamanho</label>
                <select name="tamanho" class="w-full p-3 border rounded-lg bg-white">
                    <option value="P">P</option>
                    <option value="M">M</option>
                    <option value="G">G</option>
                    <option value="GG">GG</option>
                    <option value="XG">XG</option>
                    <option value="Unico">Único</option>
                    <option value="36">36</option>
                    <option value="38">38</option>
                    <option value="40">40</option>
                    <option value="42">42</option>
                    <option value="44">44</option>
                </select>
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Gênero</label>
                <select name="genero" class="w-full p-3 border rounded-lg bg-white">
                    <option value="Masculino">Masculino</option>
                    <option value="Feminino">Feminino</option>
                    <option value="Unissex">Unissex</option>
                </select>
            </div>
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Categoria</label>
            <select name="categoria" class="w-full p-3 border rounded-lg bg-white">
                <option value="Uniforme">Uniforme</option>
                <option value="EPI">EPI</option>
                <option value="Escritorio">Escritório</option>
            </select>
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Quantidade</label>
            <input type="number" name="quantidade" min="1" value="1" class="w-full p-3 border rounded-lg font-bold text-lg text-green-700" required>
        </div>
        <button type="submit" class="w-full bg-green-600 hover:bg-green-700 text-white font-bold p-4 rounded-lg shadow transition">CONFIRMAR ENTRADA</button>
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
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Selecione o Uniforme</label>
            <select name="item_id" class="w-full p-3 border rounded-lg bg-white" required>
                <option value="" disabled selected>Escolha o item...</option>
                {% for item in itens %}
                <option value="{{ item.id }}">{{ item.nome }} | {{ item.genero }} | Tam: {{ item.tamanho }} (Disp: {{ item.quantidade }})</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Coordenador</label>
            <input type="text" name="coordenador" class="w-full p-3 border rounded-lg" required>
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Colaborador</label>
            <input type="text" name="colaborador" class="w-full p-3 border rounded-lg" required>
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Data</label>
            <input type="date" name="data" class="w-full p-3 border rounded-lg" required>
        </div>
        <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold p-4 rounded-lg shadow transition">REGISTRAR SAÍDA</button>
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
                <td class="px-4 py-3 font-medium text-gray-900 whitespace-nowrap">{{ log.data_hora.strftime('%d/%m/%Y %H:%M') }}</td>
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
                <p class="text-sm text-gray-600">Recebeu: <span class="font-medium">{{ log.item_nome }} ({{ log.tamanho }} - {{ log.genero }})</span></p>
            </div>
            <div class="text-right">
                <span class="block text-xs text-gray-400">Coord.</span>
                <span class="text-sm font-medium text-blue-900">{{ log.coordenador }}</span>
            </div>
        </div>
    </div>
    {% else %}
    <p class="text-center text-gray-500 mt-10">Nenhuma entrega registrada.</p>
    {% endfor %}
</div>
{% endblock %}
"""

# --- FUNÇÕES ---

def create_backup():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join("backup", timestamp)
    print(f"Criando backup em: {backup_dir}...")
    
    files_to_check = ["app.py", "requirements.txt", "Procfile"]
    for root, dirs, files in os.walk("templates"):
        for file in files:
            files_to_check.append(os.path.join(root, file))
            
    for file_path in files_to_check:
        if os.path.exists(file_path):
            dest = os.path.join(backup_dir, file_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(file_path, dest)

def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())
    print(f"Recriado: {path}")

def git_update():
    try:
        print("Executando Git...")
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO! Correção V5 enviada. <<<")
    except subprocess.CalledProcessError as e:
        print(f"Erro no Git: {e}")

def self_destruct():
    try:
        os.remove(os.path.abspath(__file__))
    except:
        pass

def main():
    print(f"--- CORREÇÃO BLINDADA V5: {PROJECT_NAME} ---")
    create_backup()
    
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP) # App com try/catch no boot e connection pool tunado
    
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



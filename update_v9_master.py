import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Thay RH"
COMMIT_MSG = "V9: Niveis de Estoque, Edicao Centralizada e Correcao de Historico"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""
FILE_REQ = """flask\nflask-sqlalchemy\npsycopg2-binary\ngunicorn"""
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY ---
FILE_APP = f"""
import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'chave_v9_master_secret'

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

def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

# --- MODELOS ATUALIZADOS ---
class ItemEstoque(db.Model):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), default='Uniforme')
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20)) 
    quantidade = db.Column(db.Integer, default=0)
    # Novos campos para Niveis de Estoque
    estoque_minimo = db.Column(db.Integer, default=5)  # Abaixo disso = Ruim (Vermelho)
    estoque_ideal = db.Column(db.Integer, default=20)  # Acima disso = Bom (Verde)
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

# --- BOOT COM MIGRAÇÃO ---
try:
    with app.app_context():
        db.create_all()
        # Migração manual para adicionar colunas de nível
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS genero VARCHAR(20)"))
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS estoque_minimo INTEGER DEFAULT 5"))
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS estoque_ideal INTEGER DEFAULT 20"))
                conn.commit()
        except: pass
except Exception: pass

# --- ROTAS ---
@app.route('/')
def dashboard():
    try:
        itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
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
            tamanho = request.form.get('tamanho')
            genero = request.form.get('genero')
            quantidade = int(request.form.get('quantidade') or 1)
            # Novos campos de configuração
            est_min = int(request.form.get('estoque_minimo') or 5)
            est_ideal = int(request.form.get('estoque_ideal') or 20)
            
            item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
            if item:
                item.quantidade += quantidade
                # Atualiza configurações se mudou
                item.estoque_minimo = est_min
                item.estoque_ideal = est_ideal
                item.data_atualizacao = get_brasil_time()
                flash(f'Estoque atualizado: {{nome}}')
            else:
                novo = ItemEstoque(
                    nome=nome, tamanho=tamanho, genero=genero, quantidade=quantidade,
                    estoque_minimo=est_min, estoque_ideal=est_ideal
                )
                novo.data_atualizacao = get_brasil_time()
                db.session.add(novo)
                flash(f'Novo item cadastrado: {{nome}}')
            
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

# --- NOVAS ROTAS DE GERENCIAMENTO ---

@app.route('/gerenciar/selecao', methods=['GET', 'POST'])
def selecionar_edicao():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        if item_id:
            return redirect(url_for('editar_item', id=item_id))
    
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('selecionar_edicao.html', itens=itens)

@app.route('/gerenciar/item/<int:id>', methods=['GET', 'POST'])
def editar_item(id):
    item = ItemEstoque.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        if acao == 'excluir':
            db.session.delete(item)
            db.session.commit()
            flash('Item excluído permanentemente.')
            return redirect(url_for('dashboard'))
            
        # Edição
        item.nome = request.form.get('nome')
        item.tamanho = request.form.get('tamanho')
        item.genero = request.form.get('genero')
        item.quantidade = int(request.form.get('quantidade'))
        item.estoque_minimo = int(request.form.get('estoque_minimo'))
        item.estoque_ideal = int(request.form.get('estoque_ideal'))
        item.data_atualizacao = get_brasil_time()
        
        db.session.commit()
        flash('Item atualizado com sucesso.')
        return redirect(url_for('dashboard'))
        
    return render_template('editar_item.html', item=item)

# --- ROTAS DE HISTÓRICO (AGORA COM EDIÇÃO) ---

@app.route('/historico/entrada')
def view_historico_entrada():
    logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all()
    return render_template('historico_entrada.html', logs=logs)

@app.route('/historico/entrada/editar/<int:id>', methods=['GET', 'POST'])
def editar_historico_entrada(id):
    log = HistoricoEntrada.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            db.session.delete(log)
            db.session.commit()
            flash('Registro de histórico excluído.')
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
def view_historico_saida():
    logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all()
    return render_template('historico_saida.html', logs=logs)

@app.route('/historico/saida/editar/<int:id>', methods=['GET', 'POST'])
def editar_historico_saida(id):
    log = HistoricoSaida.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            db.session.delete(log)
            db.session.commit()
            flash('Registro de saída excluído.')
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
    <title>Thay RH | V9 Master</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>body { font-family: 'Inter', sans-serif; }</style>
</head>
<body class="bg-slate-50 text-slate-800">
    <nav class="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div class="max-w-4xl mx-auto px-4">
            <div class="flex justify-between items-center h-16">
                <a href="/" class="flex items-center gap-2 text-slate-800 hover:text-blue-600 transition">
                    <div class="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-lg">T</div>
                    <span class="font-bold text-xl tracking-tight">Thay RH</span>
                </a>
                <a href="/" class="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-2 rounded-full text-sm font-semibold transition">
                    <i class="fas fa-home text-blue-500"></i> Início
                </a>
            </div>
        </div>
    </nav>
    <main class="max-w-4xl mx-auto p-4 md:p-6 pb-20">
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="mb-4 p-4 rounded-lg bg-blue-50 border border-blue-100 text-blue-700 text-sm font-medium shadow-sm flex items-center gap-2">
                        <i class="fas fa-check-circle"></i> {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>
    <footer class="mt-8 text-center text-xs text-slate-400 pb-8">&copy; 2026 Thay RH System. V9 Master</footer>
</body>
</html>
"""

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
                <div class="w-10 h-10 rounded-full flex items-center justify-center text-slate-500 bg-slate-100 font-bold text-xs border border-slate-200">
                    {{ item.tamanho }}
                </div>
                <div>
                    <div class="font-semibold text-slate-800 text-sm">{{ item.nome }}</div>
                    <div class="text-xs text-slate-500 flex items-center gap-1">
                        {{ item.genero }}
                    </div>
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

FILE_SELECIONAR = """
{% extends 'base.html' %}
{% block content %}
<div class="bg-white rounded-xl border border-slate-200 shadow-lg p-8 max-w-lg mx-auto">
    <h2 class="text-xl font-bold text-slate-800 mb-6 text-center">Gerenciar Item</h2>
    
    <form action="/gerenciar/selecao" method="POST" class="space-y-6">
        <div>
            <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Selecione o Item para Editar/Excluir</label>
            <div class="relative">
                <select name="item_id" class="w-full appearance-none bg-slate-50 border border-slate-200 rounded-lg px-4 py-4 text-slate-800 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500" required onchange="this.form.submit()">
                    <option value="" disabled selected>Clique para selecionar...</option>
                    {% for item in itens %}
                    <option value="{{ item.id }}">{{ item.nome }} - {{ item.tamanho }} ({{ item.genero }})</option>
                    {% endfor %}
                </select>
                <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-slate-500">
                    <i class="fas fa-chevron-down"></i>
                </div>
            </div>
        </div>
        <div class="text-center">
            <a href="/" class="text-sm text-slate-400 hover:text-slate-600">Cancelar</a>
        </div>
    </form>
</div>
{% endblock %}
"""

FILE_EDITAR_ITEM = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center justify-between mb-6">
    <h2 class="text-lg font-bold text-slate-800">Editar Detalhes</h2>
    <a href="/gerenciar/selecao" class="text-xs font-medium text-slate-500 hover:text-slate-800">Voltar</a>
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <form action="/gerenciar/item/{{ item.id }}" method="POST" class="p-6 space-y-6">
        
        <!-- Dados Básicos -->
        <div class="space-y-4">
            <div>
                <label class="label-pro">Nome do Item</label>
                <input type="text" name="nome" value="{{ item.nome }}" class="input-pro" required>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="label-pro">Tamanho</label>
                    <select name="tamanho" class="input-pro">
                        <option value="P" {% if item.tamanho == 'P' %}selected{% endif %}>P</option>
                        <option value="M" {% if item.tamanho == 'M' %}selected{% endif %}>M</option>
                        <option value="G" {% if item.tamanho == 'G' %}selected{% endif %}>G</option>
                        <option value="GG" {% if item.tamanho == 'GG' %}selected{% endif %}>GG</option>
                        <option value="XG" {% if item.tamanho == 'XG' %}selected{% endif %}>XG</option>
                    </select>
                </div>
                <div>
                    <label class="label-pro">Gênero</label>
                    <select name="genero" class="input-pro">
                        <option value="Masculino" {% if item.genero == 'Masculino' %}selected{% endif %}>Masculino</option>
                        <option value="Feminino" {% if item.genero == 'Feminino' %}selected{% endif %}>Feminino</option>
                        <option value="Unissex" {% if item.genero == 'Unissex' %}selected{% endif %}>Unissex</option>
                    </select>
                </div>
            </div>
        </div>

        <hr class="border-slate-100">

        <!-- Quantidade e Níveis -->
        <div class="space-y-4">
            <div>
                <label class="label-pro text-blue-600">Quantidade Atual (Ajuste Manual)</label>
                <input type="number" name="quantidade" value="{{ item.quantidade }}" class="input-pro font-bold text-blue-700" required>
            </div>
            
            <div class="grid grid-cols-2 gap-4 bg-slate-50 p-4 rounded-lg border border-slate-100">
                <div>
                    <label class="label-pro text-red-500">Estoque Ruim (Mínimo)</label>
                    <input type="number" name="estoque_minimo" value="{{ item.estoque_minimo }}" class="input-pro border-red-200 text-red-600" required>
                </div>
                <div>
                    <label class="label-pro text-emerald-500">Estoque Bom (Ideal)</label>
                    <input type="number" name="estoque_ideal" value="{{ item.estoque_ideal }}" class="input-pro border-emerald-200 text-emerald-600" required>
                </div>
                <div class="col-span-2 text-[10px] text-center text-slate-400">
                    * Entre o Mínimo e o Ideal será considerado "Médio" (Amarelo).
                </div>
            </div>
        </div>

        <div class="flex gap-3 pt-4">
            <button type="submit" name="acao" value="salvar" class="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-lg shadow transition">
                SALVAR ALTERAÇÕES
            </button>
            <button type="submit" name="acao" value="excluir" class="flex-none bg-red-100 hover:bg-red-200 text-red-600 font-bold py-3 px-6 rounded-lg transition" onclick="return confirm('Tem certeza? Isso apagará o item permanentemente.')">
                <i class="fas fa-trash"></i>
            </button>
        </div>
    </form>
</div>

<style>
    .label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }
    .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; color: #1e293b; font-weight: 500; outline: none; transition: all; }
    .input-pro:focus { background-color: #fff; border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59,130,246,0.1); }
</style>
{% endblock %}
"""

FILE_ENTRADA = """
{% extends 'base.html' %}
{% block content %}
<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <div class="bg-emerald-50 px-6 py-4 border-b border-emerald-100">
        <h2 class="text-lg font-bold text-emerald-800">Nova Entrada</h2>
        <p class="text-xs text-emerald-600">Adicione itens ou crie novos cadastros.</p>
    </div>
    <form action="/entrada" method="POST" class="p-6 space-y-5">
        <div>
            <label class="label-pro">Item</label>
            <input type="text" name="nome" list="sugestoes" class="input-pro" placeholder="Ex: Camisa Polo" required>
            <datalist id="sugestoes"><option value="Camisa Polo"><option value="Calça Brim"><option value="Bota de Segurança"></datalist>
        </div>
        <div class="grid grid-cols-2 gap-4">
            <div><label class="label-pro">Tamanho</label><select name="tamanho" class="input-pro"><option value="P">P</option><option value="M">M</option><option value="G">G</option><option value="GG">GG</option><option value="XG">XG</option></select></div>
            <div><label class="label-pro">Gênero</label><select name="genero" class="input-pro"><option value="Masculino">Masculino</option><option value="Feminino">Feminino</option><option value="Unissex">Unissex</option></select></div>
        </div>
        <div>
            <label class="label-pro text-emerald-600">Quantidade</label>
            <input type="number" name="quantidade" min="1" value="1" class="input-pro font-bold text-lg text-emerald-700" required>
        </div>
        
        <!-- Configuração de Niveis na Entrada -->
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
<div class="text-center mt-4"><a href="/historico/entrada" class="text-xs font-bold text-emerald-600 hover:underline">VER HISTÓRICO DE ENTRADAS</a></div>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; color: #1e293b; font-weight: 500; outline: none; }</style>
{% endblock %}
"""

FILE_SAIDA = """
{% extends 'base.html' %}
{% block content %}
<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <div class="bg-red-50 px-6 py-4 border-b border-red-100">
        <h2 class="text-lg font-bold text-red-800">Registrar Saída</h2>
        <p class="text-xs text-red-600">Baixa de estoque e entrega de EPI/Uniforme.</p>
    </div>
    <form action="/saida" method="POST" class="p-6 space-y-5">
        <div>
            <label class="label-pro">Selecionar Item</label>
            <div class="relative">
                <select name="item_id" class="input-pro appearance-none" required>
                    <option value="" disabled selected>Escolha...</option>
                    {% for item in itens %}
                    <option value="{{ item.id }}">{{ item.nome }} - {{ item.tamanho }} ({{ item.genero }}) | Disp: {{ item.quantidade }}</option>
                    {% endfor %}
                </select>
                <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-slate-500"><i class="fas fa-chevron-down text-xs"></i></div>
            </div>
        </div>
        <div><label class="label-pro text-red-600">Quantidade a Retirar</label><input type="number" name="quantidade" min="1" value="1" class="input-pro font-bold text-lg text-red-600" required></div>
        <div class="grid grid-cols-2 gap-4">
            <div><label class="label-pro">Coordenador</label><input type="text" name="coordenador" class="input-pro" required></div>
            <div><label class="label-pro">Colaborador</label><input type="text" name="colaborador" class="input-pro" required></div>
        </div>
        <div><label class="label-pro">Data Entrega</label><input type="date" name="data" class="input-pro" required></div>
        <button type="submit" class="w-full bg-red-600 hover:bg-red-700 text-white font-bold py-4 rounded-lg shadow-md hover:shadow-lg transition">CONFIRMAR SAÍDA</button>
    </form>
</div>
<div class="text-center mt-4"><a href="/historico/saida" class="text-xs font-bold text-red-600 hover:underline">VER HISTÓRICO DE SAÍDAS</a></div>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; color: #1e293b; font-weight: 500; outline: none; }</style>
{% endblock %}
"""

FILE_EDITAR_LOG_ENTRADA = """
{% extends 'base.html' %}
{% block content %}
<div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
    <h2 class="text-lg font-bold text-slate-800 mb-4">Editar Histórico (Entrada)</h2>
    <form action="/historico/entrada/editar/{{ log.id }}" method="POST" class="space-y-4">
        <div><label class="label-pro">Item (Texto)</label><input type="text" name="item_nome" value="{{ log.item_nome }}" class="input-pro"></div>
        <div><label class="label-pro">Quantidade Original</label><input type="number" name="quantidade" value="{{ log.quantidade }}" class="input-pro"></div>
        <div><label class="label-pro">Data/Hora</label><input type="datetime-local" name="data" value="{{ log.data_hora.strftime('%Y-%m-%dT%H:%M') }}" class="input-pro"></div>
        
        <div class="flex gap-3 pt-4">
            <button type="submit" name="acao" value="salvar" class="flex-1 bg-blue-600 text-white font-bold py-3 rounded-lg">Salvar Correção</button>
            <button type="submit" name="acao" value="excluir" class="flex-none bg-red-100 text-red-600 font-bold py-3 px-6 rounded-lg" onclick="return confirm('Excluir este registro? O estoque atual NÃO será alterado.')"><i class="fas fa-trash"></i></button>
        </div>
        <p class="text-[10px] text-slate-400 mt-2 text-center">Nota: Alterar este log não muda o estoque atual. Use o menu Gerenciar para ajustar quantidades atuais.</p>
    </form>
</div>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; }</style>
{% endblock %}
"""

FILE_EDITAR_LOG_SAIDA = """
{% extends 'base.html' %}
{% block content %}
<div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
    <h2 class="text-lg font-bold text-slate-800 mb-4">Editar Histórico (Saída)</h2>
    <form action="/historico/saida/editar/{{ log.id }}" method="POST" class="space-y-4">
        <div class="grid grid-cols-2 gap-4">
            <div><label class="label-pro">Coordenador</label><input type="text" name="coordenador" value="{{ log.coordenador }}" class="input-pro"></div>
            <div><label class="label-pro">Colaborador</label><input type="text" name="colaborador" value="{{ log.colaborador }}" class="input-pro"></div>
        </div>
        <div><label class="label-pro">Item (Texto)</label><input type="text" name="item_nome" value="{{ log.item_nome }}" class="input-pro"></div>
        <div><label class="label-pro">Quantidade</label><input type="number" name="quantidade" value="{{ log.quantidade }}" class="input-pro"></div>
        <div><label class="label-pro">Data</label><input type="date" name="data" value="{{ log.data_entrega.strftime('%Y-%m-%d') }}" class="input-pro"></div>
        
        <div class="flex gap-3 pt-4">
            <button type="submit" name="acao" value="salvar" class="flex-1 bg-blue-600 text-white font-bold py-3 rounded-lg">Salvar Correção</button>
            <button type="submit" name="acao" value="excluir" class="flex-none bg-red-100 text-red-600 font-bold py-3 px-6 rounded-lg" onclick="return confirm('Excluir este registro?')"><i class="fas fa-trash"></i></button>
        </div>
    </form>
</div>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; }</style>
{% endblock %}
"""

FILE_HIST_ENTRADA = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6"><h2 class="text-lg font-bold text-slate-800">Log de Entradas</h2></div>
<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <div class="divide-y divide-slate-100">
        {% for log in logs %}
        <div class="p-4 flex justify-between items-center hover:bg-slate-50">
            <div>
                <div class="text-xs text-slate-400 font-bold">{{ log.data_hora.strftime('%d/%m %H:%M') }}</div>
                <div class="font-medium text-slate-800 text-sm">{{ log.item_nome }}</div>
            </div>
            <div class="flex items-center gap-4">
                <span class="font-bold text-emerald-600">+{{ log.quantidade }}</span>
                <a href="/historico/entrada/editar/{{ log.id }}" class="text-slate-300 hover:text-blue-500"><i class="fas fa-pencil-alt"></i></a>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
"""

FILE_HIST_SAIDA = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6"><h2 class="text-lg font-bold text-slate-800">Log de Entregas</h2></div>
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
        <div class="pt-3 border-t border-slate-100 text-sm text-slate-700 flex items-center gap-2">
            <i class="fas fa-tshirt text-slate-400"></i> {{ log.item_nome }}
        </div>
    </div>
    {% endfor %}
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
        print("\n>>> SUCESSO V9 MASTER! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V9 MASTER: {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    
    # Templates
    write_file("templates/base.html", FILE_BASE)
    write_file("templates/dashboard.html", FILE_DASHBOARD)
    write_file("templates/selecionar_edicao.html", FILE_SELECIONAR) # Novo (Gerenciar)
    write_file("templates/editar_item.html", FILE_EDITAR_ITEM) # Form Edicao
    write_file("templates/entrada.html", FILE_ENTRADA)
    write_file("templates/saida.html", FILE_SAIDA)
    write_file("templates/historico_entrada.html", FILE_HIST_ENTRADA)
    write_file("templates/editar_log_entrada.html", FILE_EDITAR_LOG_ENTRADA) # Novo
    write_file("templates/historico_saida.html", FILE_HIST_SAIDA)
    write_file("templates/editar_log_saida.html", FILE_EDITAR_LOG_SAIDA) # Novo
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



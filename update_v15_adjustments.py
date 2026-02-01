import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V15: Separacao Estoque Master, Fluxo de Ajuste Ponto e Espelho Expansivel"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""
FILE_REQ = """flask\nflask-sqlalchemy\npsycopg2-binary\ngunicorn\nflask-login\nwerkzeug"""
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Novas Tabelas e Lógica de Aprovação) ---
FILE_APP = f"""
import os
import logging
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date, time
from sqlalchemy import text, func

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'chave_v15_ajustes_secret'

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
    
    horario_entrada = db.Column(db.String(5), default='08:00')
    horario_almoco_inicio = db.Column(db.String(5), default='12:00')
    horario_almoco_fim = db.Column(db.String(5), default='13:00')
    horario_saida = db.Column(db.String(5), default='17:00')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class PontoRegistro(db.Model):
    __tablename__ = 'ponto_registros'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_registro = db.Column(db.Date, default=get_brasil_time)
    hora_registro = db.Column(db.Time, default=lambda: get_brasil_time().time())
    tipo = db.Column(db.String(20))
    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))
    # Relacionamento
    user = db.relationship('User', backref=db.backref('pontos', lazy=True))

# NOVO MODELO: SOLICITAÇÃO DE AJUSTE
class PontoAjuste(db.Model):
    __tablename__ = 'ponto_ajustes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_referencia = db.Column(db.Date, nullable=False)
    ponto_original_id = db.Column(db.Integer, nullable=True) # Se for editar um existente
    novo_horario = db.Column(db.String(5), nullable=False) # HH:MM
    tipo_batida = db.Column(db.String(20), nullable=False) # Entrada, Saida...
    justificativa = db.Column(db.String(255))
    status = db.Column(db.String(20), default='Pendente') # Pendente, Aprovado, Reprovado
    motivo_reprovacao = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=get_brasil_time)
    
    user = db.relationship('User', backref=db.backref('ajustes', lazy=True))

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
        # Garantir tabelas e master
        if not User.query.filter_by(username='Thaynara').first():
            master = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
            master.set_password('1855')
            db.session.add(master)
            db.session.commit()
except Exception: pass

# --- ROTAS PRINCIPAIS ---

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

@app.route('/')
@login_required
def dashboard():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    
    # Dashboard LIMPO: Apenas status de ponto
    hoje = get_brasil_time().date()
    pontos_hoje = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).count()
    status_ponto = "Não Iniciado"
    if pontos_hoje == 1: status_ponto = "Trabalhando"
    elif pontos_hoje == 2: status_ponto = "Almoço"
    elif pontos_hoje == 3: status_ponto = "Trabalhando (Tarde)"
    elif pontos_hoje >= 4: status_ponto = "Dia Finalizado"
    
    return render_template('dashboard.html', status_ponto=status_ponto)

# --- ROTAS DE ESTOQUE (AGORA PROTEGIDAS E SEPARADAS) ---

@app.route('/controle-uniforme')
@login_required
def controle_uniforme():
    if current_user.role != 'Master': 
        flash('Acesso restrito ao Master.')
        return redirect(url_for('dashboard'))
    
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('controle_uniforme.html', itens=itens)

@app.route('/entrada', methods=['GET', 'POST'])
@login_required
def entrada():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    if request.method == 'POST':
        try:
            nome = request.form.get('nome_outros') if request.form.get('nome_select') == 'Outros' else request.form.get('nome_select')
            item = ItemEstoque.query.filter_by(nome=nome, tamanho=request.form.get('tamanho'), genero=request.form.get('genero')).first()
            qtd = int(request.form.get('quantidade') or 1)
            if item:
                item.quantidade += qtd
                item.estoque_minimo = int(request.form.get('estoque_minimo') or 5)
                item.estoque_ideal = int(request.form.get('estoque_ideal') or 20)
                item.data_atualizacao = get_brasil_time()
            else:
                novo = ItemEstoque(nome=nome, tamanho=request.form.get('tamanho'), genero=request.form.get('genero'), quantidade=qtd, 
                                 estoque_minimo=int(request.form.get('estoque_minimo') or 5),
                                 estoque_ideal=int(request.form.get('estoque_ideal') or 20))
                novo.data_atualizacao = get_brasil_time()
                db.session.add(novo)
            db.session.add(HistoricoEntrada(item_nome=f"{{nome}} ({{request.form.get('genero')}}-{{request.form.get('tamanho')}})", quantidade=qtd, data_hora=get_brasil_time()))
            db.session.commit()
            return redirect(url_for('controle_uniforme')) # Redireciona para o novo painel
        except: db.session.rollback()
    return render_template('entrada.html')

@app.route('/saida', methods=['GET', 'POST'])
@login_required
def saida():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    if request.method == 'POST':
        item = ItemEstoque.query.get(request.form.get('item_id'))
        qtd = int(request.form.get('quantidade') or 1)
        if item and item.quantidade >= qtd:
            item.quantidade -= qtd
            item.data_atualizacao = get_brasil_time()
            try: dt = datetime.strptime(request.form.get('data'), '%Y-%m-%d')
            except: dt = get_brasil_time()
            db.session.add(HistoricoSaida(coordenador=request.form.get('coordenador'), colaborador=request.form.get('colaborador'), item_nome=item.nome, tamanho=item.tamanho, genero=item.genero, quantidade=qtd, data_entrega=dt))
            db.session.commit()
            return redirect(url_for('controle_uniforme'))
        flash('Erro estoque.')
    itens = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).order_by(ItemEstoque.nome).all()
    return render_template('saida.html', itens=itens)

@app.route('/gerenciar/item/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_item(id):
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    item = ItemEstoque.query.get_or_404(id)
    if request.method == 'POST':
        if request.form.get('acao') == 'excluir': db.session.delete(item); db.session.commit(); return redirect(url_for('controle_uniforme'))
        item.nome = request.form.get('nome'); item.quantidade = int(request.form.get('quantidade')); item.estoque_minimo = int(request.form.get('estoque_minimo')); item.estoque_ideal = int(request.form.get('estoque_ideal')); db.session.commit(); return redirect(url_for('controle_uniforme'))
    return render_template('editar_item.html', item=item)

# --- ROTAS PONTO (ATUALIZADAS) ---

@app.route('/ponto/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    hoje = get_brasil_time().date()
    pontos_hoje = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
    proxima = "Entrada"
    if len(pontos_hoje) == 1: proxima = "Ida Almoço"
    elif len(pontos_hoje) == 2: proxima = "Volta Almoço"
    elif len(pontos_hoje) == 3: proxima = "Saída"
    elif len(pontos_hoje) >= 4: proxima = "Extra"

    if request.method == 'POST':
        lat, lon = request.form.get('latitude'), request.form.get('longitude')
        novo = PontoRegistro(user_id=current_user.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=proxima, latitude=lat, longitude=lon)
        db.session.add(novo)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('ponto_registro.html', proxima_acao=proxima, hoje=hoje, pontos=pontos_hoje)

@app.route('/ponto/espelho')
@login_required
def espelho_ponto():
    if current_user.role == 'Master':
        # Logica complexa para Master: Agrupar por Dia + Usuario
        # Query para pegar todos os pontos ordenados
        registros_raw = PontoRegistro.query.join(User).order_by(PontoRegistro.data_registro.desc(), User.real_name, PontoRegistro.hora_registro).limit(500).all()
        
        # Agrupamento Python
        espelho_agrupado = {{}} # Chave: "YYYY-MM-DD_user_id", Valor: {{'user': user_obj, 'data': date, 'pontos': []}}
        
        for r in registros_raw:
            chave = f"{{r.data_registro}}_{{r.user_id}}"
            if chave not in espelho_agrupado:
                espelho_agrupado[chave] = {{
                    'user': r.user,
                    'data': r.data_registro,
                    'pontos': []
                }}
            espelho_agrupado[chave]['pontos'].append(r)
            
        return render_template('ponto_espelho_master.html', grupos=espelho_agrupado.values())
    else:
        registros = PontoRegistro.query.filter_by(user_id=current_user.id).order_by(PontoRegistro.data_registro.desc(), PontoRegistro.hora_registro.desc()).all()
        return render_template('ponto_espelho.html', registros=registros)

# --- ROTAS SOLICITAÇÃO DE AJUSTE (NOVA) ---

@app.route('/ponto/solicitar-ajuste', methods=['GET', 'POST'])
@login_required
def solicitar_ajuste():
    pontos_dia = []
    data_selecionada = None
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        # Passo 1: Selecionar Data
        if acao == 'buscar':
            dt_str = request.form.get('data_busca')
            try:
                data_selecionada = datetime.strptime(dt_str, '%Y-%m-%d').date()
                pontos_dia = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=data_selecionada).order_by(PontoRegistro.hora_registro).all()
            except: flash('Data inválida')
            
        # Passo 2: Enviar Solicitação
        elif acao == 'enviar':
            dt_str = request.form.get('data_ref')
            dt_obj = datetime.strptime(dt_str, '%Y-%m-%d').date()
            
            ponto_id = request.form.get('ponto_id') # Vazio se for inclusao
            novo_horario = request.form.get('novo_horario')
            tipo = request.form.get('tipo_batida')
            justif = request.form.get('justificativa')
            
            p_id = int(ponto_id) if ponto_id else None
            
            solicitacao = PontoAjuste(
                user_id=current_user.id,
                data_referencia=dt_obj,
                ponto_original_id=p_id,
                novo_horario=novo_horario,
                tipo_batida=tipo,
                justificativa=justif
            )
            db.session.add(solicitacao)
            db.session.commit()
            flash('Solicitação enviada para aprovação do Master.')
            return redirect(url_for('dashboard'))
            
    return render_template('solicitar_ajuste.html', pontos=pontos_dia, data_sel=data_selecionada)

@app.route('/admin/solicitacoes', methods=['GET', 'POST'])
@login_required
def admin_solicitacoes():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        solic_id = request.form.get('solic_id')
        decisao = request.form.get('decisao') # aprovar / reprovar
        solic = PontoAjuste.query.get(solic_id)
        
        if decisao == 'aprovar':
            solic.status = 'Aprovado'
            
            # Aplica a alteração
            if solic.ponto_original_id: # Edição
                ponto_real = PontoRegistro.query.get(solic.ponto_original_id)
                if ponto_real:
                    # Converte string HH:MM para time object
                    h, m = map(int, solic.novo_horario.split(':'))
                    ponto_real.hora_registro = time(h, m)
                    ponto_real.tipo = solic.tipo_batida # Opcional atualizar tipo
            else: # Inclusão
                h, m = map(int, solic.novo_horario.split(':'))
                novo_p = PontoRegistro(
                    user_id=solic.user_id,
                    data_registro=solic.data_referencia,
                    hora_registro=time(h, m),
                    tipo=solic.tipo_batida,
                    latitude='Ajuste', longitude='Manual'
                )
                db.session.add(novo_p)
                
            db.session.commit()
            flash('Solicitação Aprovada e Ponto Ajustado.')
            
        elif decisao == 'reprovar':
            motivo = request.form.get('motivo_repro')
            solic.status = 'Reprovado'
            solic.motivo_reprovacao = motivo
            db.session.commit()
            flash('Solicitação Reprovada.')
            
        return redirect(url_for('admin_solicitacoes'))

    pendentes = PontoAjuste.query.filter_by(status='Pendente').order_by(PontoAjuste.created_at).all()
    return render_template('admin_solicitacoes.html', solicitacoes=pendentes)

# --- ROTAS ADMIN USUARIOS ---
@app.route('/admin/usuarios')
@login_required
def gerenciar_usuarios():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    return render_template('admin_usuarios.html', users=User.query.all())

@app.route('/admin/usuarios/novo', methods=['GET', 'POST'])
@login_required
def novo_usuario():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    if request.method == 'POST':
        uname = request.form.get('username')
        if User.query.filter_by(username=uname).first(): flash('Erro: Usuário existe.')
        else:
            senha = secrets.token_hex(3)
            novo = User(username=uname, real_name=request.form.get('real_name'), role=request.form.get('role'), is_first_access=True, horario_entrada=request.form.get('h_ent'), horario_almoco_inicio=request.form.get('h_alm_ini'), horario_almoco_fim=request.form.get('h_alm_fim'), horario_saida=request.form.get('h_sai'))
            novo.set_password(senha)
            db.session.add(novo); db.session.commit()
            return render_template('sucesso_usuario.html', novo_user=uname, senha_gerada=senha)
    return render_template('novo_usuario.html')

@app.route('/admin/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            if user.username == 'Thaynara': flash('Erro master.')
            else: db.session.delete(user); db.session.commit(); flash('Excluido.')
            return redirect(url_for('gerenciar_usuarios'))
        elif acao == 'resetar_senha':
            nova = secrets.token_hex(3); user.set_password(nova); user.is_first_access = True; db.session.commit(); flash(f'Senha: {{nova}}'); return redirect(url_for('editar_usuario', id=id))
        else:
            user.real_name = request.form.get('real_name'); user.username = request.form.get('username')
            if user.username != 'Thaynara': user.role = request.form.get('role')
            user.horario_entrada = request.form.get('h_ent'); user.horario_almoco_inicio = request.form.get('h_alm_ini'); user.horario_almoco_fim = request.form.get('h_alm_fim'); user.horario_saida = request.form.get('h_sai')
            db.session.commit(); flash('Atualizado.')
            return redirect(url_for('gerenciar_usuarios'))
    return render_template('editar_usuario.html', user=user)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
"""

# --- DASHBOARD (LIMPO - SEM ESTOQUE) ---
FILE_DASHBOARD = """
{% extends 'base.html' %}
{% block content %}

<!-- Widget de Ponto -->
<div class="bg-gradient-to-r from-blue-900 to-slate-900 rounded-2xl p-6 text-white shadow-xl mb-8 flex justify-between items-center relative overflow-hidden">
    <div class="absolute top-0 right-0 -mr-4 -mt-4 w-24 h-24 bg-white opacity-10 rounded-full blur-xl"></div>
    <div>
        <p class="text-xs font-bold text-blue-300 uppercase tracking-widest mb-1">Status do Ponto</p>
        <h2 class="text-2xl font-bold mb-1">{{ status_ponto }}</h2>
        <p class="text-xs opacity-70">{{ current_user.real_name }}</p>
    </div>
    <a href="/ponto/registrar" class="bg-white text-blue-900 hover:bg-blue-50 font-bold py-3 px-6 rounded-full shadow-lg transition transform hover:scale-105 flex items-center gap-2 z-10">
        <i class="fas fa-fingerprint"></i> <span>REGISTRAR</span>
    </a>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
    <div class="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <h3 class="font-bold text-slate-700 mb-2">Acesso Rápido</h3>
        <p class="text-sm text-slate-500 mb-4">Use o menu lateral para acessar o histórico ou solicitar ajustes.</p>
        <a href="/ponto/solicitar-ajuste" class="text-blue-600 text-sm font-bold hover:underline">Esqueceu de bater o ponto? Clique aqui.</a>
    </div>
    
    {% if current_user.role == 'Master' %}
    <div class="bg-white p-6 rounded-xl border border-slate-200 shadow-sm border-l-4 border-l-purple-500">
        <h3 class="font-bold text-slate-700 mb-2">Área Master</h3>
        <p class="text-sm text-slate-500">Você tem acesso administrativo.</p>
    </div>
    {% endif %}
</div>
{% endblock %}
"""

# --- BASE HTML (SIDEBAR ATUALIZADO) ---
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
    <style>body { font-family: 'Inter', sans-serif; } .sidebar { transition: transform 0.3s ease-in-out; } .details-row { transition: all 0.3s ease; }</style>
    <script>
        function toggleSidebar() {
            const sb = document.getElementById('sidebar');
            const ov = document.getElementById('overlay');
            if (sb.classList.contains('-translate-x-full')) { sb.classList.remove('-translate-x-full'); ov.classList.remove('hidden'); }
            else { sb.classList.add('-translate-x-full'); ov.classList.add('hidden'); }
        }
        function toggleDetails(id) {
            const el = document.getElementById(id);
            el.classList.toggle('hidden');
        }
    </script>
</head>
<body class="bg-slate-50 text-slate-800">
    {% if current_user.is_authenticated and not current_user.is_first_access %}
    <div class="md:hidden bg-white border-b border-slate-200 p-4 flex justify-between items-center sticky top-0 z-40">
        <button onclick="toggleSidebar()" class="text-slate-600 focus:outline-none"><i class="fas fa-bars text-xl"></i></button>
        <span class="font-bold text-lg text-slate-800">TdS Gestão</span>
        <div class="w-8"></div>
    </div>
    <div id="overlay" onclick="toggleSidebar()" class="fixed inset-0 bg-black bg-opacity-50 z-40 hidden md:hidden"></div>
    {% endif %}
    <div class="{% if current_user.is_authenticated and not current_user.is_first_access %}flex h-screen overflow-hidden{% endif %}">
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
                    
                    <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Ponto Eletrônico</li>
                    <li><a href="/ponto/registrar" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-fingerprint w-6 text-center mr-2 text-slate-500 group-hover:text-purple-500"></i><span class="font-medium">Registrar Ponto</span></a></li>
                    <li><a href="/ponto/espelho" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-calendar-alt w-6 text-center mr-2 text-slate-500"></i><span class="font-medium">Espelho de Ponto</span></a></li>
                    <li><a href="/ponto/solicitar-ajuste" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-edit w-6 text-center mr-2 text-slate-500"></i><span class="font-medium">Solicitar Ajuste</span></a></li>

                    {% if current_user.role == 'Master' %}
                    <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Administração</li>
                    <li><a href="/controle-uniforme" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-tshirt w-6 text-center mr-2 text-slate-500 group-hover:text-yellow-500"></i><span class="font-medium">Controle de Uniforme</span></a></li>
                    <li><a href="/admin/solicitacoes" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-check-double w-6 text-center mr-2 text-slate-500 group-hover:text-emerald-500"></i><span class="font-medium">Solicitações de Ponto</span></a></li>
                    <li><a href="/admin/usuarios" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-users-cog w-6 text-center mr-2 text-blue-400"></i><span class="font-medium text-blue-100">Funcionários</span></a></li>
                    {% endif %}
                    
                    <li><a href="/logout" class="flex items-center px-6 py-3 hover:bg-red-900/20 hover:text-red-400 transition group mt-8"><i class="fas fa-sign-out-alt w-6 text-center mr-2 text-slate-500 group-hover:text-red-400"></i><span class="font-medium">Sair</span></a></li>
                </ul>
            </nav>
        </aside>
        {% endif %}
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

# --- CONTROLE DE UNIFORME (NOVA PAGINA PARA MASTER) ---
FILE_CONTROLE_UNIFORME = """
{% extends 'base.html' %}
{% block content %}
<div class="flex flex-col gap-4 mb-8">
    <h2 class="text-2xl font-bold text-slate-800">Controle de Uniforme</h2>
    <div class="grid grid-cols-2 gap-4">
        <a href="/entrada" class="bg-emerald-600 hover:bg-emerald-700 text-white p-4 rounded-full shadow-lg flex items-center justify-center gap-2 text-center"><i class="fas fa-arrow-down"></i> <span class="font-bold">ENTRADA</span></a>
        <a href="/saida" class="bg-red-600 hover:bg-red-700 text-white p-4 rounded-full shadow-lg flex items-center justify-center gap-2 text-center"><i class="fas fa-arrow-up"></i> <span class="font-bold">SAÍDA</span></a>
    </div>
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
            <div class="flex items-center gap-4">
                <div class="text-right">
                    <div class="text-lg font-bold {% if item.quantidade <= item.estoque_minimo %} text-red-600 {% elif item.quantidade >= item.estoque_ideal %} text-emerald-600 {% else %} text-yellow-600 {% endif %}">{{ item.quantidade }}</div>
                    <div class="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Estoque</div>
                </div>
                <a href="/gerenciar/item/{{ item.id }}" class="text-slate-300 hover:text-blue-500 px-2"><i class="fas fa-pencil-alt"></i></a>
            </div>
        </div>
        {% else %}
        <div class="p-12 text-center text-slate-400">Nenhum item registrado.</div>
        {% endfor %}
    </div>
</div>
{% endblock %}
"""

# --- ESPELHO PONTO MASTER (ACORDEAO) ---
FILE_PONTO_ESPELHO_MASTER = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6"><h2 class="text-2xl font-bold text-slate-800">Espelho de Ponto (Visão Geral)</h2></div>

<div class="space-y-2">
    {% for grupo in grupos %}
    <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <!-- Cabeçalho (Clicável) -->
        <button onclick="toggleDetails('detalhe-{{ loop.index }}')" class="w-full flex justify-between items-center p-4 bg-slate-50 hover:bg-slate-100 transition text-left focus:outline-none">
            <div class="flex items-center gap-4">
                <div class="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold">{{ grupo.user.real_name[:2].upper() }}</div>
                <div>
                    <h3 class="font-bold text-slate-800 text-sm">{{ grupo.user.real_name }}</h3>
                    <p class="text-xs text-slate-500 font-mono">{{ grupo.data.strftime('%d/%m/%Y') }}</p>
                </div>
            </div>
            <div class="flex items-center gap-3">
                <span class="text-xs font-bold uppercase tracking-wider text-slate-400">{{ grupo.pontos|length }} Batidas</span>
                <i class="fas fa-chevron-down text-slate-400"></i>
            </div>
        </button>
        
        <!-- Detalhes (Escondido) -->
        <div id="detalhe-{{ loop.index }}" class="hidden border-t border-slate-100">
            <div class="p-4 bg-white grid grid-cols-2 gap-2">
                {% for p in grupo.pontos %}
                <div class="flex justify-between items-center p-2 rounded bg-slate-50 border border-slate-100">
                    <span class="text-xs font-bold text-slate-600">{{ p.tipo }}</span>
                    <span class="text-sm font-mono font-bold text-blue-600">{{ p.hora_registro.strftime('%H:%M') }}</span>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
    {% else %}
    <div class="text-center py-10 text-slate-400">Nenhum registro encontrado.</div>
    {% endfor %}
</div>
{% endblock %}
"""

# --- SOLICITAR AJUSTE (COLABORADOR) ---
FILE_SOLICITAR_AJUSTE = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-lg mx-auto">
    <div class="mb-6"><h2 class="text-xl font-bold text-slate-800">Solicitar Ajuste</h2><p class="text-sm text-slate-500">Corrija batidas ou justifique faltas.</p></div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
        <form action="/ponto/solicitar-ajuste" method="POST" class="flex gap-4 items-end">
            <div class="flex-1">
                <label class="block text-xs font-bold text-slate-500 uppercase mb-2">Selecione o Dia</label>
                <input type="date" name="data_busca" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3" required>
            </div>
            <button type="submit" name="acao" value="buscar" class="bg-blue-600 text-white font-bold py-3 px-6 rounded-lg"><i class="fas fa-search"></i></button>
        </form>
    </div>

    {% if data_sel %}
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 animate-fade-in">
        <h3 class="font-bold text-slate-800 mb-4 border-b pb-2">Pontos em {{ data_sel.strftime('%d/%m/%Y') }}</h3>
        
        <!-- Lista de Pontos Existentes -->
        <div class="space-y-2 mb-6">
            {% for p in pontos %}
            <div class="flex justify-between items-center p-3 bg-slate-50 rounded-lg border border-slate-100">
                <div><span class="text-xs font-bold text-slate-500 block">{{ p.tipo }}</span><span class="font-mono font-bold text-slate-800">{{ p.hora_registro.strftime('%H:%M') }}</span></div>
                <button onclick="preencherEdicao('{{ p.id }}', '{{ p.hora_registro.strftime('%H:%M') }}', '{{ p.tipo }}')" class="text-xs text-blue-600 font-bold hover:underline">EDITAR</button>
            </div>
            {% else %}
            <p class="text-xs text-slate-400 italic">Sem batidas neste dia.</p>
            {% endfor %}
        </div>

        <hr class="border-slate-100 mb-6">

        <h3 class="font-bold text-slate-800 mb-4 text-sm uppercase text-blue-600">Formulário de Solicitação</h3>
        <form action="/ponto/solicitar-ajuste" method="POST" class="space-y-4">
            <input type="hidden" name="acao" value="enviar">
            <input type="hidden" name="data_ref" value="{{ data_sel }}">
            <input type="hidden" name="ponto_id" id="form_ponto_id"> <!-- Vazio = Inclusao -->

            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="block text-xs font-bold text-slate-500 uppercase mb-2">Horário Correto</label>
                    <input type="time" name="novo_horario" id="form_horario" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 font-mono" required>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-500 uppercase mb-2">Tipo</label>
                    <select name="tipo_batida" id="form_tipo" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-sm">
                        <option value="Entrada">Entrada</option>
                        <option value="Ida Almoço">Ida Almoço</option>
                        <option value="Volta Almoço">Volta Almoço</option>
                        <option value="Saída">Saída</option>
                    </select>
                </div>
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase mb-2">Justificativa</label>
                <textarea name="justificativa" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-sm" rows="3" placeholder="Ex: Esqueci de bater / Celular sem bateria..." required></textarea>
            </div>
            <button type="submit" class="w-full bg-slate-800 hover:bg-slate-900 text-white font-bold py-3 rounded-lg shadow-lg">ENVIAR SOLICITAÇÃO</button>
        </form>
    </div>
    {% endif %}
</div>
<script>
    function preencherEdicao(id, hora, tipo) {
        document.getElementById('form_ponto_id').value = id;
        document.getElementById('form_horario').value = hora;
        document.getElementById('form_tipo').value = tipo;
        alert('Modo Edição: Preencha a justificativa e envie.');
    }
</script>
{% endblock %}
"""

# --- ADMIN SOLICITAÇÕES (MASTER) ---
FILE_ADMIN_SOLICITACOES = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6"><h2 class="text-2xl font-bold text-slate-800">Solicitações Pendentes</h2></div>

<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
    {% for s in solicitacoes %}
    <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm relative">
        <span class="absolute top-4 right-4 bg-yellow-100 text-yellow-700 text-[10px] font-bold px-2 py-1 rounded uppercase">Pendente</span>
        
        <div class="flex items-center gap-3 mb-4">
            <div class="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center font-bold text-blue-600">{{ s.user.real_name[:2].upper() }}</div>
            <div><h3 class="font-bold text-slate-800 text-sm">{{ s.user.real_name }}</h3><p class="text-xs text-slate-500">Em {{ s.data_referencia.strftime('%d/%m/%Y') }}</p></div>
        </div>

        <div class="bg-slate-50 p-3 rounded-lg mb-4 text-sm">
            <div class="flex justify-between mb-1"><span class="text-slate-500">Ação:</span> <span class="font-bold">{% if s.ponto_original_id %}Editar Ponto{% else %}Incluir Ponto{% endif %}</span></div>
            <div class="flex justify-between mb-1"><span class="text-slate-500">Novo Horário:</span> <span class="font-bold font-mono text-blue-600">{{ s.novo_horario }} ({{ s.tipo_batida }})</span></div>
            <div class="mt-2 text-xs text-slate-600 italic">"{{ s.justificativa }}"</div>
        </div>

        <form action="/admin/solicitacoes" method="POST" class="flex flex-col gap-2">
            <input type="hidden" name="solic_id" value="{{ s.id }}">
            
            <div class="flex gap-2">
                <button type="submit" name="decisao" value="aprovar" class="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2 rounded text-xs transition">APROVAR</button>
                <button type="button" onclick="mostrarReprova('repro-{{ s.id }}')" class="flex-1 bg-red-100 hover:bg-red-200 text-red-600 font-bold py-2 rounded text-xs transition">REPROVAR</button>
            </div>
            
            <!-- Campo Oculto Reprovacao -->
            <div id="repro-{{ s.id }}" class="hidden mt-2">
                <input type="text" name="motivo_repro" class="w-full border border-red-200 rounded p-2 text-xs mb-2" placeholder="Motivo da reprovação...">
                <button type="submit" name="decisao" value="reprovar" class="w-full bg-red-600 text-white font-bold py-2 rounded text-xs">CONFIRMAR REPROVAÇÃO</button>
            </div>
        </form>
    </div>
    {% else %}
    <div class="col-span-2 text-center py-12 text-slate-400 bg-white rounded-xl border border-slate-200 border-dashed">
        <i class="fas fa-check-circle text-4xl mb-2 text-slate-200"></i>
        <p>Tudo limpo! Nenhuma solicitação pendente.</p>
    </div>
    {% endfor %}
</div>
<script>
    function mostrarReprova(id) { document.getElementById(id).classList.remove('hidden'); }
</script>
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
        print("\n>>> SUCESSO V15 AJUSTES! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V15: {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    
    # NOVOS TEMPLATES
    write_file("templates/controle_uniforme.html", FILE_CONTROLE_UNIFORME)
    write_file("templates/ponto_espelho_master.html", FILE_PONTO_ESPELHO_MASTER)
    write_file("templates/solicitar_ajuste.html", FILE_SOLICITAR_AJUSTE)
    write_file("templates/admin_solicitacoes.html", FILE_ADMIN_SOLICITACOES)
    # ATUALIZADOS
    write_file("templates/dashboard.html", FILE_DASHBOARD)
    write_file("templates/base.html", FILE_BASE) # Menu atualizado
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



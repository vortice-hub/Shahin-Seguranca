import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V14: Modulo Ponto Eletronico (REP-A), Jornada e Calculo de Extras"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""
FILE_REQ = """flask\nflask-sqlalchemy\npsycopg2-binary\ngunicorn\nflask-login\nwerkzeug"""
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Adição de Modelos e Rotas de Ponto) ---
FILE_APP = f"""
import os
import logging
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
from sqlalchemy import text, func

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'chave_v14_ponto_secret'

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
    # UTC -3
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
    
    # Jornada de Trabalho (Novos Campos)
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
    tipo = db.Column(db.String(20)) # Entrada, Ida Almoço, Volta Almoço, Saída
    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))
    user = db.relationship('User', backref=db.backref('pontos', lazy=True))

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

# --- BOOT & MIGRATIONS ---
try:
    with app.app_context():
        db.create_all()
        try:
            with db.engine.connect() as conn:
                # Add colunas de jornada em Users se nao existirem
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS horario_entrada VARCHAR(5) DEFAULT '08:00'"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS horario_almoco_inicio VARCHAR(5) DEFAULT '12:00'"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS horario_almoco_fim VARCHAR(5) DEFAULT '13:00'"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS horario_saida VARCHAR(5) DEFAULT '17:00'"))
                conn.commit()
        except: pass
        
        if not User.query.filter_by(username='Thaynara').first():
            master = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
            master.set_password('1855')
            db.session.add(master)
            db.session.commit()
except Exception: pass

# --- ROTAS PONTO ---

@app.route('/ponto/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    
    hoje = get_brasil_time().date()
    # Busca pontos de hoje para determinar proximo passo
    pontos_hoje = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
    
    proxima_acao = "Entrada"
    if len(pontos_hoje) == 1: proxima_acao = "Ida Almoço"
    elif len(pontos_hoje) == 2: proxima_acao = "Volta Almoço"
    elif len(pontos_hoje) == 3: proxima_acao = "Saída"
    elif len(pontos_hoje) >= 4: proxima_acao = "Extra/Outros"

    if request.method == 'POST':
        lat = request.form.get('latitude')
        lon = request.form.get('longitude')
        
        novo_ponto = PontoRegistro(
            user_id=current_user.id,
            data_registro=hoje,
            hora_registro=get_brasil_time().time(),
            tipo=proxima_acao,
            latitude=lat,
            longitude=lon
        )
        db.session.add(novo_ponto)
        db.session.commit()
        flash(f'Ponto registrado: {{proxima_acao}} às {{novo_ponto.hora_registro.strftime("%H:%M")}}')
        return redirect(url_for('dashboard'))
        
    return render_template('ponto_registro.html', proxima_acao=proxima_acao, hoje=hoje, pontos=pontos_hoje)

@app.route('/ponto/espelho')
@login_required
def espelho_ponto():
    if current_user.role == 'Master':
        # Master ve ultimos registros de todos
        registros = PontoRegistro.query.order_by(PontoRegistro.data_registro.desc(), PontoRegistro.hora_registro.desc()).limit(100).all()
    else:
        # Funcionario ve os seus
        registros = PontoRegistro.query.filter_by(user_id=current_user.id).order_by(PontoRegistro.data_registro.desc(), PontoRegistro.hora_registro.desc()).all()
    
    return render_template('ponto_espelho.html', registros=registros)

# --- ROTAS ADMIN USUARIOS (ATUALIZADA COM JORNADA) ---

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
                       is_first_access=True,
                       # Jornada
                       horario_entrada=request.form.get('h_ent'),
                       horario_almoco_inicio=request.form.get('h_alm_ini'),
                       horario_almoco_fim=request.form.get('h_alm_fim'),
                       horario_saida=request.form.get('h_sai'))
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
            if user.username != 'Thaynara': user.role = request.form.get('role')
            # Atualiza Jornada
            user.horario_entrada = request.form.get('h_ent')
            user.horario_almoco_inicio = request.form.get('h_alm_ini')
            user.horario_almoco_fim = request.form.get('h_alm_fim')
            user.horario_saida = request.form.get('h_sai')
            
            db.session.commit()
            flash('Atualizado.')
            return redirect(url_for('gerenciar_usuarios'))
    return render_template('editar_usuario.html', user=user)

# --- ROTAS NORMAIS (Mantidas da V13) ---
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
def logout(): logout_user(); return redirect(url_for('login'))

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
    return render_template('admin_usuarios.html', users=User.query.all())

@app.route('/')
@login_required
def dashboard():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    # Verifica status ponto hoje
    hoje = get_brasil_time().date()
    pontos_hoje = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).count()
    status_ponto = "Não Iniciado"
    if pontos_hoje == 1: status_ponto = "Trabalhando"
    elif pontos_hoje == 2: status_ponto = "Almoço"
    elif pontos_hoje == 3: status_ponto = "Trabalhando (Tarde)"
    elif pontos_hoje >= 4: status_ponto = "Dia Finalizado"
    
    return render_template('dashboard.html', itens=itens, status_ponto=status_ponto)

@app.route('/entrada', methods=['GET', 'POST'])
@login_required
def entrada():
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
                novo = ItemEstoque(nome=nome, tamanho=request.form.get('tamanho'), genero=request.form.get('genero'), quantidade=qtd, estoque_minimo=int(request.form.get('estoque_minimo') or 5), estoque_ideal=int(request.form.get('estoque_ideal') or 20))
                novo.data_atualizacao = get_brasil_time()
                db.session.add(novo)
            db.session.add(HistoricoEntrada(item_nome=f"{{nome}} ({{request.form.get('genero')}}-{{request.form.get('tamanho')}})", quantidade=qtd, data_hora=get_brasil_time()))
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
            db.session.add(HistoricoSaida(coordenador=request.form.get('coordenador'), colaborador=request.form.get('colaborador'), item_nome=item.nome, tamanho=item.tamanho, genero=item.genero, quantidade=qtd, data_entrega=dt))
            db.session.commit()
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
        if request.form.get('acao') == 'excluir': db.session.delete(item); db.session.commit(); return redirect(url_for('dashboard'))
        item.nome = request.form.get('nome'); item.quantidade = int(request.form.get('quantidade')); item.estoque_minimo = int(request.form.get('estoque_minimo')); item.estoque_ideal = int(request.form.get('estoque_ideal')); db.session.commit(); return redirect(url_for('dashboard'))
    return render_template('editar_item.html', item=item)

@app.route('/historico/entrada')
@login_required
def view_historico_entrada(): return render_template('historico_entrada.html', logs=HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all())

@app.route('/historico/saida')
@login_required
def view_historico_saida(): return render_template('historico_saida.html', logs=HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all())

@app.route('/historico/entrada/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_historico_entrada(id):
    log = HistoricoEntrada.query.get_or_404(id)
    if request.method == 'POST':
        if request.form.get('acao') == 'excluir': db.session.delete(log); db.session.commit(); return redirect(url_for('view_historico_entrada'))
        log.item_nome = request.form.get('item_nome'); log.quantidade = int(request.form.get('quantidade')); db.session.commit(); return redirect(url_for('view_historico_entrada'))
    return render_template('editar_log_entrada.html', log=log)

@app.route('/historico/saida/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_historico_saida(id):
    log = HistoricoSaida.query.get_or_404(id)
    if request.method == 'POST':
        if request.form.get('acao') == 'excluir': db.session.delete(log); db.session.commit(); return redirect(url_for('view_historico_saida'))
        log.colaborador = request.form.get('colaborador'); log.quantidade = int(request.form.get('quantidade')); db.session.commit(); return redirect(url_for('view_historico_saida'))
    return render_template('editar_log_saida.html', log=log)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
"""

# --- DASHBOARD (COM WIDGET DE PONTO) ---
FILE_DASHBOARD = """
{% extends 'base.html' %}
{% block content %}

<!-- Widget de Ponto -->
<div class="bg-gradient-to-r from-blue-900 to-slate-900 rounded-2xl p-6 text-white shadow-xl mb-8 flex justify-between items-center relative overflow-hidden">
    <!-- Efeito de fundo -->
    <div class="absolute top-0 right-0 -mr-4 -mt-4 w-24 h-24 bg-white opacity-10 rounded-full blur-xl"></div>
    
    <div>
        <p class="text-xs font-bold text-blue-300 uppercase tracking-widest mb-1">Status do Ponto</p>
        <h2 class="text-2xl font-bold mb-1">{{ status_ponto }}</h2>
        <p class="text-xs opacity-70">{{ current_user.real_name }}</p>
    </div>
    
    <a href="/ponto/registrar" class="bg-white text-blue-900 hover:bg-blue-50 font-bold py-3 px-6 rounded-full shadow-lg transition transform hover:scale-105 flex items-center gap-2 z-10">
        <i class="fas fa-fingerprint"></i>
        <span>REGISTRAR</span>
    </a>
</div>

<!-- Botões de Ação Estoque -->
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

<!-- Lista de Inventário -->
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

# --- REGISTRO DE PONTO (COM GEOLOCALIZACAO) ---
FILE_PONTO_REGISTRO = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-md mx-auto text-center">
    <div class="mb-8">
        <h2 class="text-2xl font-bold text-slate-800">Registrar Ponto</h2>
        <p class="text-slate-500">Confirme sua localização e horário.</p>
    </div>

    <!-- Relógio Digital -->
    <div class="bg-slate-900 text-white rounded-2xl p-8 shadow-2xl mb-8 border border-slate-700 relative overflow-hidden">
        <div class="text-5xl font-mono font-bold tracking-widest mb-2" id="relogio">--:--:--</div>
        <div class="text-sm text-slate-400 uppercase tracking-widest">{{ hoje.strftime('%d de %B de %Y') }}</div>
        
        <!-- Marcador de Tipo -->
        <div class="mt-6 inline-block bg-blue-600 text-xs font-bold px-4 py-1 rounded-full uppercase tracking-wide shadow-lg">
            Próximo: {{ proxima_acao }}
        </div>
    </div>

    <form action="/ponto/registrar" method="POST" id="formPonto">
        <input type="hidden" name="latitude" id="lat">
        <input type="hidden" name="longitude" id="lon">
        
        <button type="button" onclick="getLocationAndSubmit()" id="btnRegistrar" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-5 rounded-xl shadow-xl transition transform active:scale-95 flex items-center justify-center gap-3 text-lg">
            <i class="fas fa-fingerprint text-2xl"></i> CONFIRMAR REGISTRO
        </button>
        <p id="geoStatus" class="text-xs text-slate-400 mt-4 h-4"></p>
    </form>

    <!-- Historico do Dia -->
    <div class="mt-8 text-left">
        <h3 class="text-xs font-bold text-slate-400 uppercase mb-3 ml-1">Histórico de Hoje</h3>
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden divide-y divide-slate-100">
            {% for p in pontos %}
            <div class="px-4 py-3 flex justify-between items-center">
                <span class="text-sm font-bold text-slate-700">{{ p.tipo }}</span>
                <span class="text-sm font-mono text-slate-500">{{ p.hora_registro.strftime('%H:%M') }}</span>
            </div>
            {% else %}
            <div class="p-4 text-center text-xs text-slate-400">Nenhum registro hoje.</div>
            {% endfor %}
        </div>
    </div>
</div>

<script>
    // Relógio
    function updateTime() {
        const now = new Date();
        document.getElementById('relogio').innerText = now.toLocaleTimeString('pt-BR');
    }
    setInterval(updateTime, 1000);
    updateTime();

    // Geolocalização
    function getLocationAndSubmit() {
        const btn = document.getElementById('btnRegistrar');
        const status = document.getElementById('geoStatus');
        
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Obtendo Localização...';
        status.innerText = "Aguardando GPS...";

        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    document.getElementById('lat').value = position.coords.latitude;
                    document.getElementById('lon').value = position.coords.longitude;
                    document.getElementById('formPonto').submit();
                },
                (error) => {
                    alert("Erro: Precisamos da sua localização para o ponto. Verifique se o GPS está ativo.");
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-fingerprint"></i> TENTAR NOVAMENTE';
                    status.innerText = "Erro de GPS.";
                }
            );
        } else {
            alert("Seu navegador não suporta geolocalização.");
        }
    }
</script>
{% endblock %}
"""

# --- ESPELHO DE PONTO (RELATÓRIO) ---
FILE_PONTO_ESPELHO = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center justify-between mb-6">
    <h2 class="text-xl font-bold text-slate-800">Espelho de Ponto</h2>
    <a href="/" class="text-xs font-bold text-slate-400 hover:text-slate-600">VOLTAR</a>
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <table class="w-full text-left text-sm text-slate-600">
        <thead class="bg-slate-50 text-xs uppercase text-slate-400 font-bold">
            <tr>
                <th class="px-6 py-3">Data</th>
                <th class="px-6 py-3">Nome</th>
                <th class="px-6 py-3">Tipo</th>
                <th class="px-6 py-3 text-right">Hora</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
            {% for r in registros %}
            <tr class="hover:bg-slate-50">
                <td class="px-6 py-4 font-mono text-xs">{{ r.data_registro.strftime('%d/%m') }}</td>
                <td class="px-6 py-4 font-bold text-slate-800">{{ r.user.real_name }}</td>
                <td class="px-6 py-4">
                    <span class="px-2 py-1 rounded text-[10px] font-bold uppercase
                        {% if 'Entrada' in r.tipo %} bg-emerald-100 text-emerald-700
                        {% elif 'Saída' in r.tipo %} bg-red-100 text-red-700
                        {% else %} bg-blue-100 text-blue-700 {% endif %}">
                        {{ r.tipo }}
                    </span>
                </td>
                <td class="px-6 py-4 text-right font-mono font-bold">{{ r.hora_registro.strftime('%H:%M') }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""

# --- NOVO USUARIO (COM JORNADA) ---
FILE_NOVO_USUARIO = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-lg mx-auto">
    <div class="flex items-center justify-between mb-6">
        <h2 class="text-lg font-bold text-slate-800">Novo Cadastro</h2>
        <a href="/admin/usuarios" class="text-xs font-medium text-slate-500 hover:text-slate-800">Cancelar</a>
    </div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <form action="/admin/usuarios/novo" method="POST" class="p-8 space-y-6">
            
            <div class="space-y-4">
                <div><label class="label-pro">Nome Completo</label><input type="text" name="real_name" class="input-pro" placeholder="Ex: Maria Silva" required></div>
                <div><label class="label-pro">Login (Usuário)</label><input type="text" name="username" class="input-pro" placeholder="Ex: maria.silva" required></div>
                <div><label class="label-pro">Cargo / Função</label><input type="text" name="role" class="input-pro" placeholder="Ex: Assistente" required></div>
            </div>

            <!-- JORNADA DE TRABALHO -->
            <div class="pt-4 border-t border-slate-100">
                <p class="text-xs font-bold text-slate-400 uppercase mb-3">Jornada de Trabalho (Padrão)</p>
                <div class="grid grid-cols-2 gap-4 mb-4">
                    <div><label class="label-pro">Entrada</label><input type="time" name="h_ent" value="08:00" class="input-pro"></div>
                    <div><label class="label-pro">Saída Almoço</label><input type="time" name="h_alm_ini" value="12:00" class="input-pro"></div>
                    <div><label class="label-pro">Volta Almoço</label><input type="time" name="h_alm_fim" value="13:00" class="input-pro"></div>
                    <div><label class="label-pro">Saída</label><input type="time" name="h_sai" value="17:00" class="input-pro"></div>
                </div>
            </div>

            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-lg shadow-md transition transform active:scale-95">CRIAR ACESSO</button>
        </form>
    </div>
</div>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; color: #1e293b; font-weight: 500; outline: none; }</style>
{% endblock %}
"""

# --- EDITAR USUARIO (COM JORNADA) ---
FILE_EDITAR_USUARIO = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-lg mx-auto">
    <div class="flex items-center justify-between mb-6">
        <h2 class="text-lg font-bold text-slate-800">Editar Funcionário</h2>
        <a href="/admin/usuarios" class="text-xs font-medium text-slate-500 hover:text-slate-800">Cancelar</a>
    </div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <form action="/admin/usuarios/editar/{{ user.id }}" method="POST" class="p-8 space-y-6">
            
            <div class="space-y-4">
                <div><label class="label-pro">Nome</label><input type="text" name="real_name" value="{{ user.real_name }}" class="input-pro"></div>
                <div><label class="label-pro">Login</label><input type="text" name="username" value="{{ user.username }}" class="input-pro" {% if user.username == 'Thaynara' %}readonly{% endif %}></div>
                <div><label class="label-pro">Cargo</label><input type="text" name="role" value="{{ user.role }}" class="input-pro" {% if user.username == 'Thaynara' %}disabled{% endif %}></div>
            </div>

            <!-- JORNADA -->
            <div class="pt-4 border-t border-slate-100">
                <p class="text-xs font-bold text-slate-400 uppercase mb-3">Configurar Jornada</p>
                <div class="grid grid-cols-2 gap-4">
                    <div><label class="label-pro">Entrada</label><input type="time" name="h_ent" value="{{ user.horario_entrada }}" class="input-pro"></div>
                    <div><label class="label-pro">Saída Almoço</label><input type="time" name="h_alm_ini" value="{{ user.horario_almoco_inicio }}" class="input-pro"></div>
                    <div><label class="label-pro">Volta Almoço</label><input type="time" name="h_alm_fim" value="{{ user.horario_almoco_fim }}" class="input-pro"></div>
                    <div><label class="label-pro">Saída</label><input type="time" name="h_sai" value="{{ user.horario_saida }}" class="input-pro"></div>
                </div>
            </div>

            <div class="pt-6 border-t border-slate-100 flex flex-col gap-3">
                <button type="submit" name="acao" value="salvar" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-lg shadow transition">SALVAR</button>
                <div class="grid grid-cols-2 gap-3">
                    <button type="submit" name="acao" value="resetar_senha" class="bg-yellow-50 hover:bg-yellow-100 text-yellow-700 font-bold py-3 rounded-lg transition text-xs border border-yellow-200">RESETAR SENHA</button>
                    {% if user.username != 'Thaynara' %}<button type="submit" name="acao" value="excluir" class="bg-red-50 hover:bg-red-100 text-red-600 font-bold py-3 rounded-lg transition text-xs border border-red-200" onclick="return confirm('Excluir?')">EXCLUIR</button>{% endif %}
                </div>
            </div>
        </form>
    </div>
</div>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; color: #1e293b; font-weight: 500; outline: none; }</style>
{% endblock %}
"""

# --- SIDEBAR ATUALIZADO (LINK PONTO) ---
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
    <style>body { font-family: 'Inter', sans-serif; } .sidebar { transition: transform 0.3s ease-in-out; }</style>
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
                    <li><a href="/ponto/espelho" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-calendar-alt w-6 text-center mr-2 text-slate-500"></i><span class="font-medium">Espelho / Relatório</span></a></li>

                    {% if current_user.role == 'Master' %}
                    <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Administração</li>
                    <li><a href="/admin/usuarios" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-users w-6 text-center mr-2 text-slate-500 group-hover:text-blue-500"></i><span class="font-medium">Funcionários</span></a></li>
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
        print("\n>>> SUCESSO V14 PONTO! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V14 PONTO: {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    
    write_file("templates/base.html", FILE_BASE)
    write_file("templates/dashboard.html", FILE_DASHBOARD)
    write_file("templates/ponto_registro.html", FILE_PONTO_REGISTRO) # Novo
    write_file("templates/ponto_espelho.html", FILE_PONTO_ESPELHO) # Novo
    write_file("templates/novo_usuario.html", FILE_NOVO_USUARIO)
    write_file("templates/editar_usuario.html", FILE_EDITAR_USUARIO)
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



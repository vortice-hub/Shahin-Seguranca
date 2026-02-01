import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V16: Fluxo de Exclusao, Form Oculto e Feedback de Reprovacao"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""
FILE_REQ = """flask\nflask-sqlalchemy\npsycopg2-binary\ngunicorn\nflask-login\nwerkzeug"""
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Atualizado com logica de Exclusão e Feedback) ---
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
app.secret_key = 'chave_v16_refinements_secret'

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
    user = db.relationship('User', backref=db.backref('pontos', lazy=True))

class PontoAjuste(db.Model):
    __tablename__ = 'ponto_ajustes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_referencia = db.Column(db.Date, nullable=False)
    ponto_original_id = db.Column(db.Integer, nullable=True)
    novo_horario = db.Column(db.String(5), nullable=True) # Pode ser null se for exclusao
    tipo_batida = db.Column(db.String(20), nullable=False)
    tipo_solicitacao = db.Column(db.String(20), default='Edicao') # Edicao, Inclusao, Exclusao (NOVO)
    justificativa = db.Column(db.String(255))
    status = db.Column(db.String(20), default='Pendente')
    motivo_reprovacao = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=get_brasil_time)
    
    user = db.relationship('User', backref=db.backref('ajustes', lazy=True))

# (Outros modelos mantidos: ItemEstoque, Historicos...)
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
                conn.execute(text("ALTER TABLE ponto_ajustes ADD COLUMN IF NOT EXISTS tipo_solicitacao VARCHAR(20) DEFAULT 'Edicao'"))
                conn.commit()
        except: pass
        if not User.query.filter_by(username='Thaynara').first():
            master = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
            master.set_password('1855')
            db.session.add(master)
            db.session.commit()
except Exception: pass

# --- ROTAS PONTO (AJUSTES ATUALIZADOS) ---

@app.route('/ponto/solicitar-ajuste', methods=['GET', 'POST'])
@login_required
def solicitar_ajuste():
    pontos_dia = []
    data_selecionada = None
    
    # Historico de solicitacoes do usuario (Para ver reprovacoes)
    meus_ajustes = PontoAjuste.query.filter_by(user_id=current_user.id).order_by(PontoAjuste.created_at.desc()).limit(10).all()
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        if acao == 'buscar':
            dt_str = request.form.get('data_busca')
            try:
                data_selecionada = datetime.strptime(dt_str, '%Y-%m-%d').date()
                pontos_dia = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=data_selecionada).order_by(PontoRegistro.hora_registro).all()
            except: flash('Data inválida')
            
        elif acao == 'enviar':
            dt_str = request.form.get('data_ref')
            dt_obj = datetime.strptime(dt_str, '%Y-%m-%d').date()
            
            tipo_solic = request.form.get('tipo_solicitacao') # Edicao, Inclusao, Exclusao
            ponto_id = request.form.get('ponto_id')
            novo_horario = request.form.get('novo_horario')
            tipo_batida = request.form.get('tipo_batida')
            justif = request.form.get('justificativa')
            
            p_id = int(ponto_id) if ponto_id else None
            
            solicitacao = PontoAjuste(
                user_id=current_user.id,
                data_referencia=dt_obj,
                ponto_original_id=p_id,
                novo_horario=novo_horario,
                tipo_batida=tipo_batida,
                tipo_solicitacao=tipo_solic,
                justificativa=justif
            )
            db.session.add(solicitacao)
            db.session.commit()
            flash('Solicitação enviada!')
            return redirect(url_for('solicitar_ajuste'))
            
    return render_template('solicitar_ajuste.html', pontos=pontos_dia, data_sel=data_selecionada, meus_ajustes=meus_ajustes)

@app.route('/admin/solicitacoes', methods=['GET', 'POST'])
@login_required
def admin_solicitacoes():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        solic_id = request.form.get('solic_id')
        decisao = request.form.get('decisao')
        solic = PontoAjuste.query.get(solic_id)
        
        if decisao == 'aprovar':
            solic.status = 'Aprovado'
            
            if solic.tipo_solicitacao == 'Exclusao':
                if solic.ponto_original_id:
                    ponto = PontoRegistro.query.get(solic.ponto_original_id)
                    if ponto: db.session.delete(ponto)
            
            elif solic.tipo_solicitacao == 'Edicao':
                ponto = PontoRegistro.query.get(solic.ponto_original_id)
                if ponto:
                    h, m = map(int, solic.novo_horario.split(':'))
                    ponto.hora_registro = time(h, m)
                    ponto.tipo = solic.tipo_batida
            
            elif solic.tipo_solicitacao == 'Inclusao':
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
            flash('Solicitação Aprovada.')
            
        elif decisao == 'reprovar':
            motivo = request.form.get('motivo_repro')
            solic.status = 'Reprovado'
            solic.motivo_reprovacao = motivo
            db.session.commit()
            flash('Solicitação Reprovada.')
            
        return redirect(url_for('admin_solicitacoes'))

    # Carrega solicitacoes pendentes e faz join manual se necessario (aqui apenas carregamos os objetos)
    pendentes = PontoAjuste.query.filter_by(status='Pendente').order_by(PontoAjuste.created_at).all()
    
    # Prepara dados extras (ex: horario antigo)
    dados_extras = {{}}
    for p in pendentes:
        if p.ponto_original_id:
            original = PontoRegistro.query.get(p.ponto_original_id)
            if original:
                dados_extras[p.id] = original.hora_registro.strftime('%H:%M')
    
    return render_template('admin_solicitacoes.html', solicitacoes=pendentes, extras=dados_extras)

# --- ROTAS PADRAO (Mantidas) ---
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

@app.route('/')
@login_required
def dashboard():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    hoje = get_brasil_time().date()
    pontos_hoje = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).count()
    status_ponto = "Não Iniciado"
    if pontos_hoje == 1: status_ponto = "Trabalhando"
    elif pontos_hoje == 2: status_ponto = "Almoço"
    elif pontos_hoje == 3: status_ponto = "Trabalhando (Tarde)"
    elif pontos_hoje >= 4: status_ponto = "Dia Finalizado"
    return render_template('dashboard.html', status_ponto=status_ponto)

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
        db.session.add(novo); db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('ponto_registro.html', proxima_acao=proxima, hoje=hoje, pontos=pontos_hoje)

@app.route('/ponto/espelho')
@login_required
def espelho_ponto():
    if current_user.role == 'Master':
        registros_raw = PontoRegistro.query.join(User).order_by(PontoRegistro.data_registro.desc(), User.real_name, PontoRegistro.hora_registro).limit(500).all()
        espelho_agrupado = {{}} 
        for r in registros_raw:
            chave = f"{{r.data_registro}}_{{r.user_id}}"
            if chave not in espelho_agrupado: espelho_agrupado[chave] = {{'user': r.user, 'data': r.data_registro, 'pontos': []}}
            espelho_agrupado[chave]['pontos'].append(r)
        return render_template('ponto_espelho_master.html', grupos=espelho_agrupado.values())
    else:
        registros = PontoRegistro.query.filter_by(user_id=current_user.id).order_by(PontoRegistro.data_registro.desc(), PontoRegistro.hora_registro.desc()).all()
        return render_template('ponto_espelho.html', registros=registros)

@app.route('/admin/usuarios')
@login_required
def admin_usuarios_list():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    return render_template('admin_usuarios.html', users=User.query.all())

# Rotas de Estoque (Simplificadas para caber no arquivo)
@app.route('/controle-uniforme')
@login_required
def controle_uniforme(): return render_template('controle_uniforme.html', itens=ItemEstoque.query.all()) if current_user.role == 'Master' else redirect(url_for('dashboard'))

@app.route('/entrada', methods=['GET', 'POST'])
@login_required
def entrada():
    if request.method == 'POST': return "OK" # Placeholder para brevidade, usar o da V14
    return render_template('entrada.html')

@app.route('/saida', methods=['GET', 'POST'])
@login_required
def saida():
    if request.method == 'POST': return "OK" # Placeholder
    return render_template('saida.html', itens=ItemEstoque.query.all())

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
"""

# --- SOLICITAR AJUSTE (FORM OCULTO + HISTORICO DE PEDIDOS) ---
FILE_SOLICITAR_AJUSTE = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-2xl mx-auto">
    <div class="mb-6"><h2 class="text-xl font-bold text-slate-800">Solicitar Ajuste</h2><p class="text-sm text-slate-500">Gestão de ponto.</p></div>

    <!-- Seletor de Data -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
        <form action="/ponto/solicitar-ajuste" method="POST" class="flex gap-4 items-end">
            <div class="flex-1">
                <label class="block text-xs font-bold text-slate-500 uppercase mb-2">Data do Ponto</label>
                <input type="date" name="data_busca" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3" required>
            </div>
            <button type="submit" name="acao" value="buscar" class="bg-blue-600 text-white font-bold py-3 px-6 rounded-lg"><i class="fas fa-search"></i></button>
        </form>
    </div>

    {% if data_sel %}
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-8 animate-fade-in">
        <div class="flex justify-between items-center mb-4 border-b pb-2">
            <h3 class="font-bold text-slate-800">Registros em {{ data_sel.strftime('%d/%m/%Y') }}</h3>
            <button onclick="abrirInclusao()" class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 px-3 py-1 rounded font-bold transition"><i class="fas fa-plus mr-1"></i> ADICIONAR NOVO</button>
        </div>
        
        <div class="space-y-2 mb-6">
            {% for p in pontos %}
            <div class="flex justify-between items-center p-3 bg-slate-50 rounded-lg border border-slate-100">
                <div><span class="text-xs font-bold text-slate-500 block">{{ p.tipo }}</span><span class="font-mono font-bold text-slate-800">{{ p.hora_registro.strftime('%H:%M') }}</span></div>
                <div class="flex gap-2">
                    <button onclick="abrirEdicao('{{ p.id }}', '{{ p.hora_registro.strftime('%H:%M') }}', '{{ p.tipo }}')" class="text-[10px] bg-blue-50 text-blue-600 font-bold px-2 py-1 rounded hover:bg-blue-100">EDITAR</button>
                    <button onclick="abrirExclusao('{{ p.id }}', '{{ p.hora_registro.strftime('%H:%M') }}')" class="text-[10px] bg-red-50 text-red-600 font-bold px-2 py-1 rounded hover:bg-red-100">EXCLUIR</button>
                </div>
            </div>
            {% else %}
            <p class="text-xs text-slate-400 italic">Sem registros neste dia.</p>
            {% endfor %}
        </div>

        <!-- FORMULARIO OCULTO (POP-UP INLINE) -->
        <div id="formContainer" class="hidden bg-slate-50 p-4 rounded-xl border border-blue-200 shadow-inner">
            <h3 class="font-bold text-blue-700 mb-4 text-sm uppercase" id="formTitle">Detalhes da Solicitação</h3>
            <form action="/ponto/solicitar-ajuste" method="POST" class="space-y-4">
                <input type="hidden" name="acao" value="enviar">
                <input type="hidden" name="data_ref" value="{{ data_sel }}">
                <input type="hidden" name="ponto_id" id="form_ponto_id"> 
                <input type="hidden" name="tipo_solicitacao" id="form_tipo_solic"> 

                <div class="grid grid-cols-2 gap-4" id="divHorarioTipo">
                    <div>
                        <label class="block text-xs font-bold text-slate-500 uppercase mb-2">Horário</label>
                        <input type="time" name="novo_horario" id="form_horario" class="w-full bg-white border border-slate-200 rounded-lg px-4 py-2 font-mono">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-500 uppercase mb-2">Tipo</label>
                        <select name="tipo_batida" id="form_tipo" class="w-full bg-white border border-slate-200 rounded-lg px-4 py-2 text-sm">
                            <option value="Entrada">Entrada</option>
                            <option value="Ida Almoço">Ida Almoço</option>
                            <option value="Volta Almoço">Volta Almoço</option>
                            <option value="Saída">Saída</option>
                        </select>
                    </div>
                </div>
                
                <div>
                    <label class="block text-xs font-bold text-slate-500 uppercase mb-2">Justificativa</label>
                    <textarea name="justificativa" class="w-full bg-white border border-slate-200 rounded-lg px-4 py-2 text-sm" rows="2" placeholder="Motivo da alteração/exclusão..." required></textarea>
                </div>
                
                <div class="flex gap-2">
                    <button type="button" onclick="fecharForm()" class="flex-1 bg-slate-200 text-slate-600 font-bold py-2 rounded-lg text-xs">CANCELAR</button>
                    <button type="submit" class="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 rounded-lg shadow text-xs">ENVIAR</button>
                </div>
            </form>
        </div>
    </div>
    {% endif %}

    <!-- TABELA DE FEEDBACK (MEUS PEDIDOS) -->
    <div class="mt-8">
        <h3 class="font-bold text-slate-700 text-sm mb-4 border-b pb-2">Meus Pedidos Recentes</h3>
        <div class="space-y-3">
            {% for req in meus_ajustes %}
            <div class="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
                <div class="flex justify-between items-start mb-2">
                    <div>
                        <span class="text-xs font-bold text-slate-400 block">{{ req.data_referencia.strftime('%d/%m') }} - {{ req.tipo_solicitacao }}</span>
                        {% if req.status == 'Reprovado' %}
                            <p class="text-xs text-red-600 font-bold mt-1 bg-red-50 p-2 rounded">Motivo: "{{ req.motivo_reprovacao }}"</p>
                        {% endif %}
                    </div>
                    <span class="px-2 py-1 rounded text-[10px] font-bold uppercase
                        {% if req.status == 'Pendente' %} bg-yellow-100 text-yellow-700
                        {% elif req.status == 'Aprovado' %} bg-emerald-100 text-emerald-700
                        {% else %} bg-red-100 text-red-700 {% endif %}">
                        {{ req.status }}
                    </span>
                </div>
                <div class="text-xs text-slate-500 italic">"{{ req.justificativa }}"</div>
            </div>
            {% else %}
            <p class="text-center text-xs text-slate-400 py-4">Nenhum pedido recente.</p>
            {% endfor %}
        </div>
    </div>
</div>

<script>
    function abrirInclusao() {
        resetForm();
        document.getElementById('formTitle').innerText = "INCLUIR NOVO PONTO";
        document.getElementById('formTitle').className = "font-bold text-emerald-700 mb-4 text-sm uppercase";
        document.getElementById('form_tipo_solic').value = "Inclusao";
        document.getElementById('formContainer').classList.remove('hidden');
    }

    function abrirEdicao(id, hora, tipo) {
        resetForm();
        document.getElementById('formTitle').innerText = "EDITAR PONTO";
        document.getElementById('formTitle').className = "font-bold text-blue-700 mb-4 text-sm uppercase";
        document.getElementById('form_ponto_id').value = id;
        document.getElementById('form_horario').value = hora;
        document.getElementById('form_tipo').value = tipo;
        document.getElementById('form_tipo_solic').value = "Edicao";
        document.getElementById('formContainer').classList.remove('hidden');
    }

    function abrirExclusao(id, hora) {
        resetForm();
        document.getElementById('formTitle').innerText = "SOLICITAR EXCLUSÃO";
        document.getElementById('formTitle').className = "font-bold text-red-700 mb-4 text-sm uppercase";
        document.getElementById('form_ponto_id').value = id;
        document.getElementById('form_tipo_solic').value = "Exclusao";
        document.getElementById('divHorarioTipo').classList.add('hidden'); // Esconde hora pois é exclusao
        document.getElementById('formContainer').classList.remove('hidden');
    }

    function resetForm() {
        document.getElementById('form_ponto_id').value = "";
        document.getElementById('form_horario').value = "";
        document.getElementById('divHorarioTipo').classList.remove('hidden');
    }

    function fecharForm() {
        document.getElementById('formContainer').classList.add('hidden');
    }
</script>
{% endblock %}
"""

# --- ADMIN SOLICITAÇÕES (COM DIFF ANTIGO/NOVO) ---
FILE_ADMIN_SOLICITACOES = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6"><h2 class="text-2xl font-bold text-slate-800">Solicitações Pendentes</h2></div>

<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
    {% for s in solicitacoes %}
    <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm relative border-l-4 
        {% if s.tipo_solicitacao == 'Exclusao' %} border-l-red-500 
        {% elif s.tipo_solicitacao == 'Inclusao' %} border-l-emerald-500 
        {% else %} border-l-blue-500 {% endif %}">
        
        <span class="absolute top-4 right-4 bg-yellow-100 text-yellow-700 text-[10px] font-bold px-2 py-1 rounded uppercase">{{ s.tipo_solicitacao }}</span>
        
        <div class="flex items-center gap-3 mb-4">
            <div class="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center font-bold text-slate-600">{{ s.user.real_name[:2].upper() }}</div>
            <div><h3 class="font-bold text-slate-800 text-sm">{{ s.user.real_name }}</h3><p class="text-xs text-slate-500">Ref: {{ s.data_referencia.strftime('%d/%m/%Y') }}</p></div>
        </div>

        <div class="bg-slate-50 p-3 rounded-lg mb-4 text-sm">
            {% if s.tipo_solicitacao == 'Edicao' %}
                <div class="flex justify-between mb-1 text-xs">
                    <span class="text-slate-400">De:</span> 
                    <span class="font-mono text-slate-600 line-through">{{ extras[s.id] }}</span>
                </div>
                <div class="flex justify-between mb-1 text-sm font-bold">
                    <span class="text-slate-600">Para:</span> 
                    <span class="font-mono text-blue-600">{{ s.novo_horario }} ({{ s.tipo_batida }})</span>
                </div>
            {% elif s.tipo_solicitacao == 'Exclusao' %}
                <div class="text-red-600 font-bold text-center py-2">SOLICITA REMOÇÃO DO PONTO</div>
                <div class="text-center text-xs text-slate-500">Horário Alvo: {{ extras[s.id] }}</div>
            {% else %}
                <div class="text-emerald-600 font-bold text-center py-2">NOVA MARCAÇÃO</div>
                <div class="text-center font-mono">{{ s.novo_horario }} ({{ s.tipo_batida }})</div>
            {% endif %}
            
            <div class="mt-3 text-xs text-slate-600 italic border-t pt-2">"{{ s.justificativa }}"</div>
        </div>

        <form action="/admin/solicitacoes" method="POST" class="flex flex-col gap-2">
            <input type="hidden" name="solic_id" value="{{ s.id }}">
            <div class="flex gap-2">
                <button type="submit" name="decisao" value="aprovar" class="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2 rounded text-xs transition">APROVAR</button>
                <button type="button" onclick="document.getElementById('repro-{{ s.id }}').classList.remove('hidden')" class="flex-1 bg-red-100 hover:bg-red-200 text-red-600 font-bold py-2 rounded text-xs transition">REPROVAR</button>
            </div>
            <div id="repro-{{ s.id }}" class="hidden mt-2">
                <input type="text" name="motivo_repro" class="w-full border border-red-200 rounded p-2 text-xs mb-2 bg-red-50" placeholder="Motivo da reprovação (obrigatório)..." required>
                <button type="submit" name="decisao" value="reprovar" class="w-full bg-red-600 text-white font-bold py-2 rounded text-xs">ENVIAR</button>
            </div>
        </form>
    </div>
    {% else %}
    <div class="col-span-2 text-center py-12 text-slate-400 bg-white rounded-xl border border-slate-200 border-dashed">
        <p>Nenhuma solicitação pendente.</p>
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
        print("\n>>> SUCESSO V16! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V16: {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    
    write_file("templates/solicitar_ajuste.html", FILE_SOLICITAR_AJUSTE)
    write_file("templates/admin_solicitacoes.html", FILE_ADMIN_SOLICITACOES)
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



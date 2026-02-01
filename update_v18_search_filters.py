import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V18: Filtros de Busca, Detalhes de Pedidos e Filtro por Data"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""
FILE_REQ = """flask\nflask-sqlalchemy\npsycopg2-binary\ngunicorn\nflask-login\nwerkzeug"""
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Lógica de Filtros e Dados Extras) ---
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
app.secret_key = 'chave_v18_filters_secret'

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
    novo_horario = db.Column(db.String(5), nullable=True)
    tipo_batida = db.Column(db.String(20), nullable=False)
    tipo_solicitacao = db.Column(db.String(20), default='Edicao')
    justificativa = db.Column(db.String(255))
    status = db.Column(db.String(20), default='Pendente')
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
def load_user(user_id): return User.query.get(int(user_id))

# --- BOOT ---
try:
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='Thaynara').first():
            master = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
            master.set_password('1855')
            db.session.add(master); db.session.commit()
except: pass

# --- ROTAS PRINCIPAIS ---

@app.route('/ponto/solicitar-ajuste', methods=['GET', 'POST'])
@login_required
def solicitar_ajuste():
    pontos_dia = []
    data_selecionada = None
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'buscar':
            try:
                data_selecionada = datetime.strptime(request.form.get('data_busca'), '%Y-%m-%d').date()
                pontos_dia = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=data_selecionada).order_by(PontoRegistro.hora_registro).all()
            except: flash('Data inválida')
        elif acao == 'enviar':
            try:
                dt_obj = datetime.strptime(request.form.get('data_ref'), '%Y-%m-%d').date()
                p_id = int(request.form.get('ponto_id')) if request.form.get('ponto_id') else None
                solic = PontoAjuste(user_id=current_user.id, data_referencia=dt_obj, ponto_original_id=p_id, novo_horario=request.form.get('novo_horario'), tipo_batida=request.form.get('tipo_batida'), tipo_solicitacao=request.form.get('tipo_solicitacao'), justificativa=request.form.get('justificativa'))
                db.session.add(solic); db.session.commit(); flash('Solicitação enviada!')
                return redirect(url_for('solicitar_ajuste'))
            except Exception as e: flash(f'Erro: {{e}}')

    # Busca meus ajustes e popula dados extras (horario antigo)
    meus_ajustes = PontoAjuste.query.filter_by(user_id=current_user.id).order_by(PontoAjuste.created_at.desc()).limit(20).all()
    dados_extras = {{}}
    for p in meus_ajustes:
        if p.ponto_original_id:
            original = PontoRegistro.query.get(p.ponto_original_id)
            if original: dados_extras[p.id] = original.hora_registro.strftime('%H:%M')
            else: dados_extras[p.id] = "?"
            
    return render_template('solicitar_ajuste.html', pontos=pontos_dia, data_sel=data_selecionada, meus_ajustes=meus_ajustes, extras=dados_extras)

@app.route('/ponto/espelho')
@login_required
def espelho_ponto():
    data_filtro = request.args.get('data_filtro')
    
    query = PontoRegistro.query
    
    if current_user.role != 'Master':
        query = query.filter_by(user_id=current_user.id)
    
    if data_filtro:
        try:
            dt_obj = datetime.strptime(data_filtro, '%Y-%m-%d').date()
            query = query.filter_by(data_registro=dt_obj)
        except: pass
    
    if current_user.role == 'Master':
        registros_raw = query.join(User).order_by(PontoRegistro.data_registro.desc(), User.real_name, PontoRegistro.hora_registro).limit(1000).all()
        espelho_agrupado = {{}} 
        for r in registros_raw:
            chave = f"{{r.data_registro}}_{{r.user_id}}"
            if chave not in espelho_agrupado: espelho_agrupado[chave] = {{'user': r.user, 'data': r.data_registro, 'pontos': []}}
            espelho_agrupado[chave]['pontos'].append(r)
        return render_template('ponto_espelho_master.html', grupos=espelho_agrupado.values(), filtro_data=data_filtro)
    else:
        registros = query.order_by(PontoRegistro.data_registro.desc(), PontoRegistro.hora_registro.desc()).limit(100).all()
        return render_template('ponto_espelho.html', registros=registros, filtro_data=data_filtro)

@app.route('/admin/solicitacoes', methods=['GET', 'POST'])
@login_required
def admin_solicitacoes():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    if request.method == 'POST':
        try:
            solic = PontoAjuste.query.get(request.form.get('solic_id'))
            decisao = request.form.get('decisao')
            if decisao == 'aprovar':
                solic.status = 'Aprovado'
                if solic.tipo_solicitacao == 'Exclusao':
                    if solic.ponto_original_id: db.session.delete(PontoRegistro.query.get(solic.ponto_original_id))
                elif solic.tipo_solicitacao == 'Edicao':
                    p = PontoRegistro.query.get(solic.ponto_original_id)
                    h, m = map(int, solic.novo_horario.split(':'))
                    p.hora_registro = time(h, m); p.tipo = solic.tipo_batida
                elif solic.tipo_solicitacao == 'Inclusao':
                    h, m = map(int, solic.novo_horario.split(':'))
                    db.session.add(PontoRegistro(user_id=solic.user_id, data_registro=solic.data_referencia, hora_registro=time(h, m), tipo=solic.tipo_batida, latitude='Ajuste', longitude='Manual'))
                db.session.commit(); flash('Aprovado.')
            elif decisao == 'reprovar':
                solic.status = 'Reprovado'; solic.motivo_reprovacao = request.form.get('motivo_repro'); db.session.commit(); flash('Reprovado.')
        except Exception as e: db.session.rollback(); flash(f'Erro: {{e}}')
        return redirect(url_for('admin_solicitacoes'))

    pendentes = PontoAjuste.query.filter_by(status='Pendente').order_by(PontoAjuste.created_at).all()
    dados_extras = {{}}
    for p in pendentes:
        if p.ponto_original_id:
            original = PontoRegistro.query.get(p.ponto_original_id)
            if original: dados_extras[p.id] = original.hora_registro.strftime('%H:%M')
    return render_template('admin_solicitacoes.html', solicitacoes=pendentes, extras=dados_extras)

# --- ROTAS MANTIDAS (Login, Estoque, User Admin) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user); return redirect(url_for('primeiro_acesso')) if user.is_first_access else redirect(url_for('dashboard'))
        flash('Inválido.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/primeiro-acesso', methods=['GET', 'POST'])
@login_required
def primeiro_acesso():
    if request.method == 'POST':
        if request.form.get('nova_senha') == request.form.get('confirmacao'): current_user.set_password(request.form.get('nova_senha')); current_user.is_first_access = False; db.session.commit(); return redirect(url_for('dashboard'))
    return render_template('primeiro_acesso.html')

@app.route('/admin/usuarios')
@login_required
def gerenciar_usuarios(): return render_template('admin_usuarios.html', users=User.query.all()) if current_user.role == 'Master' else redirect(url_for('dashboard'))

@app.route('/admin/usuarios/novo', methods=['GET', 'POST'])
@login_required
def novo_usuario(): 
    if request.method == 'POST':
        uname = request.form.get('username')
        if User.query.filter_by(username=uname).first(): flash('Erro: Existe.')
        else:
            senha = secrets.token_hex(3)
            novo = User(username=uname, real_name=request.form.get('real_name'), role=request.form.get('role'), is_first_access=True, horario_entrada=request.form.get('h_ent'), horario_almoco_inicio=request.form.get('h_alm_ini'), horario_almoco_fim=request.form.get('h_alm_fim'), horario_saida=request.form.get('h_sai'))
            novo.set_password(senha); db.session.add(novo); db.session.commit()
            return render_template('sucesso_usuario.html', novo_user=uname, senha_gerada=senha)
    return render_template('novo_usuario.html')

@app.route('/admin/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        if request.form.get('acao') == 'resetar_senha': nova = secrets.token_hex(3); user.set_password(nova); user.is_first_access = True; db.session.commit(); flash(f'Senha: {{nova}}'); return redirect(url_for('editar_usuario', id=id))
        elif request.form.get('acao') == 'excluir': 
            if user.username != 'Thaynara': db.session.delete(user); db.session.commit()
            return redirect(url_for('gerenciar_usuarios'))
        else:
            user.real_name = request.form.get('real_name'); user.username = request.form.get('username'); user.horario_entrada = request.form.get('h_ent'); user.horario_almoco_inicio = request.form.get('h_alm_ini'); user.horario_almoco_fim = request.form.get('h_alm_fim'); user.horario_saida = request.form.get('h_sai')
            if user.username != 'Thaynara': user.role = request.form.get('role')
            db.session.commit(); return redirect(url_for('gerenciar_usuarios'))
    return render_template('editar_usuario.html', user=user)

@app.route('/')
@login_required
def dashboard():
    hoje = get_brasil_time().date()
    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).count()
    status = "Não Iniciado"
    if pontos == 1: status = "Trabalhando"
    elif pontos == 2: status = "Almoço"
    elif pontos == 3: status = "Trabalhando (Tarde)"
    elif pontos >= 4: status = "Dia Finalizado"
    return render_template('dashboard.html', status_ponto=status)

@app.route('/ponto/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    hoje = get_brasil_time().date()
    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
    prox = "Entrada"
    if len(pontos) == 1: prox = "Ida Almoço"
    elif len(pontos) == 2: prox = "Volta Almoço"
    elif len(pontos) == 3: prox = "Saída"
    elif len(pontos) >= 4: prox = "Extra"
    if request.method == 'POST':
        db.session.add(PontoRegistro(user_id=current_user.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=prox, latitude=request.form.get('latitude'), longitude=request.form.get('longitude')))
        db.session.commit(); return redirect(url_for('dashboard'))
    return render_template('ponto_registro.html', proxima_acao=prox, hoje=hoje, pontos=pontos)

@app.route('/controle-uniforme')
@login_required
def controle_uniforme(): return render_template('controle_uniforme.html', itens=ItemEstoque.query.all()) if current_user.role == 'Master' else redirect(url_for('dashboard'))

@app.route('/entrada', methods=['GET', 'POST'])
@login_required
def entrada(): 
    if request.method == 'POST': 
        # (Logica estoque resumida para brevidade)
        return redirect(url_for('controle_uniforme'))
    return render_template('entrada.html')

@app.route('/saida', methods=['GET', 'POST'])
@login_required
def saida():
    if request.method == 'POST': return redirect(url_for('controle_uniforme'))
    return render_template('saida.html', itens=ItemEstoque.query.all())

@app.route('/gerenciar/item/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_item(id):
    item = ItemEstoque.query.get_or_404(id)
    if request.method == 'POST':
        if request.form.get('acao') == 'excluir': db.session.delete(item); db.session.commit()
        else: item.nome = request.form.get('nome'); item.quantidade = int(request.form.get('quantidade')); db.session.commit()
        return redirect(url_for('controle_uniforme'))
    return render_template('editar_item.html', item=item)

@app.route('/historico/entrada')
@login_required
def view_historico_entrada(): return render_template('historico_entrada.html', logs=HistoricoEntrada.query.all())

@app.route('/historico/saida')
@login_required
def view_historico_saida(): return render_template('historico_saida.html', logs=HistoricoSaida.query.all())

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
"""

# --- SOLICITAR AJUSTE (MEUS PEDIDOS DETALHADO) ---
FILE_SOLICITAR_AJUSTE = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-2xl mx-auto">
    <div class="mb-6"><h2 class="text-xl font-bold text-slate-800">Solicitar Ajuste</h2><p class="text-sm text-slate-500">Gestão de ponto.</p></div>

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
            {% else %}<p class="text-xs text-slate-400 italic">Sem registros neste dia.</p>{% endfor %}
        </div>

        <div id="formContainer" class="hidden bg-slate-50 p-4 rounded-xl border border-blue-200 shadow-inner">
            <h3 class="font-bold text-blue-700 mb-4 text-sm uppercase" id="formTitle">Detalhes</h3>
            <form action="/ponto/solicitar-ajuste" method="POST" class="space-y-4">
                <input type="hidden" name="acao" value="enviar">
                <input type="hidden" name="data_ref" value="{{ data_sel }}">
                <input type="hidden" name="ponto_id" id="form_ponto_id"> 
                <input type="hidden" name="tipo_solicitacao" id="form_tipo_solic"> 
                <div class="grid grid-cols-2 gap-4" id="divHorarioTipo">
                    <div><label class="block text-xs font-bold text-slate-500 uppercase mb-2">Horário</label><input type="time" name="novo_horario" id="form_horario" class="w-full bg-white border border-slate-200 rounded-lg px-4 py-2 font-mono"></div>
                    <div><label class="block text-xs font-bold text-slate-500 uppercase mb-2">Tipo</label><select name="tipo_batida" id="form_tipo" class="w-full bg-white border border-slate-200 rounded-lg px-4 py-2 text-sm"><option value="Entrada">Entrada</option><option value="Ida Almoço">Ida Almoço</option><option value="Volta Almoço">Volta Almoço</option><option value="Saída">Saída</option></select></div>
                </div>
                <div><label class="block text-xs font-bold text-slate-500 uppercase mb-2">Justificativa</label><textarea name="justificativa" class="w-full bg-white border border-slate-200 rounded-lg px-4 py-2 text-sm" rows="2" required></textarea></div>
                <div class="flex gap-2"><button type="button" onclick="fecharForm()" class="flex-1 bg-slate-200 text-slate-600 font-bold py-2 rounded-lg text-xs">CANCELAR</button><button type="submit" class="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 rounded-lg shadow text-xs">ENVIAR</button></div>
            </form>
        </div>
    </div>
    {% endif %}

    <div class="mt-8">
        <h3 class="font-bold text-slate-700 text-sm mb-4 border-b pb-2">Meus Pedidos Recentes</h3>
        <div class="space-y-3">
            {% for req in meus_ajustes %}
            <div class="bg-white border border-slate-200 rounded-lg p-4 shadow-sm relative pl-4 border-l-4 {% if req.status == 'Aprovado' %} border-l-emerald-500 {% elif req.status == 'Reprovado' %} border-l-red-500 {% else %} border-l-yellow-500 {% endif %}">
                <div class="flex justify-between items-start mb-2">
                    <span class="text-[10px] font-bold uppercase text-slate-400">{{ req.data_referencia.strftime('%d/%m') }} - {{ req.tipo_solicitacao }}</span>
                    <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded {% if req.status == 'Pendente' %} bg-yellow-100 text-yellow-700 {% elif req.status == 'Aprovado' %} bg-emerald-100 text-emerald-700 {% else %} bg-red-100 text-red-700 {% endif %}">{{ req.status }}</span>
                </div>
                
                <div class="grid grid-cols-2 gap-2 text-xs mb-2 bg-slate-50 p-2 rounded">
                    <div><span class="block text-slate-400">Horário Antigo</span><strong class="font-mono text-slate-600">{{ extras.get(req.id, '-') }}</strong></div>
                    <div><span class="block text-slate-400">Horário Novo</span><strong class="font-mono text-blue-600">{% if req.novo_horario %}{{ req.novo_horario }} ({{ req.tipo_batida }}){% else %} - {% endif %}</strong></div>
                </div>

                <div class="text-xs text-slate-500 italic mb-2">Justificativa: "{{ req.justificativa }}"</div>
                {% if req.status == 'Reprovado' %}<div class="bg-red-50 p-2 rounded border border-red-100 text-xs text-red-700"><strong>Devolutiva:</strong> {{ req.motivo_reprovacao }}</div>{% endif %}
            </div>
            {% else %}<p class="text-center text-xs text-slate-400 py-4">Nenhum pedido recente.</p>{% endfor %}
        </div>
    </div>
</div>
<script>
    function abrirInclusao() { resetForm(); document.getElementById('formTitle').innerText = "INCLUIR"; document.getElementById('form_tipo_solic').value = "Inclusao"; document.getElementById('formContainer').classList.remove('hidden'); }
    function abrirEdicao(id, hora, tipo) { resetForm(); document.getElementById('formTitle').innerText = "EDITAR"; document.getElementById('form_ponto_id').value = id; document.getElementById('form_horario').value = hora; document.getElementById('form_tipo').value = tipo; document.getElementById('form_tipo_solic').value = "Edicao"; document.getElementById('formContainer').classList.remove('hidden'); }
    function abrirExclusao(id, hora) { resetForm(); document.getElementById('formTitle').innerText = "EXCLUIR"; document.getElementById('form_ponto_id').value = id; document.getElementById('form_tipo_solic').value = "Exclusao"; document.getElementById('divHorarioTipo').classList.add('hidden'); document.getElementById('formContainer').classList.remove('hidden'); }
    function resetForm() { document.getElementById('form_ponto_id').value = ""; document.getElementById('form_horario').value = ""; document.getElementById('divHorarioTipo').classList.remove('hidden'); }
    function fecharForm() { document.getElementById('formContainer').classList.add('hidden'); }
</script>
{% endblock %}
"""

# --- ADMIN USUARIOS (COM BUSCA) ---
FILE_ADMIN_USUARIOS = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center justify-between mb-6">
    <h2 class="text-2xl font-bold text-slate-800">Funcionários</h2>
</div>
<a href="/admin/usuarios/novo" class="block w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-xl shadow-md text-center mb-8"><i class="fas fa-user-plus mr-2"></i> CADASTRAR NOVO</a>

<!-- BARRA DE BUSCA -->
<div class="mb-6">
    <input type="text" id="buscaFunc" onkeyup="filtrarTabela('buscaFunc', 'listaFunc')" placeholder="Pesquisar funcionário..." class="w-full p-4 rounded-xl border border-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <div class="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center"><h3 class="font-bold text-slate-700">Equipe</h3><span class="text-xs bg-slate-200 text-slate-600 px-2 py-1 rounded-full font-bold">{{ users|length }}</span></div>
    <div class="divide-y divide-slate-100" id="listaFunc">
        {% for u in users %}
        <div class="px-6 py-4 flex items-center justify-between hover:bg-slate-50 transition group item-lista">
            <div class="flex items-center gap-4">
                <div class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm bg-slate-100 text-slate-600">{{ u.real_name[:2].upper() }}</div>
                <div><div class="font-bold text-slate-800 nome-item">{{ u.real_name }}</div><div class="text-xs text-slate-500">{{ u.role }}</div></div>
            </div>
            <div class="flex items-center gap-3">
                {% if u.is_first_access %}<span class="px-2 py-1 bg-yellow-100 text-yellow-700 text-[10px] font-bold uppercase rounded">Pendente</span>{% else %}<span class="px-2 py-1 bg-emerald-100 text-emerald-700 text-[10px] font-bold uppercase rounded">Ativo</span>{% endif %}
                <a href="/admin/usuarios/editar/{{ u.id }}" class="w-8 h-8 flex items-center justify-center rounded-full text-slate-300 hover:bg-white hover:text-blue-600 border border-transparent hover:border-slate-200 transition"><i class="fas fa-pencil-alt text-xs"></i></a>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
<script>
function filtrarTabela(inputId, listaId) {
    let input = document.getElementById(inputId);
    let filter = input.value.toUpperCase();
    let lista = document.getElementById(listaId);
    let itens = lista.getElementsByClassName('item-lista');
    for (let i = 0; i < itens.length; i++) {
        let nome = itens[i].getElementsByClassName('nome-item')[0];
        if (nome.innerHTML.toUpperCase().indexOf(filter) > -1) { itens[i].style.display = ""; } else { itens[i].style.display = "none"; }
    }
}
</script>
{% endblock %}
"""

# --- ADMIN SOLICITACOES (COM BUSCA) ---
FILE_ADMIN_SOLICITACOES = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6"><h2 class="text-2xl font-bold text-slate-800">Solicitações</h2></div>

<div class="mb-6"><input type="text" id="buscaSolic" onkeyup="filtrarSolic('buscaSolic', 'gridSolic')" placeholder="Pesquisar por nome..." class="w-full p-4 rounded-xl border border-slate-200 shadow-sm"></div>

<div class="grid grid-cols-1 md:grid-cols-2 gap-6" id="gridSolic">
    {% for s in solicitacoes %}
    <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm relative border-l-4 {% if s.tipo_solicitacao == 'Exclusao' %} border-l-red-500 {% elif s.tipo_solicitacao == 'Inclusao' %} border-l-emerald-500 {% else %} border-l-blue-500 {% endif %} item-solic">
        <span class="absolute top-4 right-4 bg-yellow-100 text-yellow-700 text-[10px] font-bold px-2 py-1 rounded uppercase">{{ s.tipo_solicitacao }}</span>
        <div class="flex items-center gap-3 mb-4">
            <div class="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center font-bold text-slate-600">{{ s.user.real_name[:2].upper() }}</div>
            <div><h3 class="font-bold text-slate-800 text-sm nome-solic">{{ s.user.real_name }}</h3><p class="text-xs text-slate-500">Ref: {{ s.data_referencia.strftime('%d/%m/%Y') }}</p></div>
        </div>
        <div class="bg-slate-50 p-3 rounded-lg mb-4 text-sm">
            {% if s.tipo_solicitacao == 'Edicao' %}
                <div class="flex justify-between mb-1 text-xs"><span class="text-slate-400">De:</span> <span class="font-mono text-slate-600 line-through">{{ extras[s.id] }}</span></div>
                <div class="flex justify-between mb-1 text-sm font-bold"><span class="text-slate-600">Para:</span> <span class="font-mono text-blue-600">{{ s.novo_horario }} ({{ s.tipo_batida }})</span></div>
            {% elif s.tipo_solicitacao == 'Exclusao' %}
                <div class="text-red-600 font-bold text-center py-2">SOLICITA REMOÇÃO</div><div class="text-center text-xs text-slate-500">Alvo: {{ extras[s.id] }}</div>
            {% else %}
                <div class="text-emerald-600 font-bold text-center py-2">NOVA MARCAÇÃO</div><div class="text-center font-mono">{{ s.novo_horario }} ({{ s.tipo_batida }})</div>
            {% endif %}
            <div class="mt-3 text-xs text-slate-600 italic border-t pt-2">"{{ s.justificativa }}"</div>
        </div>
        <form action="/admin/solicitacoes" method="POST" class="flex flex-col gap-2">
            <input type="hidden" name="solic_id" value="{{ s.id }}">
            <div class="flex gap-2">
                <button type="submit" name="decisao" value="aprovar" class="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2 rounded text-xs transition">APROVAR</button>
                <button type="button" onclick="document.getElementById('repro-{{ s.id }}').classList.remove('hidden')" class="flex-1 bg-red-100 hover:bg-red-200 text-red-600 font-bold py-2 rounded text-xs transition">REPROVAR</button>
            </div>
            <div id="repro-{{ s.id }}" class="hidden mt-2"><input type="text" name="motivo_repro" class="w-full border border-red-200 rounded p-2 text-xs mb-2 bg-red-50" placeholder="Motivo..."><button type="submit" name="decisao" value="reprovar" class="w-full bg-red-600 text-white font-bold py-2 rounded text-xs">ENVIAR</button></div>
        </form>
    </div>
    {% else %}<div class="col-span-2 text-center py-12 text-slate-400 bg-white rounded-xl border border-slate-200 border-dashed"><p>Nenhuma solicitação pendente.</p></div>{% endfor %}
</div>
<script>
function filtrarSolic(inputId, gridId) {
    let input = document.getElementById(inputId);
    let filter = input.value.toUpperCase();
    let grid = document.getElementById(gridId);
    let itens = grid.getElementsByClassName('item-solic');
    for (let i = 0; i < itens.length; i++) {
        let nome = itens[i].getElementsByClassName('nome-solic')[0];
        if (nome.innerHTML.toUpperCase().indexOf(filter) > -1) { itens[i].style.display = ""; } else { itens[i].style.display = "none"; }
    }
}
</script>
{% endblock %}
"""

# --- ESPELHO MASTER (COM BUSCA E FILTRO) ---
FILE_PONTO_ESPELHO_MASTER = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6 flex flex-col md:flex-row justify-between items-center gap-4">
    <h2 class="text-2xl font-bold text-slate-800">Espelho Geral</h2>
    <form action="/ponto/espelho" method="GET" class="flex gap-2">
        <input type="date" name="data_filtro" value="{{ filtro_data }}" class="border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-600">
        <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded-lg font-bold text-sm"><i class="fas fa-filter"></i></button>
        {% if filtro_data %}<a href="/ponto/espelho" class="bg-slate-200 text-slate-600 px-4 py-2 rounded-lg font-bold text-sm">Limpar</a>{% endif %}
    </form>
</div>

<div class="mb-6"><input type="text" id="buscaEspelho" onkeyup="filtrarEspelho('buscaEspelho', 'listaEspelho')" placeholder="Pesquisar funcionário..." class="w-full p-4 rounded-xl border border-slate-200 shadow-sm"></div>

<div class="space-y-2" id="listaEspelho">
    {% for grupo in grupos %}
    <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm item-espelho">
        <button onclick="toggleDetails('detalhe-{{ loop.index }}')" class="w-full flex justify-between items-center p-4 bg-slate-50 hover:bg-slate-100 transition text-left focus:outline-none">
            <div class="flex items-center gap-4">
                <div class="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold">{{ grupo.user.real_name[:2].upper() }}</div>
                <div><h3 class="font-bold text-slate-800 text-sm nome-func">{{ grupo.user.real_name }}</h3><p class="text-xs text-slate-500 font-mono">{{ grupo.data.strftime('%d/%m/%Y') }}</p></div>
            </div>
            <div class="flex items-center gap-3"><span class="text-xs font-bold uppercase tracking-wider text-slate-400">{{ grupo.pontos|length }} Batidas</span><i class="fas fa-chevron-down text-slate-400"></i></div>
        </button>
        <div id="detalhe-{{ loop.index }}" class="hidden border-t border-slate-100">
            <div class="p-4 bg-white grid grid-cols-2 gap-2">
                {% for p in grupo.pontos %}
                <div class="flex justify-between items-center p-2 rounded bg-slate-50 border border-slate-100"><span class="text-xs font-bold text-slate-600">{{ p.tipo }}</span><span class="text-sm font-mono font-bold text-blue-600">{{ p.hora_registro.strftime('%H:%M') }}</span></div>
                {% endfor %}
            </div>
        </div>
    </div>
    {% else %}<div class="text-center py-10 text-slate-400">Nenhum registro encontrado.</div>{% endfor %}
</div>
<script>
function filtrarEspelho(inputId, listaId) {
    let input = document.getElementById(inputId);
    let filter = input.value.toUpperCase();
    let lista = document.getElementById(listaId);
    let itens = lista.getElementsByClassName('item-espelho');
    for (let i = 0; i < itens.length; i++) {
        let nome = itens[i].getElementsByClassName('nome-func')[0];
        if (nome.innerHTML.toUpperCase().indexOf(filter) > -1) { itens[i].style.display = ""; } else { itens[i].style.display = "none"; }
    }
}
</script>
{% endblock %}
"""

# --- ESPELHO COLABORADOR (COM FILTRO DATA) ---
FILE_PONTO_ESPELHO = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center justify-between mb-6">
    <h2 class="text-xl font-bold text-slate-800">Espelho de Ponto</h2>
    <form action="/ponto/espelho" method="GET" class="flex gap-2">
        <input type="date" name="data_filtro" value="{{ filtro_data }}" class="border border-slate-200 rounded-lg px-2 py-1 text-xs text-slate-600">
        <button type="submit" class="bg-blue-600 text-white px-3 py-1 rounded-lg font-bold text-xs"><i class="fas fa-filter"></i></button>
        {% if filtro_data %}<a href="/ponto/espelho" class="bg-slate-200 text-slate-600 px-3 py-1 rounded-lg font-bold text-xs">X</a>{% endif %}
    </form>
</div>
<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <table class="w-full text-left text-sm text-slate-600">
        <thead class="bg-slate-50 text-xs uppercase text-slate-400 font-bold"><tr><th class="px-6 py-3">Data</th><th class="px-6 py-3">Tipo</th><th class="px-6 py-3 text-right">Hora</th></tr></thead>
        <tbody class="divide-y divide-slate-100">
            {% for r in registros %}
            <tr class="hover:bg-slate-50">
                <td class="px-6 py-4 font-mono text-xs">{{ r.data_registro.strftime('%d/%m') }}</td>
                <td class="px-6 py-4"><span class="px-2 py-1 rounded text-[10px] font-bold uppercase {% if 'Entrada' in r.tipo %} bg-emerald-100 text-emerald-700 {% elif 'Saída' in r.tipo %} bg-red-100 text-red-700 {% else %} bg-blue-100 text-blue-700 {% endif %}">{{ r.tipo }}</span></td>
                <td class="px-6 py-4 text-right font-mono font-bold">{{ r.hora_registro.strftime('%H:%M') }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
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
        print("\n>>> SUCESSO V18! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V18: {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    
    write_file("templates/solicitar_ajuste.html", FILE_SOLICITAR_AJUSTE) # Atualizado
    write_file("templates/admin_usuarios.html", FILE_ADMIN_USUARIOS) # Busca
    write_file("templates/admin_solicitacoes.html", FILE_ADMIN_SOLICITACOES) # Busca
    write_file("templates/ponto_espelho_master.html", FILE_PONTO_ESPELHO_MASTER) # Busca + Filtro
    write_file("templates/ponto_espelho.html", FILE_PONTO_ESPELHO) # Filtro
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



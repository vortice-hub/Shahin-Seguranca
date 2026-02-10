import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V36: Botao Zerar Relatorio de Folha (Limpa Saldos do Mes)"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""
FILE_REQ = """flask\nflask-sqlalchemy\npsycopg2-binary\ngunicorn\nflask-login\nwerkzeug"""
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Nova Rota de Zerar) ---
FILE_APP = f"""
import os
import logging
import secrets
import random
import unicodedata
import calendar
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date, time
from sqlalchemy import text, func

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'chave_v36_reset_report'

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

def remove_accents(input_str):
    if not input_str: return ""
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def gerar_login_automatico(nome_completo):
    try:
        clean_name = remove_accents(nome_completo).lower().strip()
        parts = clean_name.split()
        if not parts: return f"user.{{random.randint(10,99)}}"
        primeiro = parts[0]
        ultimo = parts[-1] if len(parts) > 1 else "colab"
        for _ in range(10): 
            num = random.randint(10, 99)
            login_candidato = f"{{primeiro}}.{{ultimo}}.{{num}}"
            if not User.query.filter_by(username=login_candidato).first():
                return login_candidato
        return f"{{primeiro}}.{{random.randint(1000,9999)}}"
    except:
        return f"user.{{random.randint(1000,9999)}}"

# --- MODELOS ---
class PreCadastro(db.Model):
    __tablename__ = 'pre_cadastros'
    id = db.Column(db.Integer, primary_key=True)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    nome_previsto = db.Column(db.String(100))
    cargo = db.Column(db.String(50), default='Colaborador')
    salario = db.Column(db.Float, default=2000.00)
    horario_entrada = db.Column(db.String(5), default='07:12')
    horario_almoco_inicio = db.Column(db.String(5), default='12:00')
    horario_almoco_fim = db.Column(db.String(5), default='13:00')
    horario_saida = db.Column(db.String(5), default='17:00')
    escala = db.Column(db.String(20), default='Livre')
    data_inicio_escala = db.Column(db.Date, nullable=True)
    criado_em = db.Column(db.DateTime, default=get_brasil_time)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    real_name = db.Column(db.String(100))
    role = db.Column(db.String(50)) 
    cpf = db.Column(db.String(14), unique=True, nullable=True)
    is_first_access = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_brasil_time)
    
    horario_entrada = db.Column(db.String(5), default='07:12')
    horario_almoco_inicio = db.Column(db.String(5), default='12:00')
    horario_almoco_fim = db.Column(db.String(5), default='13:00')
    horario_saida = db.Column(db.String(5), default='17:00')
    salario = db.Column(db.Float, default=2000.00)
    escala = db.Column(db.String(20), default='Livre')
    data_inicio_escala = db.Column(db.Date, nullable=True)

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

class PontoResumo(db.Model):
    __tablename__ = 'ponto_resumos'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_referencia = db.Column(db.Date, nullable=False)
    minutos_trabalhados = db.Column(db.Integer, default=0)
    minutos_esperados = db.Column(db.Integer, default=0)
    minutos_saldo = db.Column(db.Integer, default=0)
    status_dia = db.Column(db.String(50))
    user = db.relationship('User', backref=db.backref('resumos', lazy=True))

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

# --- MOTOR DE CÁLCULO ---
def time_to_min(t_input):
    if not t_input: return 0
    try:
        if isinstance(t_input, time): return t_input.hour * 60 + t_input.minute
        h, m = map(int, str(t_input).split(':')[:2]); return h * 60 + m
    except: return 0

def calcular_dia(user_id, data_ref):
    user = User.query.get(user_id)
    if not user: return
    
    dia_trabalho = True
    if user.escala == '5x2' and data_ref.weekday() >= 5: dia_trabalho = False
    elif user.escala == '12x36' and user.data_inicio_escala:
        if (data_ref - user.data_inicio_escala).days % 2 != 0: dia_trabalho = False
            
    if dia_trabalho:
        m_ent = time_to_min(user.horario_entrada)
        m_alm_ini = time_to_min(user.horario_almoco_inicio)
        m_alm_fim = time_to_min(user.horario_almoco_fim)
        m_sai = time_to_min(user.horario_saida)
        jornada_esperada = max(0, m_alm_ini - m_ent) + max(0, m_sai - m_alm_fim)
        if jornada_esperada <= 0: jornada_esperada = 480
    else: jornada_esperada = 0

    pontos = PontoRegistro.query.filter_by(user_id=user_id, data_registro=data_ref).order_by(PontoRegistro.hora_registro).all()
    trabalhado_minutos = 0
    status = "OK"
    saldo = 0
    
    if len(pontos) < 2:
        if len(pontos) == 0:
            if dia_trabalho: status = "Falta"; saldo = -jornada_esperada
            else: status = "Folga"; saldo = 0
    else:
        loops = len(pontos)
        if loops % 2 != 0: status = "Erro: Ímpar"; loops -= 1
        for i in range(0, loops, 2):
            p_ent = time_to_min(pontos[i].hora_registro)
            p_sai = time_to_min(pontos[i+1].hora_registro)
            trabalhado_minutos += (p_sai - p_ent)
        saldo = trabalhado_minutos - jornada_esperada
        if not dia_trabalho and trabalhado_minutos > 0: status = "Hora Extra (Folga)"; saldo = trabalhado_minutos
        else:
            if abs(saldo) <= 10: saldo = 0; status = "Normal"
            elif saldo > 0: status = "Hora Extra"
            elif saldo < 0: status = "Atraso/Débito"

    resumo = PontoResumo.query.filter_by(user_id=user_id, data_referencia=data_ref).first()
    if not resumo: resumo = PontoResumo(user_id=user_id, data_referencia=data_ref); db.session.add(resumo)
    resumo.minutos_trabalhados = trabalhado_minutos; resumo.minutos_esperados = jornada_esperada; resumo.minutos_saldo = saldo; resumo.status_dia = status
    db.session.commit()

# --- BOOT ---
try:
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='Thaynara').first():
            m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False); m.set_password('1855'); db.session.add(m); db.session.commit()
except: pass

# --- NOVA ROTA: ZERAR RELATORIO ---
@app.route('/admin/relatorio-folha/zerar', methods=['POST'])
@login_required
def zerar_relatorio():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    
    mes_ref = request.form.get('mes_ref')
    if not mes_ref:
        flash('Erro: Mês não identificado.')
        return redirect(url_for('admin_relatorio_folha'))
        
    try:
        ano, mes = map(int, mes_ref.split('-'))
        
        # Apaga SOMENTE os resumos calculados daquele mes
        # Os pontos originais sao mantidos para seguranca
        num_deleted = PontoResumo.query.filter(
            func.extract('year', PontoResumo.data_referencia) == ano,
            func.extract('month', PontoResumo.data_referencia) == mes
        ).delete(synchronize_session=False)
        
        db.session.commit()
        flash(f'Relatório de {{mes_ref}} zerado com sucesso! ({{num_deleted}} registros limpos)')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao zerar: {{e}}')
        
    return redirect(url_for('admin_relatorio_folha'))

@app.route('/admin/relatorio-folha', methods=['GET', 'POST'])
@login_required
def admin_relatorio_folha():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    mes_ref = request.form.get('mes_ref') or datetime.now().strftime('%Y-%m')
    try: ano, mes = map(int, mes_ref.split('-'))
    except: hoje = datetime.now(); ano, mes = hoje.year, hoje.month; mes_ref = hoje.strftime('%Y-%m')
    if request.method == 'POST' and not request.form.get('acao_zerar'): flash(f'Exibindo dados de {{mes_ref}}')
    users = User.query.order_by(User.real_name).all()
    relatorio = []
    for u in users:
        try:
            resumos = PontoResumo.query.filter(PontoResumo.user_id == u.id, func.extract('year', PontoResumo.data_referencia) == ano, func.extract('month', PontoResumo.data_referencia) == mes).all()
            total_saldo = sum(r.minutos_saldo for r in resumos)
            sinal = "+" if total_saldo >= 0 else "-"
            abs_s = abs(total_saldo)
            sal_val = u.salario if u.salario is not None else 0.0
            relatorio.append({{'nome': u.real_name, 'cargo': u.role, 'salario': sal_val, 'saldo_minutos': total_saldo, 'saldo_formatado': f"{{sinal}}{{abs_s // 60:02d}}:{{abs_s % 60:02d}}", 'status': 'Crédito' if total_saldo >= 0 else 'Débito'}})
        except: continue
    return render_template('admin_relatorio_folha.html', relatorio=relatorio, mes_ref=mes_ref)

@app.route('/admin/usuarios/novo', methods=['GET', 'POST'])
@login_required
def novo_usuario():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    if request.method == 'POST':
        try:
            real_name = request.form.get('real_name')
            cpf = request.form.get('cpf').replace('.', '').replace('-', '').strip()
            if User.query.filter_by(cpf=cpf).first(): flash('Erro: CPF já existe.'); return redirect(url_for('novo_usuario'))
            dt_escala = None
            if request.form.get('dt_escala'): dt_escala = datetime.strptime(request.form.get('dt_escala'), '%Y-%m-%d').date()
            pre = PreCadastro(cpf=cpf, nome_previsto=real_name, cargo=request.form.get('role'), salario=float(request.form.get('salario') or 0), horario_entrada=request.form.get('h_ent') or '07:12', horario_almoco_inicio=request.form.get('h_alm_ini') or '12:00', horario_almoco_fim=request.form.get('h_alm_fim') or '13:00', horario_saida=request.form.get('h_sai') or '17:00', escala=request.form.get('escala'), data_inicio_escala=dt_escala)
            db.session.add(pre); db.session.commit()
            return render_template('sucesso_usuario.html', nome_real=real_name, cpf=cpf)
        except Exception as e: db.session.rollback(); logger.error(f"Erro: {{e}}"); flash(f"Erro interno: {{str(e)}}"); return redirect(url_for('novo_usuario'))
    return render_template('novo_usuario.html')

@app.route('/cadastrar', methods=['GET', 'POST'])
def auto_cadastro():
    if request.method == 'GET': return render_template('auto_cadastro.html', step=1)
    if request.method == 'POST':
        cpf = request.form.get('cpf').replace('.', '').replace('-', '').strip()
        pre = PreCadastro.query.filter_by(cpf=cpf).first()
        if not pre:
            if User.query.filter_by(cpf=cpf).first(): flash('Você já tem cadastro. Faça login.'); return redirect(url_for('login'))
            flash('CPF não encontrado na lista de liberação. Fale com o RH.'); return redirect(url_for('auto_cadastro'))
        password = request.form.get('password')
        if password:
            username = gerar_login_automatico(pre.nome_previsto)
            while User.query.filter_by(username=username).first(): username = gerar_login_automatico(pre.nome_previsto)
            novo_user = User(username=username, password_hash=generate_password_hash(password), real_name=pre.nome_previsto, role=pre.cargo, cpf=cpf, salario=pre.salario, horario_entrada=pre.horario_entrada, horario_almoco_inicio=pre.horario_almoco_inicio, horario_almoco_fim=pre.horario_almoco_fim, horario_saida=pre.horario_saida, escala=pre.escala, data_inicio_escala=pre.data_inicio_escala, is_first_access=False)
            db.session.add(novo_user); db.session.delete(pre); db.session.commit()
            return render_template('auto_cadastro_sucesso.html', username=username, nome=pre.nome_previsto)
        else: return render_template('auto_cadastro.html', step=2, cpf=cpf, nome=pre.nome_previsto)

@app.route('/admin/liberar-acesso/excluir/<int:id>')
@login_required
def excluir_pre_cadastro(id):
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    pre = PreCadastro.query.get(id)
    if pre: db.session.delete(pre); db.session.commit(); flash('Removido.')
    return redirect(url_for('gerenciar_usuarios'))

@app.route('/admin/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        try:
            acao = request.form.get('acao')
            if acao == 'excluir':
                if user.username == 'Thaynara': flash('Erro master.')
                else: 
                    PontoRegistro.query.filter_by(user_id=user.id).delete(); PontoResumo.query.filter_by(user_id=user.id).delete(); PontoAjuste.query.filter_by(user_id=user.id).delete(); db.session.delete(user); db.session.commit(); flash('Excluido.')
                return redirect(url_for('gerenciar_usuarios'))
            elif acao == 'resetar_senha': nova = secrets.token_hex(3); user.set_password(nova); user.is_first_access = True; db.session.commit(); flash(f'Senha: {{nova}}'); return redirect(url_for('editar_usuario', id=id))
            else:
                user.real_name = request.form.get('real_name'); user.username = request.form.get('username')
                if user.username != 'Thaynara': user.role = request.form.get('role')
                user.salario = float(request.form.get('salario') or 0); user.horario_entrada = request.form.get('h_ent'); user.horario_almoco_inicio = request.form.get('h_alm_ini'); user.horario_almoco_fim = request.form.get('h_alm_fim'); user.horario_saida = request.form.get('h_sai'); user.escala = request.form.get('escala')
                if request.form.get('dt_escala'): user.data_inicio_escala = datetime.strptime(request.form.get('dt_escala'), '%Y-%m-%d').date()
                db.session.commit(); calcular_dia(user.id, get_brasil_time().date()); return redirect(url_for('gerenciar_usuarios'))
        except Exception as e: db.session.rollback(); flash(f'Erro: {{e}}'); return redirect(url_for('editar_usuario', id=id))
    return render_template('editar_usuario.html', user=user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')): login_user(user); return redirect(url_for('primeiro_acesso')) if user.is_first_access else redirect(url_for('dashboard'))
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
def gerenciar_usuarios(): 
    users = User.query.all(); pendentes = PreCadastro.query.all()
    return render_template('admin_usuarios.html', users=users, pendentes=pendentes)

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
    meses = {{1:'Janeiro', 2:'Fevereiro', 3:'Março', 4:'Abril', 5:'Maio', 6:'Junho', 7:'Julho', 8:'Agosto', 9:'Setembro', 10:'Outubro', 11:'Novembro', 12:'Dezembro'}}
    hoje_extenso = f"{{hoje.day}} de {{meses[hoje.month]}} de {{hoje.year}}"
    bloqueado = False; motivo = ""
    if current_user.escala == '5x2' and hoje.weekday() >= 5: bloqueado = True; motivo = "Não é possível realizar a marcação de ponto."
    elif current_user.escala == '12x36' and current_user.data_inicio_escala:
        if (hoje - current_user.data_inicio_escala).days % 2 != 0: bloqueado = True; motivo = "Não é possível realizar a marcação de ponto."
    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
    prox = "Entrada"
    if len(pontos) == 1: prox = "Ida Almoço"
    elif len(pontos) == 2: prox = "Volta Almoço"
    elif len(pontos) == 3: prox = "Saída"
    elif len(pontos) >= 4: prox = "Extra"
    if request.method == 'POST':
        if bloqueado: flash('Bloqueado'); return redirect(url_for('dashboard'))
        db.session.add(PontoRegistro(user_id=current_user.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=prox, latitude=request.form.get('latitude'), longitude=request.form.get('longitude')))
        db.session.commit(); calcular_dia(current_user.id, hoje)
        return redirect(url_for('dashboard'))
    return render_template('ponto_registro.html', proxima_acao=prox, hoje_extenso=hoje_extenso, pontos=pontos, bloqueado=bloqueado, motivo=motivo)

@app.route('/controle-uniforme')
@login_required
def controle_uniforme(): return render_template('controle_uniforme.html', itens=ItemEstoque.query.all()) if current_user.role == 'Master' else redirect(url_for('dashboard'))
@app.route('/entrada', methods=['GET', 'POST'])
@login_required
def entrada(): 
    if request.method == 'POST': return redirect(url_for('controle_uniforme'))
    return render_template('entrada.html')
@app.route('/saida', methods=['GET', 'POST'])
@login_required
def saida(): 
    if request.method == 'POST': return redirect(url_for('controle_uniforme'))
    return render_template('saida.html', itens=ItemEstoque.query.all())
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
@app.route('/ponto/solicitar-ajuste', methods=['GET', 'POST'])
@login_required
def solicitar_ajuste():
    pontos_dia = []
    data_selecionada = None
    meus_ajustes = PontoAjuste.query.filter_by(user_id=current_user.id).order_by(PontoAjuste.created_at.desc()).limit(20).all()
    if request.method == 'POST':
        if request.form.get('acao') == 'buscar':
            try: data_selecionada = datetime.strptime(request.form.get('data_busca'), '%Y-%m-%d').date(); pontos_dia = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=data_selecionada).order_by(PontoRegistro.hora_registro).all()
            except: flash('Data inválida')
        elif request.form.get('acao') == 'enviar':
            try:
                dt_obj = datetime.strptime(request.form.get('data_ref'), '%Y-%m-%d').date()
                p_id = int(request.form.get('ponto_id')) if request.form.get('ponto_id') else None
                solic = PontoAjuste(user_id=current_user.id, data_referencia=dt_obj, ponto_original_id=p_id, novo_horario=request.form.get('novo_horario'), tipo_batida=request.form.get('tipo_batida'), tipo_solicitacao=request.form.get('tipo_solicitacao'), justificativa=request.form.get('justificativa'))
                db.session.add(solic); db.session.commit(); flash('Enviado!')
                return redirect(url_for('solicitar_ajuste'))
            except: pass
    dados_extras = {{}}
    for p in meus_ajustes:
        if p.ponto_original_id:
            original = PontoRegistro.query.get(p.ponto_original_id)
            if original: dados_extras[p.id] = original.hora_registro.strftime('%H:%M')
    return render_template('solicitar_ajuste.html', pontos=pontos_dia, data_sel=data_selecionada, meus_ajustes=meus_ajustes, extras=dados_extras)
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
                db.session.commit(); calcular_dia(solic.user_id, solic.data_referencia); flash('Aprovado.')
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
"""

# --- TEMPLATE RELATORIO COM BOTAO ZERAR ---
FILE_RELATORIO = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6 flex flex-col md:flex-row justify-between items-center gap-4">
    <h2 class="text-2xl font-bold text-slate-800">Relatório de Folha</h2>
    <form action="/admin/relatorio-folha" method="POST" class="flex gap-2">
        <input type="month" name="mes_ref" value="{{ mes_ref }}" class="border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-600 bg-white">
        <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded-lg font-bold text-sm hover:bg-blue-700 transition">GERAR RELATÓRIO</button>
    </form>
</div>

<!-- BOTAO DE ZERAR FOLHA (PERIGO) -->
<div class="bg-red-50 border border-red-200 rounded-xl p-4 mb-8 flex justify-between items-center">
    <div>
        <h3 class="text-red-800 font-bold text-sm"><i class="fas fa-exclamation-triangle mr-1"></i> Área de Fechamento</h3>
        <p class="text-xs text-red-600">Deseja limpar os saldos calculados deste mês? Isso não apaga os pontos batidos, apenas os cálculos.</p>
    </div>
    <form action="/admin/relatorio-folha/zerar" method="POST">
        <input type="hidden" name="mes_ref" value="{{ mes_ref }}">
        <button type="submit" class="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded-lg text-xs shadow-md transition" onclick="return confirm('ATENÇÃO: Você está prestes a ZERAR todos os saldos calculados de {{ mes_ref }}. Tem certeza?')">
            ZERAR FOLHA DO MÊS
        </button>
    </form>
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <table class="w-full text-left text-sm text-slate-600">
        <thead class="bg-slate-50 text-xs uppercase text-slate-400 font-bold border-b border-slate-100">
            <tr>
                <th class="px-6 py-4">Funcionário</th>
                <th class="px-6 py-4">Salário Base</th>
                <th class="px-6 py-4 text-center">Status Ponto</th>
                <th class="px-6 py-4 text-right">Saldo Horas</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
            {% for item in relatorio %}
            <tr class="hover:bg-slate-50 transition">
                <td class="px-6 py-4 font-bold text-slate-800">{{ item.nome }} <span class="text-xs font-normal text-slate-400 block">{{ item.cargo }}</span></td>
                <td class="px-6 py-4">R$ {{ "%.2f"|format(item.salario) }}</td>
                <td class="px-6 py-4 text-center">
                    <span class="px-2 py-1 rounded text-[10px] font-bold uppercase
                        {% if item.saldo_minutos >= 0 %} bg-emerald-100 text-emerald-700
                        {% else %} bg-red-100 text-red-700 {% endif %}">
                        {{ item.status }}
                    </span>
                </td>
                <td class="px-6 py-4 text-right font-mono font-bold 
                    {% if item.saldo_minutos >= 0 %} text-emerald-600 {% else %} text-red-600 {% endif %}">
                    {{ item.saldo_formatado }}
                </td>
            </tr>
            {% else %}
            <tr><td colspan="4" class="px-6 py-8 text-center text-slate-400">Nenhum dado calculado para o período.</td></tr>
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
        print("\n>>> SUCESSO V36 ZERAR FOLHA! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V36 RESET REPORT: {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    write_file("templates/admin_relatorio_folha.html", FILE_RELATORIO)
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V22: Modulo de Simulacao de Massa (180 Funcionarios) e Salarios"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""
FILE_REQ = """flask\nflask-sqlalchemy\npsycopg2-binary\ngunicorn\nflask-login\nwerkzeug"""
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Com rotas de Geração de Massa) ---
FILE_APP = f"""
import os
import logging
import secrets
import random
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
app.secret_key = 'chave_v22_simulation_secret'

db_url = "{DB_URL_FIXA}"
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app, engine_options={{
    "pool_pre_ping": True,
    "pool_size": 20, # Aumentado para aguentar a geracao em massa
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
    
    # Jornada e Financeiro
    horario_entrada = db.Column(db.String(5), default='07:12')
    horario_almoco_inicio = db.Column(db.String(5), default='12:00')
    horario_almoco_fim = db.Column(db.String(5), default='13:00')
    horario_saida = db.Column(db.String(5), default='17:00')
    salario = db.Column(db.Float, default=2000.00) # Novo campo

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

# --- MIGRACAO FORÇADA (NOVO CAMPO SALARIO) ---
def fix_db():
    with app.app_context():
        db.create_all()
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS horario_entrada VARCHAR(5) DEFAULT '07:12'"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS horario_almoco_inicio VARCHAR(5) DEFAULT '12:00'"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS horario_almoco_fim VARCHAR(5) DEFAULT '13:00'"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS horario_saida VARCHAR(5) DEFAULT '17:00'"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS salario FLOAT DEFAULT 2000.00"))
                conn.commit()
        except: pass
fix_db()

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
    
    m_ent = time_to_min(user.horario_entrada)
    m_alm_ini = time_to_min(user.horario_almoco_inicio)
    m_alm_fim = time_to_min(user.horario_almoco_fim)
    m_sai = time_to_min(user.horario_saida)
    
    jornada_esperada = max(0, m_alm_ini - m_ent) + max(0, m_sai - m_alm_fim)
    if jornada_esperada <= 0: jornada_esperada = 528 # 8h48 (07:12 as 17:00)

    pontos = PontoRegistro.query.filter_by(user_id=user_id, data_registro=data_ref).order_by(PontoRegistro.hora_registro).all()
    trabalhado_minutos = 0
    status = "OK"
    saldo = 0
    
    if len(pontos) < 2:
        if len(pontos) == 0:
            if data_ref.weekday() < 5: 
                status = "Falta"
                saldo = -jornada_esperada
            else:
                status = "Folga"
                saldo = 0
    else:
        loops = len(pontos)
        if loops % 2 != 0: 
            status = "Erro: Ímpar"
            loops -= 1
        
        for i in range(0, loops, 2):
            p_ent = time_to_min(pontos[i].hora_registro)
            p_sai = time_to_min(pontos[i+1].hora_registro)
            trabalhado_minutos += (p_sai - p_ent)
            
        saldo = trabalhado_minutos - jornada_esperada
        
        if abs(saldo) <= 10: saldo = 0; status = "Normal"
        elif saldo > 0: status = "Hora Extra"
        elif saldo < 0: status = "Atraso/Débito"

    resumo = PontoResumo.query.filter_by(user_id=user_id, data_referencia=data_ref).first()
    if not resumo:
        resumo = PontoResumo(user_id=user_id, data_referencia=data_ref)
        db.session.add(resumo)
    
    resumo.minutos_trabalhados = trabalhado_minutos
    resumo.minutos_esperados = jornada_esperada
    resumo.minutos_saldo = saldo
    resumo.status_dia = status
    db.session.commit()

# --- ROTAS DE GERAÇÃO DE MASSA (SIMULAÇÃO) ---

@app.route('/admin/gerar-massa', methods=['POST'])
@login_required
def gerar_massa():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    
    try:
        # 1. Cria usuários até ter 180
        total_users = User.query.count()
        users_to_create = 180 - total_users
        
        # Pega o master para não deletar
        master = User.query.filter_by(username='Thaynara').first()
        
        logger.info(f"Gerando {{users_to_create}} novos usuarios...")
        
        for i in range(total_users, 180):
            nome = f"Colaborador {{i+1:03d}}"
            login = f"colab{{i+1}}"
            salario = random.choice([2000, 2200, 2500, 2800, 3000, 3200, 3500])
            
            if not User.query.filter_by(username=login).first():
                novo = User(
                    username=login, 
                    real_name=nome, 
                    role='Colaborador', 
                    is_first_access=False,
                    salario=salario,
                    horario_entrada='07:12',
                    horario_almoco_inicio='12:00',
                    horario_almoco_fim='13:00',
                    horario_saida='17:00'
                )
                novo.set_password('123456') # Senha padrao teste
                db.session.add(novo)
        
        db.session.commit()
        
        # 2. Gera pontos para o Mês Atual
        hoje = get_brasil_time().date()
        ano = hoje.year
        mes = hoje.month
        num_dias = calendar.monthrange(ano, mes)[1]
        
        todos_users = User.query.filter(User.username != 'Thaynara').all()
        
        logger.info("Gerando pontos diarios...")
        
        # Limites base em minutos
        base_ent = 7*60 + 12 # 07:12
        base_alm_ini = 12*60
        base_alm_fim = 13*60
        base_sai = 17*60
        
        for dia in range(1, num_dias + 1):
            data_atual = date(ano, mes, dia)
            if data_atual.weekday() >= 5: continue # Pula Fim de Semana na geracao
            
            # Para cada usuario, gera o dia
            for u in todos_users:
                # Sorteio do destino do usuario hoje
                chance = random.random() # 0.0 a 1.0
                
                # 5% de falta
                if chance < 0.05: continue 
                
                # Variaveis de tempo (minutos)
                delta_ent = 0
                delta_sai = 0
                
                # 10% Atraso na entrada
                if chance < 0.15: 
                    delta_ent = random.randint(15, 60) # Chegou 15 a 60 min atrasado
                # 80% Normal (Variacao pequena +/- 5 min)
                else:
                    delta_ent = random.randint(-5, 5)
                
                # 5% Hora Extra na saida
                if chance > 0.95:
                    delta_sai = random.randint(30, 120) # Ficou 30 a 120 min a mais
                # 5% Saida Antecipada
                elif chance > 0.90:
                    delta_sai = random.randint(-60, -10) # Saiu antes
                else:
                    delta_sai = random.randint(-5, 5) # Normal
                
                # Converte e Cria Pontos
                # Entrada
                m1 = base_ent + delta_ent
                h1 = time(m1 // 60, m1 % 60)
                db.session.add(PontoRegistro(user_id=u.id, data_registro=data_atual, hora_registro=h1, tipo='Entrada', latitude='Sim', longitude='Sim'))
                
                # Almoco (Fixo para simplificar, com leve variação)
                m2 = base_alm_ini + random.randint(-2, 5)
                h2 = time(m2 // 60, m2 % 60)
                db.session.add(PontoRegistro(user_id=u.id, data_registro=data_atual, hora_registro=h2, tipo='Ida Almoço', latitude='Sim', longitude='Sim'))
                
                m3 = base_alm_fim + random.randint(0, 5) # As vezes volta atrasado do almoco
                h3 = time(m3 // 60, m3 % 60)
                db.session.add(PontoRegistro(user_id=u.id, data_registro=data_atual, hora_registro=h3, tipo='Volta Almoço', latitude='Sim', longitude='Sim'))
                
                # Saida
                m4 = base_sai + delta_sai
                h4 = time(m4 // 60, m4 % 60)
                db.session.add(PontoRegistro(user_id=u.id, data_registro=data_atual, hora_registro=h4, tipo='Saída', latitude='Sim', longitude='Sim'))
                
                # Commit a cada dia/usuario para nao estourar memoria? 
                # Melhor fazer em blocos. Vamos deixar o SQLAlchemy gerenciar a sessao, mas flushar.
            
            db.session.commit()
            
            # Calcular os dias gerados
            for u in todos_users:
                calcular_dia(u.id, data_atual)
                
        flash(f'Simulação Concluída! 180 Usuários e Pontos de {{mes}}/{{ano}} gerados.')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro simulacao: {{e}}")
        flash(f'Erro na simulação: {{e}}')
        
    return redirect(url_for('admin_relatorio_folha'))

@app.route('/admin/limpar-massa', methods=['POST'])
@login_required
def limpar_massa():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    try:
        # Apaga registros de quem não é Master
        ids_users = [u.id for u in User.query.filter(User.username != 'Thaynara').all()]
        
        if ids_users:
            # Delete em massa via SQL Core para performance
            stmt1 = PontoRegistro.__table__.delete().where(PontoRegistro.user_id.in_(ids_users))
            db.session.execute(stmt1)
            
            stmt2 = PontoResumo.__table__.delete().where(PontoResumo.user_id.in_(ids_users))
            db.session.execute(stmt2)
            
            stmt3 = PontoAjuste.__table__.delete().where(PontoAjuste.user_id.in_(ids_users))
            db.session.execute(stmt3)
            
            stmt4 = User.__table__.delete().where(User.id.in_(ids_users))
            db.session.execute(stmt4)
            
            db.session.commit()
            flash('Dados de simulação limpos com sucesso.')
        else:
            flash('Nada para limpar.')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao limpar: {{e}}')
        
    return redirect(url_for('admin_relatorio_folha'))

# --- ROTAS NORMAIS (Mantidas) ---
try:
    with app.app_context():
        if not User.query.filter_by(username='Thaynara').first():
            m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False); m.set_password('1855'); db.session.add(m); db.session.commit()
except: pass

@app.route('/admin/relatorio-folha', methods=['GET', 'POST'])
@login_required
def admin_relatorio_folha():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    mes_ref = request.form.get('mes_ref') or datetime.now().strftime('%Y-%m')
    users = User.query.all()
    relatorio = []
    ano, mes = map(int, mes_ref.split('-'))
    for u in users:
        resumos = PontoResumo.query.filter(PontoResumo.user_id == u.id, func.extract('year', PontoResumo.data_referencia) == ano, func.extract('month', PontoResumo.data_referencia) == mes).all()
        total_saldo = sum(r.minutos_saldo for r in resumos)
        sinal = "+" if total_saldo >= 0 else "-"
        abs_s = abs(total_saldo)
        relatorio.append({{'nome': u.real_name, 'cargo': u.role, 'salario': u.salario, 'saldo_minutos': total_saldo, 'saldo_formatado': f"{{sinal}}{{abs_s // 60:02d}}:{{abs_s % 60:02d}}", 'status': 'Crédito' if total_saldo >= 0 else 'Débito'}})
    return render_template('admin_relatorio_folha.html', relatorio=relatorio, mes_ref=mes_ref)

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
        db.session.add(novo); db.session.commit(); calcular_dia(current_user.id, hoje)
        return redirect(url_for('dashboard'))
    return render_template('ponto_registro.html', proxima_acao=proxima, hoje=hoje, pontos=pontos_hoje)

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
            user.real_name = request.form.get('real_name'); user.username = request.form.get('username')
            user.horario_entrada = request.form.get('h_ent') or '07:12'; user.horario_almoco_inicio = request.form.get('h_alm_ini') or '12:00'; user.horario_almoco_fim = request.form.get('h_alm_fim') or '13:00'; user.horario_saida = request.form.get('h_sai') or '17:00'
            user.salario = float(request.form.get('salario') or 2000)
            if user.username != 'Thaynara': user.role = request.form.get('role')
            db.session.commit(); calcular_dia(user.id, get_brasil_time().date()); return redirect(url_for('gerenciar_usuarios'))
    return render_template('editar_usuario.html', user=user)

# Rotas de Login e Dashboard mantidas iguais...
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

@app.route('/ponto/espelho')
@login_required
def espelho_ponto():
    data_filtro = request.args.get('data_filtro')
    query = PontoRegistro.query
    if current_user.role != 'Master': query = query.filter_by(user_id=current_user.id)
    if data_filtro:
        try: query = query.filter_by(data_registro=datetime.strptime(data_filtro, '%Y-%m-%d').date())
        except: pass
    if current_user.role == 'Master':
        registros_raw = query.join(User).order_by(PontoRegistro.data_registro.desc(), User.real_name, PontoRegistro.hora_registro).limit(1000).all()
        espelho_agrupado = {{}} 
        for r in registros_raw:
            chave = f"{{r.data_registro}}_{{r.user_id}}"
            if chave not in espelho_agrupado:
                resumo = PontoResumo.query.filter_by(user_id=r.user_id, data_referencia=r.data_registro).first()
                saldo_fmt = "--:--"
                status_dia = ""
                if resumo:
                    abs_s = abs(resumo.minutos_saldo)
                    sinal = "+" if resumo.minutos_saldo >= 0 else "-"
                    saldo_fmt = f"{{sinal}}{{abs_s // 60:02d}}:{{abs_s % 60:02d}}"
                    status_dia = resumo.status_dia
                espelho_agrupado[chave] = {{'user': r.user, 'data': r.data_registro, 'pontos': [], 'saldo': saldo_fmt, 'status': status_dia}}
            espelho_agrupado[chave]['pontos'].append(r)
        return render_template('ponto_espelho_master.html', grupos=espelho_agrupado.values(), filtro_data=data_filtro)
    else:
        registros = query.order_by(PontoRegistro.data_registro.desc(), PontoRegistro.hora_registro.desc()).limit(100).all()
        dias_agrupados = {{}}
        for r in registros:
            d = r.data_registro
            if d not in dias_agrupados:
                resumo = PontoResumo.query.filter_by(user_id=current_user.id, data_referencia=d).first()
                saldo_fmt = "--:--"
                if resumo:
                    abs_s = abs(resumo.minutos_saldo)
                    sinal = "+" if resumo.minutos_saldo >= 0 else "-"
                    saldo_fmt = f"{{sinal}}{{abs_s // 60:02d}}:{{abs_s % 60:02d}}"
                dias_agrupados[d] = {{'data': d, 'pontos': [], 'saldo': saldo_fmt}}
            dias_agrupados[d]['pontos'].append(r)
        return render_template('ponto_espelho.html', dias=dias_agrupados.values(), filtro_data=data_filtro)

@app.route('/admin/usuarios')
@login_required
def admin_usuarios_list(): return render_template('admin_usuarios.html', users=User.query.all()) if current_user.role == 'Master' else redirect(url_for('dashboard'))

@app.route('/admin/usuarios/novo', methods=['GET', 'POST'])
@login_required
def novo_usuario(): 
    if request.method == 'POST':
        uname = request.form.get('username')
        if User.query.filter_by(username=uname).first(): flash('Existe.')
        else:
            senha = secrets.token_hex(3)
            novo = User(username=uname, real_name=request.form.get('real_name'), role=request.form.get('role'), is_first_access=True, horario_entrada=request.form.get('h_ent'), horario_almoco_inicio=request.form.get('h_alm_ini'), horario_almoco_fim=request.form.get('h_alm_fim'), horario_saida=request.form.get('h_sai'))
            novo.set_password(senha); db.session.add(novo); db.session.commit()
            return render_template('sucesso_usuario.html', novo_user=uname, senha_gerada=senha)
    return render_template('novo_usuario.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
"""

# --- RELATORIO FOLHA (COM BOTÕES DE SIMULAÇÃO) ---
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

<!-- PAINEL DE SIMULAÇÃO (MASTER ONLY) -->
<div class="bg-indigo-50 border border-indigo-200 rounded-xl p-6 mb-8">
    <h3 class="text-indigo-800 font-bold mb-2 flex items-center gap-2"><i class="fas fa-flask"></i> Laboratório de Testes</h3>
    <p class="text-xs text-indigo-600 mb-4">Ferramentas para gerar dados fictícios em massa. Use com cuidado.</p>
    <div class="flex gap-4">
        <form action="/admin/gerar-massa" method="POST">
            <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 px-6 rounded-lg text-sm shadow-md transition" onclick="return confirm('Isso criará até 180 usuários e milhares de pontos. Pode levar alguns segundos. Continuar?')">
                <i class="fas fa-magic mr-2"></i> GERAR MASSA DE DADOS
            </button>
        </form>
        <form action="/admin/limpar-massa" method="POST">
            <button type="submit" class="bg-red-500 hover:bg-red-600 text-white font-bold py-2 px-6 rounded-lg text-sm shadow-md transition" onclick="return confirm('ATENÇÃO: Isso apagará TODOS os dados gerados (exceto o Master). Tem certeza absoluta?')">
                <i class="fas fa-trash mr-2"></i> LIMPAR TUDO
            </button>
        </form>
    </div>
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
            <tr><td colspan="4" class="px-6 py-8 text-center text-slate-400">Nenhum dado para o período selecionado.</td></tr>
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
        print("\n>>> SUCESSO V22 SIMULATION! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V22 SIMULATION: {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    write_file("templates/admin_relatorio_folha.html", FILE_RELATORIO) # Com botoes de massa
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



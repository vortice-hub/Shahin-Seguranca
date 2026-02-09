import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V26: Implementacao de Escala Rigida (12x36 e 5x2) com Bloqueio"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""
FILE_REQ = """flask\nflask-sqlalchemy\npsycopg2-binary\ngunicorn\nflask-login\nwerkzeug"""
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Lógica de Bloqueio de Escala) ---
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
app.secret_key = 'chave_v26_rigid_secret'

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
    
    # Jornada
    horario_entrada = db.Column(db.String(5), default='08:00')
    horario_almoco_inicio = db.Column(db.String(5), default='12:00')
    horario_almoco_fim = db.Column(db.String(5), default='13:00')
    horario_saida = db.Column(db.String(5), default='17:00')
    salario = db.Column(db.Float, default=2000.00)
    
    # Escala (NOVOS CAMPOS)
    escala = db.Column(db.String(20), default='Livre') # Livre, 5x2, 12x36
    data_inicio_escala = db.Column(db.Date, nullable=True) # Marco zero para 12x36

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
    
    # Verifica Escala para definir Meta do Dia
    dia_trabalho = True
    
    if user.escala == '5x2':
        # 0=Seg, 4=Sex, 5=Sab, 6=Dom
        if data_ref.weekday() >= 5: 
            dia_trabalho = False
            
    elif user.escala == '12x36' and user.data_inicio_escala:
        delta = (data_ref - user.data_inicio_escala).days
        if delta % 2 != 0: # Impar = Folga
            dia_trabalho = False
            
    # Calculo da Meta
    if dia_trabalho:
        m_ent = time_to_min(user.horario_entrada)
        m_alm_ini = time_to_min(user.horario_almoco_inicio)
        m_alm_fim = time_to_min(user.horario_almoco_fim)
        m_sai = time_to_min(user.horario_saida)
        jornada_esperada = max(0, m_alm_ini - m_ent) + max(0, m_sai - m_alm_fim)
        if jornada_esperada <= 0: jornada_esperada = 480
    else:
        jornada_esperada = 0 # Dia de folga meta é zero

    pontos = PontoRegistro.query.filter_by(user_id=user_id, data_registro=data_ref).order_by(PontoRegistro.hora_registro).all()
    trabalhado_minutos = 0
    status = "OK"
    saldo = 0
    
    if len(pontos) < 2:
        if len(pontos) == 0:
            if dia_trabalho: 
                status = "Falta"
                saldo = -jornada_esperada
            else:
                status = "Folga"
                saldo = 0
        # Se tem 1 ponto so, e erro impar
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
        
        # Se for dia de folga e trabalhou, é 100% extra
        if not dia_trabalho and trabalhado_minutos > 0:
            status = "Hora Extra (Folga)"
            saldo = trabalhado_minutos # Tudo é saldo positivo
        else:
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

# --- BOOT COM MIGRACAO ---
def check_db():
    with app.app_context():
        db.create_all()
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS escala VARCHAR(20) DEFAULT 'Livre'"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS data_inicio_escala DATE"))
                conn.commit()
        except: pass
        if not User.query.filter_by(username='Thaynara').first():
            m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False); m.set_password('1855'); db.session.add(m); db.session.commit()
check_db()

# --- ROTAS PONTO COM BLOQUEIO RÍGIDO ---

@app.route('/ponto/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    hoje = get_brasil_time().date()
    
    # --- VERIFICAÇÃO DE ESCALA RÍGIDA ---
    bloqueado = False
    motivo_bloqueio = ""
    
    if current_user.escala == '5x2':
        # 5=Sabado, 6=Domingo
        if hoje.weekday() >= 5:
            bloqueado = True
            motivo_bloqueio = "Escala 5x2: Fim de Semana (Folga)"
            
    elif current_user.escala == '12x36' and current_user.data_inicio_escala:
        dias_passados = (hoje - current_user.data_inicio_escala).days
        # Se dias_passados for impar (1, 3, 5...), é dia de folga
        # Ex: Dia 0 (Trab), Dia 1 (Folga), Dia 2 (Trab)
        if dias_passados % 2 != 0:
            bloqueado = True
            motivo_bloqueio = "Escala 12x36: Dia de Folga Calculado"

    pontos_hoje = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
    proxima = "Entrada"
    if len(pontos_hoje) == 1: proxima = "Ida Almoço"
    elif len(pontos_hoje) == 2: proxima = "Volta Almoço"
    elif len(pontos_hoje) == 3: proxima = "Saída"
    elif len(pontos_hoje) >= 4: proxima = "Extra"

    if request.method == 'POST':
        # Dupla checagem no server side para evitar burla
        if bloqueado:
            flash(f'AÇÃO BLOQUEADA: {{motivo_bloqueio}}', 'error')
            return redirect(url_for('dashboard'))
            
        lat, lon = request.form.get('latitude'), request.form.get('longitude')
        novo = PontoRegistro(user_id=current_user.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=proxima, latitude=lat, longitude=lon)
        db.session.add(novo)
        db.session.commit()
        calcular_dia(current_user.id, hoje)
        return redirect(url_for('dashboard'))
        
    return render_template('ponto_registro.html', proxima_acao=proxima, hoje=hoje, pontos=pontos_hoje, bloqueado=bloqueado, motivo=motivo_bloqueio)

# --- ROTAS ADMIN USUARIOS (ATUALIZADA COM ESCALA) ---

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
            # Tratamento da data de inicio escala
            dt_escala = None
            if request.form.get('dt_escala'):
                dt_escala = datetime.strptime(request.form.get('dt_escala'), '%Y-%m-%d').date()
                
            novo = User(username=username, 
                       real_name=request.form.get('real_name'), 
                       role=request.form.get('role'),
                       is_first_access=True,
                       horario_entrada=request.form.get('h_ent') or '08:00',
                       horario_almoco_inicio=request.form.get('h_alm_ini') or '12:00',
                       horario_almoco_fim=request.form.get('h_alm_fim') or '13:00',
                       horario_saida=request.form.get('h_sai') or '17:00',
                       escala=request.form.get('escala'),
                       data_inicio_escala=dt_escala
                       )
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
        try:
            acao = request.form.get('acao')
            if acao == 'excluir':
                if user.username == 'Thaynara': flash('Erro master.')
                else: db.session.delete(user); db.session.commit(); flash('Excluido.')
                return redirect(url_for('gerenciar_usuarios'))
            elif acao == 'resetar_senha':
                nova = secrets.token_hex(3); user.set_password(nova); user.is_first_access = True; db.session.commit(); flash(f'Senha: {{nova}}'); return redirect(url_for('editar_usuario', id=id))
            else:
                user.real_name = request.form.get('real_name')
                user.username = request.form.get('username')
                if user.username != 'Thaynara': user.role = request.form.get('role')
                
                user.horario_entrada = request.form.get('h_ent') or '08:00'
                user.horario_almoco_inicio = request.form.get('h_alm_ini') or '12:00'
                user.horario_almoco_fim = request.form.get('h_alm_fim') or '13:00'
                user.horario_saida = request.form.get('h_sai') or '17:00'
                user.salario = float(request.form.get('salario') or 0)
                
                # Atualizacao de Escala
                user.escala = request.form.get('escala')
                if request.form.get('dt_escala'):
                    user.data_inicio_escala = datetime.strptime(request.form.get('dt_escala'), '%Y-%m-%d').date()
                
                db.session.commit()
                flash('Atualizado com sucesso.')
                return redirect(url_for('gerenciar_usuarios'))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro: {{e}}")
            return redirect(url_for('editar_usuario', id=id))
            
    return render_template('editar_usuario.html', user=user)

# --- ROTAS MANTIDAS ---
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
def gerenciar_usuarios(): return render_template('admin_usuarios.html', users=User.query.all()) if current_user.role == 'Master' else redirect(url_for('dashboard'))

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
        relatorio.append({{'nome': u.real_name, 'cargo': u.role, 'saldo_minutos': total_saldo, 'saldo_formatado': f"{{sinal}}{{abs_s // 60:02d}}:{{abs_s % 60:02d}}", 'status': 'Crédito' if total_saldo >= 0 else 'Débito'}})
    return render_template('admin_relatorio_folha.html', relatorio=relatorio, mes_ref=mes_ref)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
"""

# --- BASE (FLASH CATEGORIES) ---
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
        function toggleDetails(id) { document.getElementById(id).classList.toggle('hidden'); }
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
                    <li><a href="/admin/relatorio-folha" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-file-invoice-dollar w-6 text-center mr-2 text-slate-500 group-hover:text-emerald-400"></i><span class="font-medium">Relatório de Folha</span></a></li>
                    <li><a href="/controle-uniforme" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-tshirt w-6 text-center mr-2 text-slate-500 group-hover:text-yellow-500"></i><span class="font-medium">Controle de Uniforme</span></a></li>
                    <li><a href="/admin/solicitacoes" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-check-double w-6 text-center mr-2 text-slate-500 group-hover:text-emerald-500"></i><span class="font-medium">Solicitações de Ponto</span></a></li>
                    <li><a href="/admin/usuarios" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-users-cog w-6 text-center mr-2 text-blue-400"></i><span class="font-medium">Funcionários</span></a></li>
                    {% endif %}
                    <li><a href="/logout" class="flex items-center px-6 py-3 hover:bg-red-900/20 hover:text-red-400 transition group mt-8"><i class="fas fa-sign-out-alt w-6 text-center mr-2 text-slate-500 group-hover:text-red-400"></i><span class="font-medium">Sair</span></a></li>
                </ul>
            </nav>
        </aside>
        {% endif %}
        <div class="flex-1 h-full overflow-y-auto bg-slate-50 relative w-full">
            <div class="max-w-5xl mx-auto p-4 md:p-8 pb-20">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="mb-6 p-4 rounded-lg text-sm font-medium shadow-sm flex items-center gap-3 animate-fade-in 
                                {% if category == 'error' %} bg-red-100 border border-red-200 text-red-700 
                                {% else %} bg-blue-50 border border-blue-100 text-blue-700 {% endif %}">
                                <i class="fas {% if category == 'error' %}fa-exclamation-circle{% else %}fa-info-circle{% endif %} text-lg"></i> {{ message }}
                            </div>
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

# --- REGISTRO PONTO (VISUAL BLOQUEIO) ---
FILE_PONTO_REGISTRO = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-md mx-auto text-center">
    <div class="mb-8"><h2 class="text-2xl font-bold text-slate-800">Registrar Ponto</h2><p class="text-sm text-slate-500">Confirme sua localização.</p></div>

    {% if bloqueado %}
    <div class="bg-red-50 border-l-4 border-red-500 p-6 rounded-r-xl shadow-md text-left mb-8">
        <h3 class="text-lg font-bold text-red-700 flex items-center gap-2"><i class="fas fa-ban"></i> AÇÃO BLOQUEADA</h3>
        <p class="text-sm text-red-600 mt-2">{{ motivo }}</p>
        <p class="text-xs text-red-500 mt-4 italic">Se você está trabalhando em dia de folga (Extraordinário), solicite o ajuste manualmente após o expediente.</p>
    </div>
    {% else %}
    <div class="bg-slate-900 text-white rounded-2xl p-8 shadow-2xl mb-8 border border-slate-700 relative overflow-hidden">
        <div class="text-5xl font-mono font-bold tracking-widest mb-2" id="relogio">--:--:--</div>
        <div class="text-sm text-slate-400 uppercase tracking-widest">{{ hoje.strftime('%d de %B de %Y') }}</div>
        <div class="mt-6 inline-block bg-blue-600 text-xs font-bold px-4 py-1 rounded-full uppercase tracking-wide shadow-lg">Próximo: {{ proxima_acao }}</div>
    </div>
    <form action="/ponto/registrar" method="POST" id="formPonto">
        <input type="hidden" name="latitude" id="lat"><input type="hidden" name="longitude" id="lon">
        <button type="button" onclick="getLocationAndSubmit()" id="btnRegistrar" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-5 rounded-xl shadow-xl transition transform active:scale-95 flex items-center justify-center gap-3 text-lg"><i class="fas fa-fingerprint text-2xl"></i> REGISTRAR</button>
        <p id="geoStatus" class="text-xs text-slate-400 mt-4 h-4"></p>
    </form>
    {% endif %}

    <div class="mt-8 text-left">
        <h3 class="text-xs font-bold text-slate-400 uppercase mb-3 ml-1">Histórico de Hoje</h3>
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden divide-y divide-slate-100">
            {% for p in pontos %}
            <div class="px-4 py-3 flex justify-between items-center"><span class="text-sm font-bold text-slate-700">{{ p.tipo }}</span><span class="text-sm font-mono text-slate-500">{{ p.hora_registro.strftime('%H:%M') }}</span></div>
            {% else %}<div class="p-4 text-center text-xs text-slate-400">Nenhum registro hoje.</div>{% endfor %}
        </div>
    </div>
</div>
<script>
    function updateTime() { document.getElementById('relogio').innerText = new Date().toLocaleTimeString('pt-BR'); }
    setInterval(updateTime, 1000); updateTime();
    function getLocationAndSubmit() {
        const btn = document.getElementById('btnRegistrar');
        const st = document.getElementById('geoStatus');
        btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Obtendo...';
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (p) => { document.getElementById('lat').value = p.coords.latitude; document.getElementById('lon').value = p.coords.longitude; document.getElementById('formPonto').submit(); },
                (e) => { alert("Erro GPS."); btn.disabled = false; btn.innerHTML = 'TENTAR NOVAMENTE'; }
            );
        } else alert("Sem suporte GPS.");
    }
</script>
{% endblock %}
"""

# --- NOVO USUARIO (COM CAMPOS ESCALA) ---
FILE_NOVO_USUARIO = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-lg mx-auto">
    <div class="flex items-center justify-between mb-6"><h2 class="text-lg font-bold text-slate-800">Novo Cadastro</h2><a href="/admin/usuarios" class="text-xs font-medium text-slate-500 hover:text-slate-800">Cancelar</a></div>
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <form action="/admin/usuarios/novo" method="POST" class="p-8 space-y-6">
            <div class="space-y-4">
                <div><label class="label-pro">Nome</label><input type="text" name="real_name" class="input-pro" required></div>
                <div><label class="label-pro">Login</label><input type="text" name="username" class="input-pro" required></div>
                <div><label class="label-pro">Cargo</label><input type="text" name="role" class="input-pro" required></div>
            </div>
            <div class="pt-4 border-t border-slate-100">
                <p class="text-xs font-bold text-slate-400 uppercase mb-3">Escala e Jornada</p>
                <div class="mb-4">
                    <label class="label-pro">Tipo de Escala</label>
                    <select name="escala" class="input-pro" onchange="toggleDtRef(this)">
                        <option value="Livre">Livre (Sem Bloqueio)</option>
                        <option value="5x2">Normal 5x2 (Seg-Sex)</option>
                        <option value="12x36">Plantão 12x36</option>
                    </select>
                </div>
                <div id="divDtRef" class="hidden mb-4 bg-blue-50 p-3 rounded border border-blue-100">
                    <label class="label-pro text-blue-700">Data de Referência (Dia Trabalhado)</label>
                    <input type="date" name="dt_escala" class="input-pro">
                    <p class="text-[10px] text-blue-600 mt-1">Escolha um dia que ele TRABALHA para calcular a alternância.</p>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div><label class="label-pro">Entrada</label><input type="time" name="h_ent" value="08:00" class="input-pro"></div>
                    <div><label class="label-pro">Saída Almoço</label><input type="time" name="h_alm_ini" value="12:00" class="input-pro"></div>
                    <div><label class="label-pro">Volta Almoço</label><input type="time" name="h_alm_fim" value="13:00" class="input-pro"></div>
                    <div><label class="label-pro">Saída</label><input type="time" name="h_sai" value="17:00" class="input-pro"></div>
                </div>
            </div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-lg shadow-md transition">CRIAR ACESSO</button>
        </form>
    </div>
</div>
<script>
    function toggleDtRef(sel) {
        if (sel.value === '12x36') document.getElementById('divDtRef').classList.remove('hidden');
        else document.getElementById('divDtRef').classList.add('hidden');
    }
</script>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; outline: none; }</style>
{% endblock %}
"""

# --- EDITAR USUARIO (COM CAMPOS ESCALA) ---
FILE_EDITAR_USUARIO = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-lg mx-auto">
    <div class="flex items-center justify-between mb-6"><h2 class="text-lg font-bold text-slate-800">Editar</h2><a href="/admin/usuarios" class="text-xs font-medium text-slate-500 hover:text-slate-800">Cancelar</a></div>
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <form action="/admin/usuarios/editar/{{ user.id }}" method="POST" class="p-8 space-y-6">
            <div class="space-y-4">
                <div><label class="label-pro">Nome</label><input type="text" name="real_name" value="{{ user.real_name }}" class="input-pro"></div>
                <div><label class="label-pro">Login</label><input type="text" name="username" value="{{ user.username }}" class="input-pro" {% if user.username == 'Thaynara' %}readonly{% endif %}></div>
                <div><label class="label-pro">Cargo</label><input type="text" name="role" value="{{ user.role }}" class="input-pro" {% if user.username == 'Thaynara' %}disabled{% endif %}></div>
                <div><label class="label-pro">Salário</label><input type="number" step="0.01" name="salario" value="{{ user.salario }}" class="input-pro"></div>
            </div>
            <div class="pt-4 border-t border-slate-100">
                <p class="text-xs font-bold text-slate-400 uppercase mb-3">Escala e Jornada</p>
                <div class="mb-4">
                    <label class="label-pro">Tipo de Escala</label>
                    <select name="escala" class="input-pro" onchange="toggleDtRef(this)">
                        <option value="Livre" {% if user.escala == 'Livre' %}selected{% endif %}>Livre</option>
                        <option value="5x2" {% if user.escala == '5x2' %}selected{% endif %}>Normal 5x2</option>
                        <option value="12x36" {% if user.escala == '12x36' %}selected{% endif %}>Plantão 12x36</option>
                    </select>
                </div>
                <div id="divDtRef" class="{% if user.escala != '12x36' %}hidden{% endif %} mb-4 bg-blue-50 p-3 rounded border border-blue-100">
                    <label class="label-pro text-blue-700">Data Ref (Trabalho)</label>
                    <input type="date" name="dt_escala" value="{{ user.data_inicio_escala }}" class="input-pro">
                </div>
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
                    <button type="submit" name="acao" value="resetar_senha" class="bg-yellow-50 hover:bg-yellow-100 text-yellow-700 font-bold py-3 rounded-lg text-xs border border-yellow-200">RESETAR SENHA</button>
                    {% if user.username != 'Thaynara' %}<button type="submit" name="acao" value="excluir" class="bg-red-50 hover:bg-red-100 text-red-600 font-bold py-3 rounded-lg text-xs border border-red-200" onclick="return confirm('Excluir?')">EXCLUIR</button>{% endif %}
                </div>
            </div>
        </form>
    </div>
</div>
<script>function toggleDtRef(s){if(s.value==='12x36')document.getElementById('divDtRef').classList.remove('hidden');else document.getElementById('divDtRef').classList.add('hidden');}</script>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; outline: none; }</style>
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
        print("\n>>> SUCESSO V26 RIGID SCHEDULE! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V26 ESCALA RIGIDA: {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    
    write_file("templates/base.html", FILE_BASE) # Flash error styles
    write_file("templates/ponto_registro.html", FILE_PONTO_REGISTRO) # Bloqueio visual
    write_file("templates/novo_usuario.html", FILE_NOVO_USUARIO) # Campos novos
    write_file("templates/editar_usuario.html", FILE_EDITAR_USUARIO) # Campos novos
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



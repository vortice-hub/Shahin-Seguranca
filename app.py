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
db_url = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app, engine_options={
    "pool_pre_ping": True,
    "pool_size": 10,
    "pool_recycle": 300,
})

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
    dados_extras = {}
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
        espelho_agrupado = {} 
        for r in registros_raw:
            chave = f"{r.data_registro}_{r.user_id}"
            if chave not in espelho_agrupado: espelho_agrupado[chave] = {'user': r.user, 'data': r.data_registro, 'pontos': []}
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
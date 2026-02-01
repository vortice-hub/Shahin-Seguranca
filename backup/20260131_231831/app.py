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
        flash(f'Ponto registrado: {proxima_acao} às {novo_ponto.hora_registro.strftime("%H:%M")}')
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
            flash(f'Senha resetada: {nova}')
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
            db.session.add(HistoricoEntrada(item_nome=f"{nome} ({request.form.get('genero')}-{request.form.get('tamanho')})", quantidade=qtd, data_hora=get_brasil_time()))
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
import os
import logging
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'chave_v10_auth_super_secreta'

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

# --- CONFIGURAÇÃO DE LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Se não estiver logado, manda pra cá

def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

# --- MODELOS ---

# Novo Modelo de Usuário
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    real_name = db.Column(db.String(100))
    role = db.Column(db.String(50)) # Ex: Master, Almoxarife, RH
    is_first_access = db.Column(db.Boolean, default=True) # Obriga troca de senha
    created_at = db.Column(db.DateTime, default=get_brasil_time)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

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

# --- BOOT & GENESIS (Criação do Master) ---
try:
    with app.app_context():
        db.create_all()
        # Verifica se o Master existe, se não, cria.
        if not User.query.filter_by(username='Thaynara').first():
            master = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
            master.set_password('1855')
            db.session.add(master)
            db.session.commit()
            logger.info("Usuario Master Thaynara criado.")
except Exception as e: 
    logger.error(f"Erro Boot: {e}")

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            # Se for primeiro acesso, força troca de senha
            if user.is_first_access:
                return redirect(url_for('primeiro_acesso'))
            return redirect(url_for('dashboard'))
        else:
            flash('Usuário ou senha incorretos.')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.')
    return redirect(url_for('login'))

@app.route('/primeiro-acesso', methods=['GET', 'POST'])
@login_required
def primeiro_acesso():
    if not current_user.is_first_access:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        confirmacao = request.form.get('confirmacao')
        
        if nova_senha == confirmacao:
            current_user.set_password(nova_senha)
            current_user.is_first_access = False
            db.session.commit()
            flash('Senha atualizada com sucesso! Bem-vindo.')
            return redirect(url_for('dashboard'))
        else:
            flash('As senhas não coincidem.')
            
    return render_template('primeiro_acesso.html')

# --- ROTAS DE GESTÃO DE USUÁRIOS (MASTER) ---

@app.route('/admin/usuarios', methods=['GET', 'POST'])
@login_required
def gerenciar_usuarios():
    # Apenas Master (Thaynara) ou quem tiver role Master pode acessar
    if current_user.role != 'Master':
        flash('Acesso negado. Apenas Master.')
        return redirect(url_for('dashboard'))
        
    senha_gerada = None
    novo_usuario_nome = None
    
    if request.method == 'POST':
        # Criar novo usuário
        username = request.form.get('username')
        real_name = request.form.get('real_name')
        role = request.form.get('role')
        
        if User.query.filter_by(username=username).first():
            flash('Erro: Nome de usuário já existe.')
        else:
            # Gera senha aleatoria de 6 digitos
            senha_temp = secrets.token_hex(3) 
            
            novo_user = User(username=username, real_name=real_name, role=role, is_first_access=True)
            novo_user.set_password(senha_temp)
            db.session.add(novo_user)
            db.session.commit()
            
            senha_gerada = senha_temp
            novo_usuario_nome = username
            flash(f'Usuário criado!')

    users = User.query.all()
    return render_template('admin_usuarios.html', users=users, senha_gerada=senha_gerada, novo_user=novo_usuario_nome)

# --- ROTAS PRINCIPAIS (PROTEGIDAS) ---

@app.route('/')
@login_required
def dashboard():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    
    try:
        itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
        total_pecas = sum(i.quantidade for i in itens)
        total_itens = len(itens)
        return render_template('dashboard.html', itens=itens, total_pecas=total_pecas, total_itens=total_itens)
    except Exception as e:
        return f"Erro DB: {e}", 500

@app.route('/entrada', methods=['GET', 'POST'])
@login_required
def entrada():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            tamanho = request.form.get('tamanho')
            genero = request.form.get('genero')
            quantidade = int(request.form.get('quantidade') or 1)
            est_min = int(request.form.get('estoque_minimo') or 5)
            est_ideal = int(request.form.get('estoque_ideal') or 20)
            
            item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
            if item:
                item.quantidade += quantidade
                item.estoque_minimo = est_min
                item.estoque_ideal = est_ideal
                item.data_atualizacao = get_brasil_time()
                flash(f'Estoque atualizado: {nome}')
            else:
                novo = ItemEstoque(nome=nome, tamanho=tamanho, genero=genero, quantidade=quantidade, estoque_minimo=est_min, estoque_ideal=est_ideal)
                novo.data_atualizacao = get_brasil_time()
                db.session.add(novo)
                flash(f'Novo item cadastrado: {nome}')
            
            log = HistoricoEntrada(item_nome=f"{nome} ({genero}-{tamanho})", quantidade=quantidade)
            db.session.add(log)
            db.session.commit()
            return redirect(url_for('entrada'))
        except Exception as e:
            db.session.rollback()
            return f"Erro: {e}", 500
    return render_template('entrada.html')

@app.route('/saida', methods=['GET', 'POST'])
@login_required
def saida():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
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
        return f"Erro: {e}", 500

@app.route('/gerenciar/selecao', methods=['GET', 'POST'])
@login_required
def selecionar_edicao():
    if current_user.is_first_access: return redirect(url_for('primeiro_acesso'))
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        if item_id: return redirect(url_for('editar_item', id=item_id))
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('selecionar_edicao.html', itens=itens)

@app.route('/gerenciar/item/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_item(id):
    item = ItemEstoque.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            db.session.delete(item)
            db.session.commit()
            flash('Item excluído.')
            return redirect(url_for('dashboard'))
        item.nome = request.form.get('nome')
        item.tamanho = request.form.get('tamanho')
        item.genero = request.form.get('genero')
        item.quantidade = int(request.form.get('quantidade'))
        item.estoque_minimo = int(request.form.get('estoque_minimo'))
        item.estoque_ideal = int(request.form.get('estoque_ideal'))
        item.data_atualizacao = get_brasil_time()
        db.session.commit()
        flash('Item atualizado.')
        return redirect(url_for('dashboard'))
    return render_template('editar_item.html', item=item)

@app.route('/historico/entrada')
@login_required
def view_historico_entrada():
    logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all()
    return render_template('historico_entrada.html', logs=logs)

@app.route('/historico/entrada/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_historico_entrada(id):
    log = HistoricoEntrada.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            db.session.delete(log)
            db.session.commit()
            flash('Registro excluído.')
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
@login_required
def view_historico_saida():
    logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all()
    return render_template('historico_saida.html', logs=logs)

@app.route('/historico/saida/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_historico_saida(id):
    log = HistoricoSaida.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            db.session.delete(log)
            db.session.commit()
            flash('Registro excluído.')
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
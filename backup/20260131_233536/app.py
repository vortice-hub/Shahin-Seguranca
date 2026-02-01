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
            db.session.add(HistoricoEntrada(item_nome=f"{nome} ({request.form.get('genero')}-{request.form.get('tamanho')})", quantidade=qtd, data_hora=get_brasil_time()))
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
        espelho_agrupado = {} # Chave: "YYYY-MM-DD_user_id", Valor: {'user': user_obj, 'data': date, 'pontos': []}
        
        for r in registros_raw:
            chave = f"{r.data_registro}_{r.user_id}"
            if chave not in espelho_agrupado:
                espelho_agrupado[chave] = {
                    'user': r.user,
                    'data': r.data_registro,
                    'pontos': []
                }
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
            nova = secrets.token_hex(3); user.set_password(nova); user.is_first_access = True; db.session.commit(); flash(f'Senha: {nova}'); return redirect(url_for('editar_usuario', id=id))
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
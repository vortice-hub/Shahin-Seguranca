import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "TdS Gestão de RH"
COMMIT_MSG = "V19: Motor de Apuracao de Horas, Saldo Diario e Relatorio de Folha"
DB_URL_FIXA = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# --- CONFIG FILES ---
FILE_RUNTIME = """python-3.11.9"""
FILE_REQ = """flask\nflask-sqlalchemy\npsycopg2-binary\ngunicorn\nflask-login\nwerkzeug"""
FILE_PROCFILE = """web: gunicorn app:app"""

# --- APP.PY (Com Lógica Matemática de Horas) ---
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
app.secret_key = 'chave_v19_calc_secret'

db_url = "{DB_URL_FIXA}"
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app, engine_options={{"pool_pre_ping": True, "pool_size": 10, "pool_recycle": 300}})

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
    
    # Jornada Esperada
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

# NOVO: Tabela de Resumo Diario (Calculada)
class PontoResumo(db.Model):
    __tablename__ = 'ponto_resumos'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_referencia = db.Column(db.Date, nullable=False)
    minutos_trabalhados = db.Column(db.Integer, default=0)
    minutos_esperados = db.Column(db.Integer, default=0)
    minutos_saldo = db.Column(db.Integer, default=0) # Positivo (Extra) ou Negativo (Falta)
    status_dia = db.Column(db.String(50)) # Normal, Falta, Extra, Erro Impar
    
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

# --- MOTOR DE CÁLCULO (A INTELIGENCIA) ---
def time_to_min(t_str):
    if not t_str: return 0
    try:
        h, m = map(int, str(t_str).split(':')[:2])
        return h * 60 + m
    except: return 0

def calcular_dia(user_id, data_ref):
    # 1. Busca pontos do dia
    pontos = PontoRegistro.query.filter_by(user_id=user_id, data_registro=data_ref).order_by(PontoRegistro.hora_registro).all()
    
    # 2. Busca Jornada do User
    user = User.query.get(user_id)
    if not user: return
    
    jornada_minutos = 0
    try:
        # Ex: 08:00 as 12:00 + 13:00 as 17:00
        m_ent = time_to_min(user.horario_entrada)
        m_alm_ini = time_to_min(user.horario_almoco_inicio)
        m_alm_fim = time_to_min(user.horario_almoco_fim)
        m_sai = time_to_min(user.horario_saida)
        jornada_minutos = (m_alm_ini - m_ent) + (m_sai - m_alm_fim)
    except:
        jornada_minutos = 480 # 8 horas default
    
    # 3. Calcula Trabalhado
    trabalhado_minutos = 0
    status = "OK"
    
    # Logica de Pares (Entrada-Saida)
    # Se tiver numero impar de batidas, nao da pra calcular com precisao
    if len(pontos) % 2 != 0:
        status = "Erro: Batidas Ímpares"
        # Tenta calcular o que der (pares)
        loops = len(pontos) - 1
    else:
        loops = len(pontos)
        
    for i in range(0, loops, 2):
        ent = pontos[i].hora_registro
        sai = pontos[i+1].hora_registro
        delta = (sai.hour * 60 + sai.minute) - (ent.hour * 60 + ent.minute)
        trabalhado_minutos += delta
        
    # 4. Calcula Saldo
    saldo = trabalhado_minutos - jornada_minutos
    
    # Tolerancia (10 min diario CLT)
    if abs(saldo) <= 10:
        saldo = 0
        status = "Normal (Tol)"
    elif saldo > 0:
        status = "Hora Extra"
    elif saldo < 0:
        status = "Atraso/Falta"
        
    if len(pontos) == 0:
        # Se for dia util (Seg a Sex), é falta
        if data_ref.weekday() < 5: 
            status = "Falta Total"
            saldo = -jornada_minutos
        else:
            status = "Folga"
            saldo = 0
            
    # 5. Salva no Banco (Update ou Insert)
    resumo = PontoResumo.query.filter_by(user_id=user_id, data_referencia=data_ref).first()
    if not resumo:
        resumo = PontoResumo(user_id=user_id, data_referencia=data_ref)
        db.session.add(resumo)
    
    resumo.minutos_trabalhados = trabalhado_minutos
    resumo.minutos_esperados = jornada_minutos
    resumo.minutos_saldo = saldo
    resumo.status_dia = status
    db.session.commit()

# --- BOOT ---
try:
    with app.app_context():
        db.create_all()
        # Cria master se nao existir
        if not User.query.filter_by(username='Thaynara').first():
            m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
            m.set_password('1855')
            db.session.add(m); db.session.commit()
except: pass

# --- ROTAS NOVAS (RELATORIO) ---

@app.route('/admin/relatorio-folha', methods=['GET', 'POST'])
@login_required
def admin_relatorio_folha():
    if current_user.role != 'Master': return redirect(url_for('dashboard'))
    
    mes_ref = datetime.now().strftime('%Y-%m')
    if request.method == 'POST':
        mes_ref = request.form.get('mes_ref')
    
    # Buscar todos os usuarios
    users = User.query.all()
    relatorio = []
    
    ano, mes = map(int, mes_ref.split('-'))
    
    for u in users:
        # Busca resumos do mes
        resumos = PontoResumo.query.filter(
            PontoResumo.user_id == u.id,
            func.extract('year', PontoResumo.data_referencia) == ano,
            func.extract('month', PontoResumo.data_referencia) == mes
        ).all()
        
        total_saldo = sum(r.minutos_saldo for r in resumos)
        
        # Formata saldo HH:MM
        sinal = "+" if total_saldo >= 0 else "-"
        abs_saldo = abs(total_saldo)
        horas = abs_saldo // 60
        minutos = abs_saldo % 60
        saldo_str = f"{{sinal}}{{horas:02d}}:{{minutos:02d}}"
        
        relatorio.append({{
            'nome': u.real_name,
            'cargo': u.role,
            'saldo_minutos': total_saldo,
            'saldo_formatado': saldo_str,
            'status': 'Crédito' if total_saldo >= 0 else 'Débito'
        }})
        
    return render_template('admin_relatorio_folha.html', relatorio=relatorio, mes_ref=mes_ref)

# --- ROTAS EXISTENTES (ATUALIZADAS PARA CHAMAR O CÁLCULO) ---

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
        # CHAMA O CALCULO
        calcular_dia(current_user.id, hoje)
        return redirect(url_for('dashboard'))
    return render_template('ponto_registro.html', proxima_acao=proxima, hoje=hoje, pontos=pontos_hoje)

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
                
                db.session.commit()
                # RECALCULA O DIA AFETADO
                calcular_dia(solic.user_id, solic.data_referencia)
                flash('Aprovado e Recalculado.')
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
                # Busca resumo calculado
                resumo = PontoResumo.query.filter_by(user_id=r.user_id, data_referencia=r.data_registro).first()
                saldo_fmt = "Calc..."
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
        # Para usuario comum, vamos agrupar por dia tbm para mostrar saldo
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

# --- OUTRAS ROTAS NECESSÁRIAS (Mantidas) ---
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

# Rotas de edição historico mantidas...
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

# --- RELATORIO DE FOLHA (NOVO) ---
FILE_RELATORIO_FOLHA = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6 flex flex-col md:flex-row justify-between items-center gap-4">
    <h2 class="text-2xl font-bold text-slate-800">Relatório de Folha</h2>
    <form action="/admin/relatorio-folha" method="POST" class="flex gap-2">
        <input type="month" name="mes_ref" value="{{ mes_ref }}" class="border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-600 bg-white">
        <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded-lg font-bold text-sm hover:bg-blue-700 transition">GERAR RELATÓRIO</button>
    </form>
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <table class="w-full text-left text-sm text-slate-600">
        <thead class="bg-slate-50 text-xs uppercase text-slate-400 font-bold border-b border-slate-100">
            <tr>
                <th class="px-6 py-4">Funcionário</th>
                <th class="px-6 py-4">Cargo</th>
                <th class="px-6 py-4 text-center">Status</th>
                <th class="px-6 py-4 text-right">Saldo do Mês</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
            {% for item in relatorio %}
            <tr class="hover:bg-slate-50 transition">
                <td class="px-6 py-4 font-bold text-slate-800">{{ item.nome }}</td>
                <td class="px-6 py-4">{{ item.cargo }}</td>
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

# --- ESPELHO MASTER ATUALIZADO (MOSTRA SALDO) ---
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
                <div>
                    <h3 class="font-bold text-slate-800 text-sm nome-func">{{ grupo.user.real_name }}</h3>
                    <p class="text-xs text-slate-500 font-mono">{{ grupo.data.strftime('%d/%m/%Y') }}</p>
                </div>
            </div>
            <div class="flex items-center gap-4">
                <!-- Mostrador de Saldo no Card -->
                {% if grupo.saldo %}
                <div class="text-right">
                    <span class="block text-[10px] font-bold uppercase text-slate-400">Saldo</span>
                    <span class="text-sm font-mono font-bold 
                        {% if '-' in grupo.saldo %} text-red-600 {% else %} text-emerald-600 {% endif %}">
                        {{ grupo.saldo }}
                    </span>
                </div>
                {% endif %}
                <i class="fas fa-chevron-down text-slate-400"></i>
            </div>
        </button>
        
        <div id="detalhe-{{ loop.index }}" class="hidden border-t border-slate-100">
            <div class="p-4 bg-white grid grid-cols-2 gap-2">
                {% for p in grupo.pontos %}
                <div class="flex justify-between items-center p-2 rounded bg-slate-50 border border-slate-100">
                    <span class="text-xs font-bold text-slate-600">{{ p.tipo }}</span>
                    <span class="text-sm font-mono font-bold text-blue-600">{{ p.hora_registro.strftime('%H:%M') }}</span>
                </div>
                {% endfor %}
                <div class="col-span-2 text-center text-xs text-slate-400 mt-2 bg-slate-50 p-1 rounded">Status: {{ grupo.status }}</div>
            </div>
        </div>
    </div>
    {% else %}
    <div class="text-center py-10 text-slate-400">Nenhum registro encontrado.</div>
    {% endfor %}
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

# --- ESPELHO COLABORADOR ATUALIZADO (MOSTRA SALDO) ---
FILE_PONTO_ESPELHO = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center justify-between mb-6">
    <h2 class="text-xl font-bold text-slate-800">Meu Espelho</h2>
    <form action="/ponto/espelho" method="GET" class="flex gap-2">
        <input type="date" name="data_filtro" value="{{ filtro_data }}" class="border border-slate-200 rounded-lg px-2 py-1 text-xs text-slate-600">
        <button type="submit" class="bg-blue-600 text-white px-3 py-1 rounded-lg font-bold text-xs"><i class="fas fa-filter"></i></button>
        {% if filtro_data %}<a href="/ponto/espelho" class="bg-slate-200 text-slate-600 px-3 py-1 rounded-lg font-bold text-xs">X</a>{% endif %}
    </form>
</div>

<div class="space-y-4">
    {% for dia in dias %}
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="px-4 py-3 bg-slate-50 border-b border-slate-100 flex justify-between items-center">
            <span class="font-bold text-slate-700 text-sm">{{ dia.data.strftime('%d/%m/%Y') }}</span>
            <span class="font-mono text-xs font-bold px-2 py-1 rounded 
                {% if '-' in dia.saldo %} bg-red-100 text-red-700 {% else %} bg-emerald-100 text-emerald-700 {% endif %}">
                Saldo: {{ dia.saldo }}
            </span>
        </div>
        <div class="p-3 grid grid-cols-2 gap-2">
            {% for p in dia.pontos %}
            <div class="flex justify-between p-2 bg-white border border-slate-100 rounded text-xs">
                <span class="text-slate-500 font-bold">{{ p.tipo }}</span>
                <span class="text-blue-600 font-mono font-bold">{{ p.hora_registro.strftime('%H:%M') }}</span>
            </div>
            {% endfor %}
        </div>
    </div>
    {% else %}
    <div class="text-center py-10 text-slate-400">Sem registros.</div>
    {% endfor %}
</div>
{% endblock %}
"""

# --- BASE (SIDEBAR COM NOVO LINK DE RELATORIO) ---
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
                    <li><a href="/admin/usuarios" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-users-cog w-6 text-center mr-2 text-blue-400"></i><span class="font-medium text-blue-100">Funcionários</span></a></li>
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
        print("\n>>> SUCESSO V19 CÁLCULO! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V19 CÁLCULO: {PROJECT_NAME} ---")
    create_backup()
    write_file("runtime.txt", FILE_RUNTIME)
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    write_file("app.py", FILE_APP)
    
    write_file("templates/base.html", FILE_BASE) # Menu Novo
    write_file("templates/admin_relatorio_folha.html", FILE_RELATORIO_FOLHA) # Novo
    write_file("templates/ponto_espelho_master.html", FILE_PONTO_ESPELHO_MASTER) # Atualizado com Saldo
    write_file("templates/ponto_espelho.html", FILE_PONTO_ESPELHO) # Atualizado com Saldo
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



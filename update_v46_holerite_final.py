import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V46: Modulo Holerites - Upload, Leitura de PDF por CPF e Cloudinary"

# --- 1. REQUIREMENTS (Adicionando bibliotecas novas) ---
FILE_REQ = """flask
flask-sqlalchemy
psycopg2-binary
gunicorn
flask-login
werkzeug
cloudinary
pypdf
"""

# --- 2. MODELOS (Nova Tabela Holerite) ---
FILE_MODELS = """
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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

class Holerite(db.Model):
    __tablename__ = 'holerites'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mes_referencia = db.Column(db.String(7), nullable=False) # Formato YYYY-MM
    url_arquivo = db.Column(db.String(500), nullable=False)
    public_id = db.Column(db.String(100)) # ID no Cloudinary
    visualizado = db.Column(db.Boolean, default=False)
    visualizado_em = db.Column(db.DateTime, nullable=True)
    enviado_em = db.Column(db.DateTime, default=get_brasil_time)
    
    user = db.relationship('User', backref=db.backref('holerites', lazy=True))
"""

# --- 3. NOVA ROTA: app/routes/holerites.py (O Robô) ---
FILE_BP_HOLERITES = """
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time
import cloudinary
import cloudinary.uploader
import re
import io
from pypdf import PdfReader, PdfWriter
from datetime import datetime

holerite_bp = Blueprint('holerite', __name__, url_prefix='/holerites')

# Configuração do Cloudinary (Pega automatico do ENV CLOUDINARY_URL)
# Se der erro, ele avisa no log, mas não quebra o app até tentar usar

def encontrar_cpf_no_texto(texto):
    # Procura padroes de CPF (XXX.XXX.XXX-XX ou sem pontuacao)
    # Remove tudo que não é digito para comparar
    apenas_digitos = re.sub(r'\D', '', texto)
    
    # Varre o banco de usuarios para ver se acha o CPF de algum deles nesse texto
    # (Metodo reverso: verifica se o CPF do usuario esta no texto da pagina)
    # Isso é mais seguro que tentar adivinhar o regex do PDF
    
    users = User.query.filter(User.cpf.isnot(None)).all()
    for user in users:
        cpf_limpo = user.cpf.replace('.', '').replace('-', '').strip()
        if len(cpf_limpo) == 11 and cpf_limpo in apenas_digitos:
            return user
    return None

@holerite_bp.route('/admin/importar', methods=['GET', 'POST'])
@login_required
def admin_importar():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        mes_ref = request.form.get('mes_ref')
        
        if not file or not mes_ref:
            flash('Selecione um arquivo e o mês de referência.')
            return redirect(url_for('holerite.admin_importar'))
            
        try:
            reader = PdfReader(file)
            cont_sucesso = 0
            cont_falha = 0
            
            for i, page in enumerate(reader.pages):
                texto = page.extract_text()
                user_encontrado = encontrar_cpf_no_texto(texto)
                
                if user_encontrado:
                    # Cria um novo PDF só com essa pagina na memoria
                    writer = PdfWriter()
                    writer.add_page(page)
                    
                    output_stream = io.BytesIO()
                    writer.write(output_stream)
                    output_stream.seek(0)
                    
                    # Nome do arquivo no Cloudinary
                    nome_arquivo = f"holerite_{user_encontrado.id}_{mes_ref}_{get_brasil_time().timestamp()}"
                    
                    # Upload para Cloudinary
                    upload_result = cloudinary.uploader.upload(
                        output_stream, 
                        public_id=nome_arquivo,
                        resource_type="auto",
                        folder="holerites"
                    )
                    
                    url_pdf = upload_result.get('secure_url')
                    public_id = upload_result.get('public_id')
                    
                    # Salva no Banco
                    # Verifica se ja existe desse mes para evitar duplicidade
                    existente = Holerite.query.filter_by(user_id=user_encontrado.id, mes_referencia=mes_ref).first()
                    if existente:
                        existente.url_arquivo = url_pdf
                        existente.public_id = public_id
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False # Reseta visualizacao
                    else:
                        novo = Holerite(user_id=user_encontrado.id, mes_referencia=mes_ref, url_arquivo=url_pdf, public_id=public_id)
                        db.session.add(novo)
                    
                    cont_sucesso += 1
                else:
                    cont_falha += 1
            
            db.session.commit()
            flash(f"Processamento concluído! {cont_sucesso} holerites enviados. {cont_falha} páginas não identificadas (sem CPF cadastrado).")
            
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao processar arquivo: {str(e)}")
            
    return render_template('admin_upload_holerite.html')

@holerite_bp.route('/meus-documentos')
@login_required
def meus_holerites():
    # Lista os holerites do usuario logado
    holerites = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.mes_referencia.desc()).all()
    return render_template('meus_holerites.html', holerites=holerites)

@holerite_bp.route('/confirmar-recebimento/<int:id>', methods=['POST'])
@login_required
def confirmar_recebimento(id):
    holerite = Holerite.query.get_or_404(id)
    if holerite.user_id != current_user.id:
        flash('Acesso negado.')
        return redirect(url_for('main.dashboard'))
    
    # Registra o aceite
    if not holerite.visualizado:
        holerite.visualizado = True
        holerite.visualizado_em = get_brasil_time()
        db.session.commit()
        flash('Recebimento confirmado com sucesso!')
        
    # Redireciona para o link do PDF (abre em nova aba geralmente)
    return redirect(holerite.url_arquivo)
"""

# --- 4. ATUALIZAR __INIT__ (Registrar Blueprint) ---
FILE_INIT = """
import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instancias globais
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app_inst = Flask(__name__)
    app_inst.secret_key = os.environ.get('SECRET_KEY', 'chave_v46_holerite_secret')
    
    # --- CONFIGURAÇÃO DO BANCO DE DADOS ---
    clean_db_url = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"
    env_db = os.environ.get('DATABASE_URL')
    
    if env_db and env_db.startswith("postgres"):
        db_url = env_db
    else:
        db_url = clean_db_url
        
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    logger.info(f"Conectando DB: {db_url[:20]}...")

    app_inst.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app_inst.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    app_inst.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10
    }

    # Inicializa Extensions
    db.init_app(app_inst)
    login_manager.init_app(app_inst)
    login_manager.login_view = 'auth.login'

    # Registra Blueprints
    with app_inst.app_context():
        from app.routes.auth import auth_bp
        from app.routes.main import main_bp
        from app.routes.admin import admin_bp
        from app.routes.ponto import ponto_bp
        from app.routes.estoque import estoque_bp
        from app.routes.holerites import holerite_bp # NOVO
        
        app_inst.register_blueprint(auth_bp)
        app_inst.register_blueprint(main_bp)
        app_inst.register_blueprint(admin_bp)
        app_inst.register_blueprint(ponto_bp)
        app_inst.register_blueprint(estoque_bp)
        app_inst.register_blueprint(holerite_bp) # NOVO

        try:
            db.create_all()
            from app.models import User
            if not User.query.filter_by(username='Thaynara').first():
                m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
                m.set_password('1855')
                db.session.add(m)
                db.session.commit()
        except Exception as e:
            logger.error(f"Erro Boot DB: {e}")

    return app_inst

app = create_app()
"""

# --- 5. TEMPLATES NOVOS ---

# Template: Admin Upload
FILE_TPL_ADMIN = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-2xl mx-auto">
    <div class="mb-6">
        <h2 class="text-2xl font-bold text-slate-800">Importação de Holerites</h2>
        <p class="text-sm text-slate-500">Envie o PDF único da contabilidade. O sistema cortará e distribuirá automaticamente por CPF.</p>
    </div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-8">
        <form action="/holerites/admin/importar" method="POST" enctype="multipart/form-data" class="space-y-6">
            
            <div>
                <label class="block text-xs font-bold text-slate-400 uppercase mb-2">Mês de Referência</label>
                <input type="month" name="mes_ref" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3" required>
            </div>

            <div>
                <label class="block text-xs font-bold text-slate-400 uppercase mb-2">Arquivo PDF da Folha</label>
                <div class="border-2 border-dashed border-slate-300 rounded-xl p-8 text-center bg-slate-50 hover:bg-slate-100 transition relative">
                    <input type="file" name="arquivo_pdf" accept=".pdf" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer" required>
                    <i class="fas fa-cloud-upload-alt text-3xl text-slate-400 mb-2"></i>
                    <p class="text-sm text-slate-600 font-medium">Clique ou arraste o PDF aqui</p>
                    <p class="text-xs text-slate-400 mt-1">O arquivo deve conter texto selecionável (não pode ser imagem escaneada).</p>
                </div>
            </div>

            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-lg shadow-md transition flex items-center justify-center gap-2" onclick="this.innerHTML='<i class=\\'fas fa-spinner fa-spin\\'></i> Processando...';">
                <i class="fas fa-cogs"></i> PROCESSAR E DISTRIBUIR
            </button>
        </form>
    </div>
</div>
{% endblock %}
"""

# Template: Meus Holerites
FILE_TPL_MEUS = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6">
    <h2 class="text-2xl font-bold text-slate-800">Meus Holerites</h2>
</div>

<div class="grid gap-4">
    {% for h in holerites %}
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex items-center justify-between">
        <div class="flex items-center gap-4">
            <div class="w-12 h-12 rounded-lg flex items-center justify-center text-2xl
                {% if h.visualizado %} bg-emerald-100 text-emerald-600 {% else %} bg-blue-100 text-blue-600 {% endif %}">
                <i class="fas fa-file-invoice-dollar"></i>
            </div>
            <div>
                <div class="font-bold text-slate-800 text-lg">{{ h.mes_referencia }}</div>
                <div class="text-xs text-slate-500">
                    {% if h.visualizado %}
                    <span class="text-emerald-600 font-bold"><i class="fas fa-check-circle"></i> Recebido em {{ h.visualizado_em.strftime('%d/%m/%Y %H:%M') }}</span>
                    {% else %}
                    <span class="text-blue-600 font-bold">Disponível para assinatura</span>
                    {% endif %}
                </div>
            </div>
        </div>

        <form action="/holerites/confirmar-recebimento/{{ h.id }}" method="POST" target="_blank">
            <button type="submit" class="px-4 py-2 rounded-lg font-bold text-sm transition shadow-sm border
                {% if h.visualizado %} 
                    bg-white text-slate-600 border-slate-200 hover:bg-slate-50
                {% else %} 
                    bg-blue-600 text-white border-blue-600 hover:bg-blue-700 animate-pulse
                {% endif %}">
                {% if h.visualizado %} <i class="fas fa-download mr-1"></i> Baixar {% else %} <i class="fas fa-pen-nib mr-1"></i> Assinar e Abrir {% endif %}
            </button>
        </form>
    </div>
    {% else %}
    <div class="text-center py-12 text-slate-400">
        <i class="fas fa-folder-open text-4xl mb-4 opacity-50"></i>
        <p>Nenhum holerite disponível ainda.</p>
    </div>
    {% endfor %}
</div>
{% endblock %}
"""

# --- 6. ATUALIZAR BASE.HTML (Adicionar Links no Menu) ---
FILE_BASE_V46 = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shahin Gestão</title>
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
    </script>
</head>
<body class="bg-slate-50 text-slate-800">
    {% if current_user.is_authenticated and not current_user.is_first_access %}
    <div class="md:hidden bg-white border-b border-slate-200 p-4 flex justify-between items-center sticky top-0 z-40">
        <button onclick="toggleSidebar()" class="text-slate-600 focus:outline-none"><i class="fas fa-bars text-xl"></i></button>
        <span class="font-bold text-lg text-slate-800">Shahin</span>
        <div class="w-8"></div>
    </div>
    <div id="overlay" onclick="toggleSidebar()" class="fixed inset-0 bg-black bg-opacity-50 z-40 hidden md:hidden"></div>
    {% endif %}
    <div class="{% if current_user.is_authenticated and not current_user.is_first_access %}flex h-screen overflow-hidden{% endif %}">
        {% if current_user.is_authenticated and not current_user.is_first_access %}
        <aside id="sidebar" class="sidebar fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-slate-300 transform -translate-x-full md:translate-x-0 md:static md:flex-shrink-0 flex flex-col shadow-2xl h-full">
            <div class="h-16 flex items-center px-6 bg-slate-950 border-b border-slate-800">
                <div class="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-lg mr-3">S</div>
                <span class="font-bold text-xl text-white tracking-tight">Shahin</span>
            </div>
            <div class="p-6 border-b border-slate-800">
                <div class="text-xs font-bold text-slate-500 uppercase mb-1">Olá,</div>
                <div class="text-sm font-bold text-white truncate">{{ current_user.real_name }}</div>
            </div>
            <nav class="flex-1 overflow-y-auto py-4">
                <ul class="space-y-1">
                    <li><a href="/" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-home w-6 text-center mr-2 text-slate-500 group-hover:text-blue-500"></i><span class="font-medium">Início</span></a></li>
                    
                    <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Funcionário</li>
                    <li><a href="/ponto/registrar" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-fingerprint w-6 text-center mr-2 text-slate-500 group-hover:text-purple-500"></i><span class="font-medium">Registrar Ponto</span></a></li>
                    <li><a href="/ponto/espelho" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-calendar-alt w-6 text-center mr-2 text-slate-500"></i><span class="font-medium">Espelho de Ponto</span></a></li>
                    <li><a href="/holerites/meus-documentos" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-folder w-6 text-center mr-2 text-slate-500 group-hover:text-yellow-400"></i><span class="font-medium">Meus Holerites</span></a></li>
                    <li><a href="/ponto/solicitar-ajuste" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-edit w-6 text-center mr-2 text-slate-500"></i><span class="font-medium">Solicitar Ajuste</span></a></li>
                    
                    {% if current_user.role == 'Master' %}
                    <li class="pt-4 pb-2 px-6 text-[10px] font-bold uppercase text-slate-600">Administração</li>
                    <li><a href="/holerites/admin/importar" class="flex items-center px-6 py-3 hover:bg-slate-800 hover:text-white transition group"><i class="fas fa-file-upload w-6 text-center mr-2 text-slate-500 group-hover:text-blue-400"></i><span class="font-medium">Importar Holerites</span></a></li>
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
            <footer class="py-6 text-center text-xs text-slate-400">&copy; 2026 Vortice Company</footer>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

# --- FUNÇÕES ---
def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f: f.write(content.strip())
    print(f"Atualizado: {path}")

def git_update():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO V46 MÓDULO HOLERITES! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V46 HOLERITES: {PROJECT_NAME} ---")
    
    write_file("requirements.txt", FILE_REQ)
    write_file("app/models.py", FILE_MODELS)
    write_file("app/routes/holerites.py", FILE_BP_HOLERITES)
    write_file("app/__init__.py", FILE_INIT)
    write_file("app/templates/admin_upload_holerite.html", FILE_TPL_ADMIN)
    write_file("app/templates/meus_holerites.html", FILE_TPL_MEUS)
    write_file("app/templates/base.html", FILE_BASE_V46)
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()
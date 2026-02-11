import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V55: Migracao de Armazenamento - Fim do Cloudinary - Holerites salvos no DB"

# --- 1. MODELOS (Adicionando campo para ficheiro binário) ---
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

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

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
    latitude = db.Column(db.String(50)); longitude = db.Column(db.String(50))
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
    tamanho = db.Column(db.String(10)); genero = db.Column(db.String(20)) 
    quantidade = db.Column(db.Integer, default=0)
    estoque_minimo = db.Column(db.Integer, default=5); estoque_ideal = db.Column(db.Integer, default=20)
    data_atualizacao = db.Column(db.DateTime, default=get_brasil_time)

class HistoricoEntrada(db.Model):
    __tablename__ = 'historico_entrada'
    id = db.Column(db.Integer, primary_key=True)
    item_nome = db.Column(db.String(150)); quantidade = db.Column(db.Integer)
    data_hora = db.Column(db.DateTime, default=get_brasil_time)

class HistoricoSaida(db.Model):
    __tablename__ = 'historico_saida'
    id = db.Column(db.Integer, primary_key=True)
    coordenador = db.Column(db.String(100)); colaborador = db.Column(db.String(100))
    item_nome = db.Column(db.String(100)); tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20)); quantidade = db.Column(db.Integer)
    data_entrega = db.Column(db.DateTime, default=get_brasil_time)

# --- MODELO HOLERITE (ATUALIZADO PARA GUARDAR O ARQUIVO NO BANCO) ---
class Holerite(db.Model):
    __tablename__ = 'holerites'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mes_referencia = db.Column(db.String(7), nullable=False) # YYYY-MM
    
    # Campo binário para o conteúdo do PDF
    conteudo_pdf = db.Column(db.LargeBinary, nullable=True) 
    
    visualizado = db.Column(db.Boolean, default=False)
    visualizado_em = db.Column(db.DateTime, nullable=True)
    enviado_em = db.Column(db.DateTime, default=get_brasil_time)
    
    user = db.relationship('User', backref=db.backref('holerites', lazy=True))
"""

# --- 2. ROTA HOLERITES (Removendo Cloudinary e salvando no DB) ---
FILE_BP_HOLERITES = """
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time, remove_accents
import io
import logging
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)
holerite_bp = Blueprint('holerite', __name__, url_prefix='/holerites')

def encontrar_usuario_por_nome(texto_pagina):
    texto_limpo = remove_accents(texto_pagina).upper()
    users = User.query.all()
    candidatos = []
    for u in users:
        nome_limpo = remove_accents(u.real_name).upper().strip()
        if len(nome_limpo.split()) > 1 and nome_limpo in texto_limpo:
            candidatos.append(u)
    return candidatos[0] if len(candidatos) == 1 else None

@holerite_bp.route('/admin/importar', methods=['GET', 'POST'])
@login_required
def admin_importar():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        if request.form.get('acao') == 'limpar_tudo':
            Holerite.query.delete(); db.session.commit()
            flash('Histórico limpo.'); return redirect(url_for('holerite.admin_importar'))

        file = request.files.get('arquivo_pdf')
        mes_ref = request.form.get('mes_ref')
        if not file or not mes_ref: return redirect(url_for('holerite.admin_importar'))
            
        try:
            reader = PdfReader(file)
            sucesso = 0
            for page in reader.pages:
                user = encontrar_usuario_por_nome(page.extract_text())
                if user:
                    writer = PdfWriter(); writer.add_page(page)
                    out = io.BytesIO(); writer.write(out); binary_data = out.getvalue()
                    
                    existente = Holerite.query.filter_by(user_id=user.id, mes_referencia=mes_ref).first()
                    if existente:
                        existente.conteudo_pdf = binary_data
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False
                    else:
                        novo = Holerite(user_id=user.id, mes_referencia=mes_ref, conteudo_pdf=binary_data)
                        db.session.add(novo)
                    sucesso += 1
            db.session.commit()
            flash(f'Sucesso: {sucesso} holerites guardados no sistema.')
        except Exception as e:
            db.session.rollback(); flash(f'Erro: {e}')

    ultimos = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    return render_template('admin_upload_holerite.html', uploads=ultimos)

@holerite_bp.route('/meus-documentos')
@login_required
def meus_holerites():
    docs = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.mes_referencia.desc()).all()
    return render_template('meus_holerites.html', holerites=docs)

@holerite_bp.route('/baixar/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if doc.user_id != current_user.id: return redirect(url_for('main.dashboard'))
    
    if not doc.visualizado:
        doc.visualizado = True; doc.visualizado_em = get_brasil_time(); db.session.commit()
        
    if not doc.conteudo_pdf:
        flash("Arquivo não encontrado no banco."); return redirect(url_for('holerite.meus_holerites'))
        
    return send_file(
        io.BytesIO(doc.conteudo_pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Holerite_{doc.mes_referencia}.pdf"
    )
"""

# --- 3. __INIT__.PY (Removendo lixo do Cloudinary) ---
FILE_INIT = """
import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app_inst = Flask(__name__)
    app_inst.secret_key = os.environ.get('SECRET_KEY', 'chave_v55_db_only')
    
    db_url = os.environ.get('DATABASE_URL', "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require")
    if db_url.startswith("postgres://"): db_url = db_url.replace("postgres://", "postgresql://", 1)

    app_inst.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app_inst.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app_inst.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 10}

    db.init_app(app_inst)
    login_manager.init_app(app_inst)
    login_manager.login_view = 'auth.login'

    with app_inst.app_context():
        from app.routes.auth import auth_bp
        from app.routes.main import main_bp
        from app.routes.admin import admin_bp
        from app.routes.ponto import ponto_bp
        from app.routes.estoque import estoque_bp
        from app.routes.holerites import holerite_bp 
        
        app_inst.register_blueprint(auth_bp); app_inst.register_blueprint(main_bp)
        app_inst.register_blueprint(admin_bp); app_inst.register_blueprint(ponto_bp)
        app_inst.register_blueprint(estoque_bp); app_inst.register_blueprint(holerite_bp)

        try:
            db.create_all()
            from app.models import User
            if not User.query.filter_by(username='Thaynara').first():
                m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
                m.set_password('1855'); db.session.add(m); db.session.commit()
        except: pass
    return app_inst
app = create_app()
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
        print("\n>>> SUCESSO V55! ARMAZENAMENTO INTERNO ATIVADO <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V55 DB STORAGE: {PROJECT_NAME} ---")
    write_file("app/models.py", FILE_MODELS)
    write_file("app/routes/holerites.py", FILE_BP_HOLERITES)
    write_file("app/__init__.py", FILE_INIT)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



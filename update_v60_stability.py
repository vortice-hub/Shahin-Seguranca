import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V60: Estabilizacao do Deploy - Removendo gargalos de inicializacao"

# --- 1. APP/UTILS.PY (REVISADO E COMPLETO) ---
FILE_UTILS = """
from datetime import datetime, timedelta, time
import unicodedata
import re

def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

def remove_accents(txt):
    if not txt: return ""
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def gerar_login_automatico(nome_completo):
    if not nome_completo: return "user"
    partes = nome_completo.split()
    primeiro_nome = remove_accents(partes[0]).lower()
    return re.sub(r'[^a-z]', '', primeiro_nome)

def time_to_minutes(t):
    if not t: return 0
    if isinstance(t, str):
        try:
            h, m = map(int, t.split(':'))
            return h * 60 + m
        except: return 0
    return t.hour * 60 + t.minute

def format_minutes_to_hm(total_minutes):
    sinal = "" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{sinal}{h:02d}:{m:02d}"

def calcular_dia(user_id, data_ref):
    from app import db
    from app.models import User, PontoRegistro, PontoResumo
    user = User.query.get(user_id)
    if not user: return

    registros = PontoRegistro.query.filter_by(user_id=user_id, data_registro=data_ref).order_by(PontoRegistro.hora_registro).all()
    
    ent_prev = time_to_minutes(user.horario_entrada)
    sai_prev = time_to_minutes(user.horario_saida)
    alm_ini_prev = time_to_minutes(user.horario_almoco_inicio)
    alm_fim_prev = time_to_minutes(user.horario_almoco_fim)
    
    minutos_esperados = (sai_prev - ent_prev) - (alm_fim_prev - alm_ini_prev)
    if minutos_esperados < 0: minutos_esperados = 0
    
    if data_ref.weekday() >= 5 and user.escala != 'Livre':
        minutos_esperados = 0

    trabalhado_total = 0
    for i in range(0, len(registros), 2):
        if i + 1 < len(registros):
            inicio = time_to_minutes(registros[i].hora_registro)
            fim = time_to_minutes(registros[i+1].hora_registro)
            trabalhado_total += (fim - inicio)

    saldo = trabalhado_total - minutos_esperados
    
    status = "OK"
    if len(registros) == 0 and minutos_esperados > 0: status = "Falta"
    elif len(registros) % 2 != 0: status = "Incompleto"
    elif saldo > 0: status = "Hora Extra"
    elif saldo < 0: status = "Débito"

    resumo = PontoResumo.query.filter_by(user_id=user_id, data_referencia=data_ref).first()
    if not resumo:
        resumo = PontoResumo(user_id=user_id, data_referencia=data_ref)
        db.session.add(resumo)
    
    resumo.minutos_trabalhados = trabalhado_total
    resumo.minutos_esperados = minutos_esperados
    resumo.minutos_saldo = saldo
    resumo.status_dia = status
    try:
        db.session.commit()
    except:
        db.session.rollback()
"""

# --- 2. APP/__INIT__.PY (OTIMIZADO PARA STARTUP RÁPIDO) ---
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
    app_inst.secret_key = os.environ.get('SECRET_KEY', 'v60_stable_key')
    
    # Config DB com timeouts para nao travar o deploy
    db_url = os.environ.get('DATABASE_URL', "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require")
    if db_url.startswith("postgres://"): db_url = db_url.replace("postgres://", "postgresql://", 1)

    app_inst.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app_inst.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app_inst.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "connect_args": {"connect_timeout": 10}
    }

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
        
        app_inst.register_blueprint(auth_bp)
        app_inst.register_blueprint(main_bp)
        app_inst.register_blueprint(admin_bp)
        app_inst.register_blueprint(ponto_bp)
        app_inst.register_blueprint(estoque_bp)
        app_inst.register_blueprint(holerite_bp)

        try:
            db.create_all()
            # Criar Master apenas se nao existir, de forma rapida
            from app.models import User
            if not User.query.filter_by(username='Thaynara').first():
                m = User(username='Thaynara', real_name='Thaynara Master', role='Master', is_first_access=False)
                m.set_password('1855')
                db.session.add(m)
                db.session.commit()
            logger.info("Startup do Banco de Dados concluído com sucesso.")
        except Exception as e:
            logger.error(f"Aviso no startup: {e}")

    return app_inst

app = create_app()
"""

# --- 3. APP/ROUTES/HOLERITES.PY (LIMPO E FUNCIONAL) ---
FILE_BP_HOLERITES = """
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time, remove_accents
import io
from pypdf import PdfReader, PdfWriter
from sqlalchemy import text

holerite_bp = Blueprint('holerite', __name__, url_prefix='/holerites')

def encontrar_usuario_por_nome(texto_pagina):
    texto_limpo = remove_accents(texto_pagina).upper()
    users = User.query.all()
    for u in users:
        nome_limpo = remove_accents(u.real_name).upper().strip()
        if len(nome_limpo.split()) > 1 and nome_limpo in texto_limpo:
            return u
    return None

@holerite_bp.route('/admin/importar', methods=['GET', 'POST'])
@login_required
def admin_importar():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        if request.form.get('acao') == 'limpar_tudo':
            Holerite.query.delete()
            db.session.commit()
            flash('Histórico removido.')
            return redirect(url_for('holerite.admin_importar'))

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
                    out = io.BytesIO(); writer.write(out)
                    
                    existente = Holerite.query.filter_by(user_id=user.id, mes_referencia=mes_ref).first()
                    if existente:
                        existente.conteudo_pdf = out.getvalue()
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False
                    else:
                        novo = Holerite(user_id=user.id, mes_referencia=mes_ref, conteudo_pdf=out.getvalue())
                        db.session.add(novo)
                    sucesso += 1
            db.session.commit()
            flash(f'Sucesso: {sucesso} holerites processados.')
        except Exception as e:
            db.session.rollback(); flash(f'Erro: {e}')

    ultimos = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    return render_template('admin_upload_holerite.html', uploads=ultimos)

@holerite_bp.route('/meus-documentos')
@login_required
def meus_holerites():
    docs = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.mes_referencia.desc()).all()
    return render_template('meus_holerites.html', holerites=docs)

@holerite_bp.route('/baixar/<int:id>', methods=['GET', 'POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if current_user.role != 'Master' and doc.user_id != current_user.id: 
        return redirect(url_for('main.dashboard'))
    
    if not doc.visualizado and current_user.id == doc.user_id:
        doc.visualizado = True
        doc.visualizado_em = get_brasil_time()
        db.session.commit()
        
    return send_file(
        io.BytesIO(doc.conteudo_pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Holerite_{doc.mes_referencia}.pdf"
    )
"""

# --- FUNÇÕES ---
def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())
    print(f"Atualizado: {path}")

def git_update():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO V60! AGUARDE O DEPLOY NO RENDER <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V60 STABILITY: {PROJECT_NAME} ---")
    write_file("app/utils.py", FILE_UTILS)
    write_file("app/__init__.py", FILE_INIT)
    write_file("app/routes/holerites.py", FILE_BP_HOLERITES)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



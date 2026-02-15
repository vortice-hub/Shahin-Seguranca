import os
import shutil
import subprocess
import sys
from datetime import datetime

# ================= CONFIGURAÇÕES =================
PROJECT_DIR = os.getcwd()
BACKUP_ROOT = os.path.join(PROJECT_DIR, "backups_auto")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
CURRENT_BACKUP_DIR = os.path.join(BACKUP_ROOT, f"bkp_{TIMESTAMP}")

# Arquivos que serão modificados
FILES_TO_MODIFY = [
    "app/__init__.py",
    "app/ponto/routes.py",
    "app/admin/routes.py"
]

def log(msg):
    print(f"\033[92m[AUTO-SCRIPT]\033[0m {msg}")

def create_backup():
    log("Iniciando backup de segurança...")
    if not os.path.exists(CURRENT_BACKUP_DIR):
        os.makedirs(CURRENT_BACKUP_DIR)
    
    for file_path in FILES_TO_MODIFY:
        full_path = os.path.join(PROJECT_DIR, file_path)
        if os.path.exists(full_path):
            dest_path = os.path.join(CURRENT_BACKUP_DIR, file_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(full_path, dest_path)
            log(f"Arquivo salvo: {file_path}")
        else:
            log(f"\033[93mAlerta: Arquivo original não encontrado para backup: {file_path}\033[0m")

def apply_fixes():
    log("Aplicando correções no código...")

    # ---------------------------------------------------------
    # FIX 1: app/__init__.py (Correção do Erro SSL/DB Drop)
    # ---------------------------------------------------------
    content_init = """import os
from flask import Flask
from app.extensions import db, login_manager

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'chave_secreta_padrao')
    
    # Configuração do Banco
    db_url = os.environ.get('DATABASE_URL', "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # FIX: Configurações para manter a conexão com o banco viva (evita SSL EOF Error)
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10,
        "max_overflow": 20,
    }
    
    # Inicializa Extensões
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # Registra Blueprints
    with app.app_context():
        from app.auth.routes import auth_bp
        from app.admin.routes import admin_bp
        from app.ponto.routes import ponto_bp
        from app.estoque.routes import estoque_bp
        from app.holerites.routes import holerite_bp
        from app.main.routes import main_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(admin_bp)
        app.register_blueprint(ponto_bp)
        app.register_blueprint(estoque_bp)
        app.register_blueprint(holerite_bp)
        app.register_blueprint(main_bp)

        try:
            db.create_all()
        except:
            pass

    return app

app = create_app()
"""
    with open(os.path.join(PROJECT_DIR, "app/__init__.py"), "w", encoding="utf-8") as f:
        f.write(content_init)

    # ---------------------------------------------------------
    # FIX 2: app/ponto/routes.py (Correção TemplateNotFound)
    # ---------------------------------------------------------
    content_ponto = """from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import PontoRegistro, PontoResumo, User
from app.utils import get_brasil_time, calcular_dia, format_minutes_to_hm
from datetime import datetime, date
from sqlalchemy import func

ponto_bp = Blueprint('ponto', __name__, template_folder='templates', url_prefix='/ponto')

@ponto_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    hoje = get_brasil_time().date()
    if request.method == 'POST':
        tipo = request.form.get('tipo')
        lat = request.form.get('lat')
        lon = request.form.get('lon')
        
        novo = PontoRegistro(
            user_id=current_user.id, 
            data_registro=hoje, 
            tipo=tipo, 
            latitude=lat, 
            longitude=lon
        )
        db.session.add(novo)
        db.session.commit()
        
        # Recalcula o saldo do dia
        calcular_dia(current_user.id, hoje)
        
        flash(f'Ponto de {tipo} registrado!')
        return redirect(url_for('main.dashboard'))
    
    registros = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).all()
    # FIX: Nome do template corrigido de 'registrar_ponto.html' para 'ponto_registro.html'
    return render_template('ponto_registro.html', registros=registros)

@ponto_bp.route('/espelho')
@login_required
def espelho_ponto():
    target_user_id = request.args.get('user_id', type=int) or current_user.id
    if target_user_id != current_user.id and current_user.role != 'Master':
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(target_user_id)
    mes_ref = request.args.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    try:
        ano, mes = map(int, mes_ref.split('-'))
    except:
        hoje = get_brasil_time()
        ano, mes = hoje.year, hoje.month
        mes_ref = hoje.strftime('%Y-%m')
    
    resumos = PontoResumo.query.filter(
        PontoResumo.user_id == target_user_id,
        func.extract('year', PontoResumo.data_referencia) == ano,
        func.extract('month', PontoResumo.data_referencia) == mes
    ).order_by(PontoResumo.data_referencia).all()
    
    detalhes = {}
    for r in resumos:
        batidas = PontoRegistro.query.filter_by(user_id=target_user_id, data_registro=r.data_referencia).order_by(PontoRegistro.hora_registro).all()
        detalhes[r.id] = [b.hora_registro.strftime('%H:%M') for b in batidas]

    return render_template('ponto/ponto_espelho.html', resumos=resumos, user=user, detalhes=detalhes, format_hm=format_minutes_to_hm, mes_ref=mes_ref)

@ponto_bp.route('/solicitar-ajuste', methods=['GET', 'POST'])
@login_required
def solicitar_ajuste():
    # Implementação futura ou placeholder para evitar erro 404 se chamado
    return render_template('ponto/solicitar_ajuste.html', data_sel=None, meus_ajustes=[])
"""
    with open(os.path.join(PROJECT_DIR, "app/ponto/routes.py"), "w", encoding="utf-8") as f:
        f.write(content_ponto)

    # ---------------------------------------------------------
    # FIX 3: app/admin/routes.py (Correção Rotas 404 e Importações)
    # ---------------------------------------------------------
    content_admin = """from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, PreCadastro, PontoResumo, PontoAjuste, PontoRegistro, Holerite
from app.utils import calcular_dia, get_brasil_time, format_minutes_to_hm, gerar_login_automatico
from werkzeug.security import generate_password_hash
import csv
import io
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__, template_folder='templates', url_prefix='/admin')

# --- ROTAS CORRIGIDAS/ADICIONADAS ---

@admin_bp.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
def novo_usuario():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        try:
            # Criação manual de usuário ou pré-cadastro
            real_name = request.form.get('real_name')
            cpf = request.form.get('cpf').replace('.', '').replace('-', '').strip()
            
            # Verifica duplicidade
            if User.query.filter_by(cpf=cpf).first() or PreCadastro.query.filter_by(cpf=cpf).first():
                flash('CPF já cadastrado!', 'error')
                return redirect(url_for('admin.novo_usuario'))

            # Criação direta de PreCadastro para o fluxo "Sou Funcionário"
            novo_pre = PreCadastro(
                cpf=cpf,
                nome_previsto=real_name,
                cargo=request.form.get('role'),
                salario=float(request.form.get('salario') or 0),
                horario_entrada=request.form.get('h_ent'),
                horario_almoco_inicio=request.form.get('h_alm_ini'),
                horario_almoco_fim=request.form.get('h_alm_fim'),
                horario_saida=request.form.get('h_sai'),
                escala=request.form.get('escala'),
                data_inicio_escala=request.form.get('dt_escala') if request.form.get('dt_escala') else None
            )
            db.session.add(novo_pre)
            db.session.commit()
            return render_template('sucesso_usuario.html', nome_real=real_name, cpf=cpf)
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar: {str(e)}', 'error')
            
    return render_template('novo_usuario.html')

@admin_bp.route('/solicitacoes', methods=['GET', 'POST'])
@login_required
def admin_solicitacoes():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        solic_id = request.form.get('solic_id')
        decisao = request.form.get('decisao')
        motivo = request.form.get('motivo_repro')
        
        solic = PontoAjuste.query.get(solic_id)
        if solic:
            if decisao == 'aprovar':
                solic.status = 'Aprovado'
                # Lógica para aplicar a alteração no ponto (se for edição/inclusão)
                # ... (Implementar lógica de aplicar no PontoRegistro se necessário)
                flash('Solicitação Aprovada.')
            else:
                solic.status = 'Reprovado'
                solic.motivo_reprovacao = motivo
                flash('Solicitação Reprovada.')
            db.session.commit()
            
    solicitacoes = PontoAjuste.query.filter_by(status='Pendente').order_by(PontoAjuste.created_at.desc()).all()
    extras = {} # Dicionário para dados auxiliares se necessário
    return render_template('admin_solicitacoes.html', solicitacoes=solicitacoes, extras=extras)

@admin_bp.route('/liberar-acesso', methods=['POST'])
@login_required
def liberar_acesso():
    # Rota auxiliar para processar o formulário da página 'admin_liberar_acesso.html'
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    try:
        cpf = request.form.get('cpf').replace('.', '').replace('-', '').strip()
        if User.query.filter_by(cpf=cpf).first() or PreCadastro.query.filter_by(cpf=cpf).first():
            flash('CPF já existe.', 'error')
        else:
            novo = PreCadastro(
                cpf=cpf,
                nome_previsto=request.form.get('nome'),
                cargo=request.form.get('cargo'),
                salario=float(request.form.get('salario') or 0),
                horario_entrada=request.form.get('h_ent'),
                horario_almoco_inicio=request.form.get('h_alm_ini'),
                horario_almoco_fim=request.form.get('h_alm_fim'),
                horario_saida=request.form.get('h_sai'),
                escala=request.form.get('escala'),
                data_inicio_escala=request.form.get('dt_escala') if request.form.get('dt_escala') else None
            )
            db.session.add(novo)
            db.session.commit()
            flash('Acesso liberado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro: {e}', 'error')
        
    return redirect(url_for('admin.gerenciar_usuarios')) # Ou redirecionar para liberar_acesso page se houver

@admin_bp.route('/liberar-acesso/excluir/<int:id>')
@login_required
def excluir_liberacao(id):
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    pre = PreCadastro.query.get(id)
    if pre:
        db.session.delete(pre)
        db.session.commit()
        flash('Removido da fila.')
    return redirect(url_for('admin.gerenciar_usuarios'))

# --- ROTAS EXISTENTES MANTIDAS ---

@admin_bp.route('/ferramentas/limpeza', methods=['GET', 'POST'])
@login_required
def admin_limpeza():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        try:
            if acao == 'limpar_testes_ponto':
                PontoRegistro.query.delete()
                PontoResumo.query.delete()
                flash('Registros de ponto limpos.')
            elif acao == 'limpar_holerites':
                Holerite.query.delete()
                flash('Holerites removidos do banco.')
            elif acao == 'limpar_usuarios_nao_master':
                User.query.filter(User.username != 'Thaynara').delete()
                PreCadastro.query.delete()
                flash('Usuários de teste removidos.')
            
            db.session.commit()
            return redirect(url_for('admin.admin_limpeza'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro na limpeza: {e}')
            
    return render_template('admin/admin_limpeza.html')

@admin_bp.route('/relatorio-folha', methods=['GET', 'POST'])
@login_required
def admin_relatorio_folha():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    mes_ref = request.form.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    try: ano, mes = map(int, mes_ref.split('-'))
    except: hoje = get_brasil_time(); ano, mes = hoje.year, hoje.month; mes_ref = hoje.strftime('%Y-%m')
    
    users = User.query.order_by(User.real_name).all()
    relatorio = []
    for u in users:
        resumos = PontoResumo.query.filter(
            PontoResumo.user_id == u.id, 
            func.extract('year', PontoResumo.data_referencia) == ano, 
            func.extract('month', PontoResumo.data_referencia) == mes
        ).all()
        total_saldo = sum(r.minutos_saldo for r in resumos)
        relatorio.append({
            'id': u.id,
            'nome': u.real_name,
            'cargo': u.role,
            'saldo_formatado': format_minutes_to_hm(total_saldo),
            'sinal': 'text-emerald-600' if total_saldo >= 0 else 'text-red-600'
        })
    return render_template('admin/admin_relatorio_folha.html', relatorio=relatorio, mes_ref=mes_ref)

@admin_bp.route('/usuarios/importar-csv', methods=['GET', 'POST'])
@login_required
def importar_csv():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        file = request.files.get('arquivo_csv')
        if not file: return redirect(url_for('admin.importar_csv'))
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream, delimiter=';')
            count = 0
            for row in csv_reader:
                cpf_limpo = row.get('CPF', '').replace('.', '').replace('-', '').strip()
                if not cpf_limpo: continue
                if PreCadastro.query.filter_by(cpf=cpf_limpo).first() or User.query.filter_by(cpf=cpf_limpo).first(): continue
                pre = PreCadastro(
                    cpf=cpf_limpo,
                    nome_previsto=row.get('Nome', 'Funcionario'),
                    cargo=row.get('Cargo', 'Colaborador'),
                    salario=float(row.get('Salario', 0).replace(',', '.') or 0),
                    horario_entrada=row.get('Entrada', '07:12'),
                    horario_saida=row.get('Saida', '17:00'),
                    horario_almoco_inicio='12:00', horario_almoco_fim='13:00', escala='5x2'
                )
                db.session.add(pre); count += 1
            db.session.commit()
            flash(f'Importados {count} CPFs.')
        except Exception as e: flash(f'Erro: {e}')
    return render_template('admin/admin_importar_csv.html')

@admin_bp.route('/usuarios')
@login_required
def gerenciar_usuarios():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    users = User.query.all(); pendentes = PreCadastro.query.all()
    return render_template('admin/admin_usuarios.html', users=users, pendentes=pendentes)

@admin_bp.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        try:
            acao = request.form.get('acao')
            if acao == 'excluir':
                if user.username == 'Thaynara': flash('Não é possível excluir o Master.')
                else: 
                    PontoRegistro.query.filter_by(user_id=user.id).delete()
                    PontoResumo.query.filter_by(user_id=user.id).delete()
                    Holerite.query.filter_by(user_id=user.id).delete()
                    db.session.delete(user); db.session.commit()
                return redirect(url_for('admin.gerenciar_usuarios'))
            user.real_name = request.form.get('real_name'); user.role = request.form.get('role')
            user.salario = float(request.form.get('salario') or 0); user.horario_entrada = request.form.get('h_ent')
            user.horario_almoco_inicio = request.form.get('h_alm_ini'); user.horario_almoco_fim = request.form.get('h_alm_fim')
            user.horario_saida = request.form.get('h_sai'); user.escala = request.form.get('escala')
            db.session.commit(); flash('Salvo.'); return redirect(url_for('admin.gerenciar_usuarios'))
        except Exception as e: flash(f'Erro: {e}')
    return render_template('admin/editar_usuario.html', user=user)
"""
    with open(os.path.join(PROJECT_DIR, "app/admin/routes.py"), "w", encoding="utf-8") as f:
        f.write(content_admin)

    log("Correções aplicadas com sucesso.")

def git_operations():
    log("Executando Git Push automático...")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Auto-Fix: DB connection, Template names e Rotas Admin"], check=True)
        subprocess.run(["git", "push"], check=True)
        log("Código enviado para o repositório.")
    except subprocess.CalledProcessError as e:
        log(f"\033[91mErro no Git: {e}\033[0m")

def self_destruct():
    log("Iniciando auto-destruição do script...")
    try:
        os.remove(__file__)
        log("Script deletado.")
    except Exception as e:
        log(f"Erro ao deletar script: {e}")

if __name__ == "__main__":
    create_backup()
    apply_fixes()
    git_operations()
    self_destruct()



from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user, login_user, logout_user
from app.services.empresa_service import EmpresaService
from app.repositories.empresa_repository import EmpresaRepository
from app.utils import super_admin_required
from app.models import User

# 🚀 PREFIXO EXCLUSIVO: Isolando a plataforma Vortice do resto do sistema
super_admin_bp = Blueprint('super_admin', __name__, template_folder='templates', url_prefix='/vortice')

# ==============================================================================
# 🔐 AUTENTICAÇÃO EXCLUSIVA VORTICE (CONTROL PLANE)
# ==============================================================================
@super_admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Porta de entrada secreta e exclusiva para o dono da infraestrutura."""
    # Se já estiver logado e for o dono, manda direto para o painel
    if current_user.is_authenticated and str(current_user.username) == '50097952800':
        return redirect(url_for('super_admin.listar_empresas'))
        
    if request.method == 'POST':
        cpf = request.form.get('cpf')
        senha = request.form.get('senha')
        
        # Bloqueio Brutal: Só a Chave Mestra Absoluta pode tentar o login aqui
        if cpf != '50097952800':
            flash("Acesso restrito. Credenciais inválidas para o portal Vortice.", "error")
            return redirect(url_for('super_admin.login'))
            
        user = User.query.filter_by(username=cpf).first()
        
        if user and user.check_password(senha):
            login_user(user)
            flash("Bem-vindo de volta ao comando, Administrador.", "success")
            return redirect(url_for('super_admin.listar_empresas'))
        else:
            flash("Credenciais inválidas ou senha incorreta.", "error")
            
    return render_template('admin/super_login.html')

@super_admin_bp.route('/logout')
@login_required
def logout():
    """Desconecta do painel global e volta para o login secreto."""
    logout_user()
    return redirect(url_for('super_admin.login'))

# ==============================================================================
# 🌍 GESTÃO GLOBAL DE CLIENTES (SAAS)
# ==============================================================================
@super_admin_bp.route('/empresas', methods=['GET'])
@login_required
@super_admin_required
def listar_empresas():
    repo = EmpresaRepository()
    empresas = repo.get_all()
    return render_template('admin/super_empresas.html', empresas=empresas)

@super_admin_bp.route('/empresas/nova', methods=['POST'])
@login_required
@super_admin_required
def cadastrar_empresa():
    service = EmpresaService()
    
    dados_empresa = {
        'nome': request.form.get('nome_empresa'),
        'plano': request.form.get('plano', 'Standard')
    }
    
    dados_master = {
        'nome_completo': request.form.get('nome_master'),
        'cpf': request.form.get('cpf_master'),
        'senha_provisoria': request.form.get('senha_provisoria', '123456')
    }
    
    try:
        empresa, master = service.criar_nova_conta_cliente(dados_empresa, dados_master)
        flash(f"Sucesso! Empresa '{empresa.nome}' criada. Master: {master.real_name}", "success")
    except ValueError as ve:
        flash(str(ve), "error")
    except Exception as e:
        flash(f"Erro crítico ao criar conta: {e}", "error")
        
    return redirect(url_for('super_admin.listar_empresas'))

@super_admin_bp.route('/empresas/status/<int:id>', methods=['POST'])
@login_required
@super_admin_required
def alterar_status_empresa(id):
    repo = EmpresaRepository()
    empresa = repo.get_by_id(id)
    if empresa:
        empresa.ativa = not empresa.ativa
        repo.commit()
        status = "Ativada" if empresa.ativa else "Bloqueada"
        flash(f"Empresa {empresa.nome} foi {status} com sucesso!", "success")
    return redirect(url_for('super_admin.listar_empresas'))

@super_admin_bp.route('/empresas/branding/<int:id>', methods=['POST'])
@login_required
@super_admin_required
def configurar_branding(id):
    """Rota para processar a mudança de cores e logo de uma empresa específica."""
    service = EmpresaService()
    
    config_visual = {
        'cor_primaria': request.form.get('cor_primaria', '#2563eb'),
        'cor_hover': request.form.get('cor_hover', '#1d4ed8'),
        'logo_url': request.form.get('logo_url', '')
    }
    
    try:
        service.atualizar_branding(id, config_visual)
        flash("Identidade visual atualizada com sucesso!", "success")
    except Exception as e:
        flash(f"Erro ao atualizar branding: {e}", "error")
        
    return redirect(url_for('super_admin.listar_empresas'))


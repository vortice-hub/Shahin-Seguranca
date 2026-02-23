import os
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.services.empresa_service import EmpresaService
from app.repositories.empresa_repository import EmpresaRepository
from app.utils import super_admin_required
from sqlalchemy.orm.attributes import flag_modified
from app.extensions import db

# 🚀 PREFIXO EXCLUSIVO: Isolando a plataforma Vortice do resto do sistema
super_admin_bp = Blueprint('super_admin', __name__, template_folder='templates', url_prefix='/vortice')

# ==============================================================================
# 🔐 AUTENTICAÇÃO DEUS EX MACHINA (SESSÃO INDEPENDENTE)
# ==============================================================================
@super_admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Porta de entrada secreta e exclusiva para o administrador global."""
    if session.get('vortice_admin'):
        return redirect(url_for('super_admin.listar_empresas'))
        
    if request.method == 'POST':
        cpf_tentativa = request.form.get('cpf')
        senha_tentativa = request.form.get('senha')
        
        MASTER_USER = os.environ.get('VORTICE_ADMIN_USER', '50097952800')
        MASTER_PASS = os.environ.get('VORTICE_ADMIN_PASS', 'vortice2026') 
        
        if cpf_tentativa == MASTER_USER and senha_tentativa == MASTER_PASS:
            session['vortice_admin'] = True
            flash("Bem-vindo de volta ao comando, Administrador Vortice.", "success")
            return redirect(url_for('super_admin.listar_empresas'))
        else:
            flash("Acesso negado. Credenciais de infraestrutura inválidas.", "error")
            
    return render_template('admin/super_login.html')

@super_admin_bp.route('/logout')
def logout():
    """Destrói a sessão de infraestrutura."""
    session.pop('vortice_admin', None)
    flash("Sessão de infraestrutura encerrada com segurança.", "success")
    return redirect(url_for('super_admin.login'))

# ==============================================================================
# 🌍 GESTÃO GLOBAL DE CLIENTES E MÓDULOS (SAAS)
# ==============================================================================
@super_admin_bp.route('/empresas', methods=['GET'])
@super_admin_required
def listar_empresas():
    repo = EmpresaRepository()
    empresas = repo.get_all()
    # Garante que features_json é um dicionário para a view
    for emp in empresas:
        if not emp.features_json:
            emp.features_json = {"ponto": True, "documentos": True, "estoque": True}
    return render_template('admin/super_empresas.html', empresas=empresas)

@super_admin_bp.route('/empresas/nova', methods=['POST'])
@super_admin_required
def cadastrar_empresa():
    """Cria nova empresa já processando o logotipo inicial."""
    service = EmpresaService()
    
    file_logo = request.files.get('logo_arquivo')
    
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
        empresa, master = service.criar_nova_conta_cliente(dados_empresa, dados_master, file_logo=file_logo)
        flash(f"Sucesso! Empresa '{empresa.nome}' criada com identidade visual.", "success")
    except ValueError as ve:
        flash(str(ve), "error")
    except Exception as e:
        flash(f"Erro crítico ao criar conta: {e}", "error")
        
    return redirect(url_for('super_admin.listar_empresas'))

@super_admin_bp.route('/empresas/excluir/<int:id>', methods=['POST'])
@super_admin_required
def excluir_empresa(id):
    """Remove permanentemente uma empresa."""
    service = EmpresaService()
    try:
        service.excluir_empresa_completo(id)
        flash("Empresa e todos os dados vinculados foram excluídos permanentemente.", "success")
    except Exception as e:
        flash(f"Erro ao excluir empresa: {e}", "error")
    return redirect(url_for('super_admin.listar_empresas'))

@super_admin_bp.route('/empresas/status/<int:id>', methods=['POST'])
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
@super_admin_required
def configurar_branding(id):
    """Processa o branding capturando ficheiros para o Cloud Storage."""
    service = EmpresaService()
    file_logo = request.files.get('logo_arquivo')
    
    config_visual = {
        'cor_primaria': request.form.get('cor_primaria', '#2563eb'),
        'cor_hover': request.form.get('cor_hover', '#1d4ed8'),
        'logo_url': request.form.get('logo_url', '')
    }
    
    try:
        service.atualizar_branding(id, config_visual, file_logo=file_logo)
        flash("Identidade visual e logotipo atualizados com sucesso!", "success")
    except Exception as e:
        flash(f"Erro ao atualizar branding: {e}", "error")
        
    return redirect(url_for('super_admin.listar_empresas'))

# 🚀 NOVA ROTA: GESTÃO DE MÓDULOS (FEATURE TOGGLING)
@super_admin_bp.route('/empresas/modulos/<int:id>', methods=['POST'])
@super_admin_required
def configurar_modulos(id):
    """Ativa ou desativa módulos específicos para uma empresa."""
    repo = EmpresaRepository()
    empresa = repo.get_by_id(id)
    
    if not empresa:
        flash("Empresa não encontrada.", "error")
        return redirect(url_for('super_admin.listar_empresas'))

    # Se o checkbox for enviado, o request.form terá o valor 'on'. Caso contrário, não existe.
    novos_modulos = {
        "ponto": request.form.get('mod_ponto') == 'on',
        "documentos": request.form.get('mod_documentos') == 'on',
        "estoque": request.form.get('mod_estoque') == 'on'
    }

    try:
        empresa.features_json = novos_modulos
        flag_modified(empresa, "features_json")
        db.session.commit()
        flash(f"Módulos da empresa '{empresa.nome}' atualizados com sucesso!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao atualizar módulos: {e}", "error")

    return redirect(url_for('super_admin.listar_empresas'))


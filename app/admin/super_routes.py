from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.services.empresa_service import EmpresaService
from app.repositories.empresa_repository import EmpresaRepository
from app.utils import super_admin_required

# Blueprint exclusivo para a gestão global da plataforma Vortice
super_admin_bp = Blueprint('super_admin', __name__, template_folder='templates', url_prefix='/admin/super')

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

# 🎨 NOVA ROTA: ATUALIZAR IDENTIDADE VISUAL (WHITE-LABEL)
@super_admin_bp.route('/empresas/branding/<int:id>', methods=['POST'])
@login_required
@super_admin_required
def configurar_branding(id):
    """Rota para processar a mudança de cores e logo de uma empresa específica."""
    service = EmpresaService()
    
    # Captura os dados visuais do formulário
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


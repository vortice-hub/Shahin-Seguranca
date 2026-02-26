import os
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.services.empresa_service import EmpresaService
from app.repositories.empresa_repository import EmpresaRepository
from app.utils import super_admin_required
from sqlalchemy.orm.attributes import flag_modified
from app.extensions import db
from app.services.test_service import TestService

# Importação necessária para buscar os dados do Master
from app.models import User

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
            
        # --- NOVA LÓGICA: Busca os dados do Master para o menu de credenciais ---
        master = User.query.filter_by(empresa_id=emp.id, role='Master').first()
        if master:
            emp.master_nome = master.real_name
            emp.master_cpf = master.cpf or master.username
        else:
            emp.master_nome = "Não cadastrado"
            emp.master_cpf = "N/A"
            
    return render_template('admin/super_empresas.html', empresas=empresas)

@super_admin_bp.route('/empresas/nova', methods=['POST'])
@super_admin_required
def cadastrar_empresa():
    """Cria nova empresa processando o logotipo e as cores iniciais."""
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
        
        # Injeta as cores escolhidas no momento da criação, se fornecidas
        cor_primaria = request.form.get('cor_primaria')
        cor_hover = request.form.get('cor_hover')
        
        if cor_primaria or cor_hover:
            config = dict(empresa.config_json) if empresa.config_json else {}
            if cor_primaria: config['cor_primaria'] = cor_primaria
            if cor_hover: config['cor_hover'] = cor_hover
            empresa.config_json = config
            flag_modified(empresa, "config_json")
            db.session.commit()
            
        # A mensagem agora exibe as credenciais prontas do Terminal!
        flash(f"Empresa '{empresa.nome}' criada! Terminal: terminal_{empresa.slug} | Senha: terminal1234{empresa.slug}", "success")
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
    """Atualiza cores e, opcionalmente, o logotipo."""
    service = EmpresaService()
    file_logo = request.files.get('logo_arquivo')
    
    config_visual = {
        'cor_primaria': request.form.get('cor_primaria', '#2563eb'),
        'cor_hover': request.form.get('cor_hover', '#1d4ed8')
    }
    
    logo_url = request.form.get('logo_url')
    if logo_url and logo_url.strip() != '':
        config_visual['logo_url'] = logo_url.strip()
    
    try:
        service.atualizar_branding(id, config_visual, file_logo=file_logo)
        flash("Identidade visual e logotipo atualizados com sucesso!", "success")
    except Exception as e:
        flash(f"Erro ao atualizar branding: {e}", "error")
        
    return redirect(url_for('super_admin.listar_empresas'))

@super_admin_bp.route('/empresas/modulos/<int:id>', methods=['POST'])
@super_admin_required
def configurar_modulos(id):
    """Ativa ou desativa módulos específicos para uma empresa."""
    repo = EmpresaRepository()
    empresa = repo.get_by_id(id)
    
    if not empresa:
        flash("Empresa não encontrada.", "error")
        return redirect(url_for('super_admin.listar_empresas'))

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

# ==============================================================================
# 🧪 VORTICE LABS: TESTES AUTOMATIZADOS DE INTEGRIDADE
# ==============================================================================

@super_admin_bp.route('/labs/audit', methods=['POST'])
@super_admin_required
def run_labs_audit():
    """Aciona o robô de testes para validar isolamento e funções do sistema."""
    tester = TestService()
    resultados = tester.run_full_audit()
    return jsonify({'logs': resultados})

@super_admin_bp.route('/labs/cleanup', methods=['POST'])
@super_admin_required
def run_labs_cleanup():
    """Remove instantaneamente todas as empresas de teste geradas."""
    tester = TestService()
    sucesso = tester.cleanup_tests()
    if sucesso:
        flash("Ambiente de teste limpo com sucesso!", "success")
    else:
        flash("Erro ao limpar dados de teste.", "error")
    return redirect(url_for('super_admin.listar_empresas'))


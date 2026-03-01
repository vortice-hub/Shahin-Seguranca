from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from app.extensions import db
from app.models import User, PreCadastro, Empresa
from app.repositories.empresa_repository import EmpresaRepository
import re
import random
import string

auth_bp = Blueprint('auth', __name__, template_folder='templates')

# ==============================================================================
# 🔐 PORTAL DE LOGIN CAMALEÃO (WHITE-LABEL E HÍBRIDO)
# ==============================================================================
@auth_bp.route('/login', methods=['GET', 'POST'])
@auth_bp.route('/login/<slug>', methods=['GET', 'POST'])
def login(slug=None):
    if current_user.is_authenticated: 
        return redirect(url_for('main.dashboard'))
    
    empresa_login = None
    if slug:
        repo = EmpresaRepository()
        empresa_login = repo.get_by_slug(slug)
        if not empresa_login or not empresa_login.ativa:
            flash('Portal de cliente não encontrado ou desativado.', 'error')
            return redirect(url_for('auth.login'))
        
        # Injeta a empresa no contexto global para cores dinâmicas no template
        g.empresa = empresa_login
    
    if request.method == 'POST':
        raw_input = request.form.get('username', '').strip()
        password = request.form.get('password')
        
        # CORREÇÃO: Limpa formatação solta, mas preserva o underscore (_) do terminal e formatos de e-mail
        username = re.sub(r'[^0-9a-zA-Z_@.-]', '', raw_input)
        
        user = User.query.filter_by(username=username).first()
        if not user:
            # Tenta por CPF
            user = User.query.filter_by(cpf=username).first()
            
        if user and user.check_password(password):
            # Se o login foi por slug, verifica se o user pertence a essa empresa
            if slug and user.empresa_id != empresa_login.id and user.role != 'Master':
                flash('Acesso negado: Utilizador não pertence a esta empresa.', 'error')
                return redirect(url_for('auth.login', slug=slug))
                
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        else:
            flash('Utilizador ou senha incorretos.', 'error')
            
    return render_template('auth/login.html', empresa_login=empresa_login)

@auth_bp.route('/logout')
@login_required
def logout():
    # Guarda a empresa antes de apagar a sessão para não perder a cor/logo
    slug = g.empresa.slug if hasattr(g, 'empresa') and g.empresa else None
    logout_user()
    if slug:
        return redirect(url_for('auth.login', slug=slug))
    return redirect(url_for('auth.login'))

@auth_bp.route('/primeiro-acesso', methods=['GET', 'POST'])
@login_required
def primeiro_acesso():
    if not current_user.is_first_access:
        return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        confirmacao = request.form.get('confirmacao')
        
        if nova_senha != confirmacao:
            flash('As senhas não coincidem. Tente novamente.', 'error')
            return redirect(url_for('auth.primeiro_acesso'))
            
        if len(nova_senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'error')
            return redirect(url_for('auth.primeiro_acesso'))
            
        current_user.set_password(nova_senha)
        current_user.is_first_access = False
        
        # --- CEREBRO: Guarda o slug ANTES de fazer logout ---
        slug = g.empresa.slug if hasattr(g, 'empresa') and g.empresa else None
        
        db.session.commit()
        logout_user()
        flash('Senha registada com sucesso! Faça o login para continuar.', 'success')
        
        # --- Redirecionamento Inteligente para o portal correto ---
        if slug:
            return redirect(url_for('auth.login', slug=slug))
        return redirect(url_for('auth.login'))
        
    return render_template('auth/primeiro_acesso.html')
    
@auth_bp.route('/auto-cadastro', methods=['GET', 'POST'])
def auto_cadastro():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
        
    step = request.args.get('step', 1, type=int)
    cpf = request.args.get('cpf', '')
    
    if request.method == 'POST':
        cpf_input = request.form.get('cpf', '').replace('.', '').replace('-', '').strip()
        pre = PreCadastro.query.filter_by(cpf=cpf_input).first()
        
        if not pre:
            flash('CPF não encontrado no sistema. Contacte os Recursos Humanos.', 'error')
            return redirect(url_for('auth.auto_cadastro'))
            
        email = request.form.get('email')
        senha = request.form.get('senha')
        confirma = request.form.get('confirmacao')
        
        if not email or not senha:
            return redirect(url_for('auth.auto_cadastro', step=2, cpf=cpf_input))
            
        if senha != confirma:
            flash('Senhas não coincidem.', 'error')
            return redirect(url_for('auth.auto_cadastro', step=2, cpf=cpf_input))
            
        novo_user = User(
            username=cpf_input,
            cpf=cpf_input,
            email=email,
            real_name=pre.nome_previsto,
            role=pre.cargo,
            departamento=pre.departamento,
            gestor_id=pre.gestor_id,
            salario=pre.salario,
            razao_social_empregadora=pre.razao_social,
            cnpj_empregador=pre.cnpj,
            data_admissao=pre.data_admissao,
            carga_horaria=pre.carga_horaria,
            tempo_intervalo=pre.tempo_intervalo,
            inicio_jornada_ideal=pre.inicio_jornada_ideal,
            escala=pre.escala,
            data_inicio_escala=pre.data_inicio_escala,
            is_first_access=False,
            empresa_id=pre.empresa_id
        )
        novo_user.set_password(senha)
        
        db.session.add(novo_user)
        db.session.delete(pre) 
        db.session.commit()
        
        return render_template('auth/auto_cadastro_sucesso.html', username=cpf_input, nome=pre.nome_previsto)
        
    if step == 2 and cpf:
        pre = PreCadastro.query.filter_by(cpf=cpf).first()
        if pre:
            return render_template('auth/auto_cadastro.html', step=2, cpf=cpf, nome=pre.nome_previsto)
            
    return render_template('auth/auto_cadastro.html', step=1)

@auth_bp.route('/esqueci-senha', methods=['GET', 'POST'])
def esqueci_senha():
    if current_user.is_authenticated: 
        return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        cpf_input = request.form.get('cpf', '').replace('.', '').replace('-', '').strip()
        data_admissao_input = request.form.get('data_admissao')
        
        user = User.query.filter_by(cpf=cpf_input).first()
        
        if user and user.data_admissao and str(user.data_admissao) == data_admissao_input:
            senha_temporaria = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            user.set_password(senha_temporaria)
            user.is_first_access = True
            
            # Puxa a empresa do user para redirecionar corretamente
            slug = None
            if user.empresa_id:
                empresa = Empresa.query.get(user.empresa_id)
                if empresa: slug = empresa.slug
                
            db.session.commit()
            
            flash(f'ACESSO RECUPERADO! Sua senha temporária é: {senha_temporaria}', 'success')
            
            if slug:
                return redirect(url_for('auth.login', slug=slug))
            return redirect(url_for('auth.login'))
        else:
            flash('Dados não conferem. Verifique o CPF e a Data de Admissão.', 'error')
            
    return render_template('auth/esqueci_senha.html')


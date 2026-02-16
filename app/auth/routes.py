from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from app.extensions import db
from app.models import User, PreCadastro
import re

auth_bp = Blueprint('auth', __name__, template_folder='templates')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: 
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        # O campo 'username' agora receberá o CPF digitado pelo utilizador
        login_input = request.form.get('username', '').replace('.', '').replace('-', '').strip()
        password = request.form.get('password')
        
        # Procura pelo username (que para funcionários será o CPF e para Thaynara será o nome)
        user = User.query.filter_by(username=login_input).first()
        
        # Caso não encontre pelo CPF limpo, tenta procurar pelo input original (para casos como 'Thaynara')
        if not user:
            user = User.query.filter_by(username=request.form.get('username')).first()

        if user and user.check_password(password):
            login_user(user)
            if user.is_first_access: 
                return redirect(url_for('auth.primeiro_acesso'))
            return redirect(url_for('main.dashboard'))
        
        flash('CPF ou senha inválidos.', 'error')
        
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/primeiro-acesso', methods=['GET', 'POST'])
@login_required
def primeiro_acesso():
    if not current_user.is_first_access: 
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        confirmacao = request.form.get('confirmacao')
        
        if nova_senha == confirmacao:
            current_user.set_password(nova_senha)
            current_user.is_first_access = False
            db.session.commit()
            flash('Senha atualizada com sucesso!', 'success')
            return redirect(url_for('main.dashboard'))
        flash('As senhas não coincidem.', 'error')
        
    return render_template('auth/primeiro_acesso.html')

@auth_bp.route('/cadastrar', methods=['GET', 'POST'])
def auto_cadastro():
    if request.method == 'GET': 
        return render_template('auth/auto_cadastro.html', step=1)
    
    if request.method == 'POST':
        cpf_input = request.form.get('cpf', '')
        cpf = re.sub(r'\D', '', cpf_input) # Mantém apenas números
        
        pre = PreCadastro.query.filter_by(cpf=cpf).first()
        
        if not pre:
            if User.query.filter_by(cpf=cpf).first():
                flash('Este CPF já possui um cadastro ativo. Tente fazer login.', 'warning')
                return redirect(url_for('auth.login'))
            flash('CPF não autorizado para cadastro. Entre em contacto com o RH.', 'error')
            return redirect(url_for('auth.auto_cadastro'))
            
        password = request.form.get('password')
        if password:
            # O LOGIN AGORA É O PRÓPRIO CPF
            username_login = cpf 
            
            novo_user = User(
                username=username_login, 
                password_hash=generate_password_hash(password), 
                real_name=pre.nome_previsto, 
                role=pre.cargo, 
                cpf=cpf, 
                salario=pre.salario, 
                razao_social_empregadora=pre.razao_social,
                cnpj_empregador=pre.cnpj,
                carga_horaria=pre.carga_horaria,
                tempo_intervalo=pre.tempo_intervalo,
                inicio_jornada_ideal=pre.inicio_jornada_ideal,
                escala=pre.escala, 
                data_inicio_escala=pre.data_inicio_escala, 
                is_first_access=False,
                permissions="" # Cadastro inicial sempre sem permissões administrativas
            )
            
            db.session.add(novo_user)
            db.session.delete(pre) # Remove da lista de pré-cadastro
            db.session.commit()
            
            return render_template('auth/auto_cadastro_sucesso.html', username=cpf, nome=pre.nome_previsto)
        else:
            return render_template('auth/auto_cadastro.html', step=2, cpf=cpf, nome=pre.nome_previsto)



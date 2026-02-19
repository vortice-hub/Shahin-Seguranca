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
        login_input = request.form.get('username', '').replace('.', '').replace('-', '').strip()
        password = request.form.get('password')
        
        user = User.query.filter_by(username=login_input).first()
        
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
        cpf = re.sub(r'\D', '', cpf_input)
        
        pre = PreCadastro.query.filter_by(cpf=cpf).first()
        
        if not pre:
            if User.query.filter_by(cpf=cpf).first():
                flash('Este CPF já possui um cadastro ativo. Tente fazer login.', 'warning')
                return redirect(url_for('auth.login'))
            flash('CPF não autorizado para cadastro. Entre em contacto com o RH.', 'error')
            return redirect(url_for('auth.auto_cadastro'))
            
        password = request.form.get('password')
        if password:
            username_login = cpf 
            
            # MAGICA DO VÍNCULO: Procura o gestor pelo CPF informado na planilha
            gestor_id_final = None
            if pre.cpf_gestor:
                gestor_encontrado = User.query.filter_by(cpf=pre.cpf_gestor).first()
                if gestor_encontrado:
                    gestor_id_final = gestor_encontrado.id
            
            novo_user = User(
                username=username_login, 
                password_hash=generate_password_hash(password), 
                real_name=pre.nome_previsto, 
                role=pre.cargo, 
                cpf=cpf, 
                salario=pre.salario, 
                razao_social_empregadora=pre.razao_social,
                cnpj_empregador=pre.cnpj,
                data_admissao=pre.data_admissao, # Correção: Migrando a data de admissão
                carga_horaria=pre.carga_horaria,
                tempo_intervalo=pre.tempo_intervalo,
                inicio_jornada_ideal=pre.inicio_jornada_ideal,
                escala=pre.escala, 
                data_inicio_escala=pre.data_inicio_escala,
                departamento=pre.departamento, # Correção: Migrando a equipe
                gestor_id=gestor_id_final, # Correção: Transformando CPF do chefe em ID
                is_first_access=False,
                permissions="" 
            )
            
            db.session.add(novo_user)
            db.session.delete(pre) 
            db.session.commit()
            
            return render_template('auth/auto_cadastro_sucesso.html', username=cpf, nome=pre.nome_previsto)
        else:
            return render_template('auth/auto_cadastro.html', step=2, cpf=cpf, nome=pre.nome_previsto)


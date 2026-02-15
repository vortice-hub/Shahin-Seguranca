from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from app import db
from app.models import User, PreCadastro
from app.utils import gerar_login_automatico

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user)
            if user.is_first_access: return redirect(url_for('auth.primeiro_acesso'))
            return redirect(url_for('main.dashboard'))
        flash('Credenciais inválidas.')
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/primeiro-acesso', methods=['GET', 'POST'])
@login_required
def primeiro_acesso():
    if not current_user.is_first_access: return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        if request.form.get('nova_senha') == request.form.get('confirmacao'):
            current_user.set_password(request.form.get('nova_senha'))
            current_user.is_first_access = False
            db.session.commit()
            return redirect(url_for('main.dashboard'))
        flash('Senhas não conferem.')
    return render_template('primeiro_acesso.html')

@auth_bp.route('/cadastrar', methods=['GET', 'POST'])
def auto_cadastro():
    if request.method == 'GET': return render_template('auto_cadastro.html', step=1)
    if request.method == 'POST':
        cpf = request.form.get('cpf').replace('.', '').replace('-', '').strip()
        pre = PreCadastro.query.filter_by(cpf=cpf).first()
        if not pre:
            if User.query.filter_by(cpf=cpf).first():
                flash('Você já tem cadastro. Faça login.')
                return redirect(url_for('auth.login'))
            flash('CPF não encontrado na lista de liberação.')
            return redirect(url_for('auth.auto_cadastro'))
            
        password = request.form.get('password')
        if password:
            username = gerar_login_automatico(pre.nome_previsto)
            while User.query.filter_by(username=username).first(): username = gerar_login_automatico(pre.nome_previsto)
            novo_user = User(username=username, password_hash=generate_password_hash(password), real_name=pre.nome_previsto, role=pre.cargo, cpf=cpf, salario=pre.salario, horario_entrada=pre.horario_entrada, horario_almoco_inicio=pre.horario_almoco_inicio, horario_almoco_fim=pre.horario_almoco_fim, horario_saida=pre.horario_saida, escala=pre.escala, data_inicio_escala=pre.data_inicio_escala, is_first_access=False)
            db.session.add(novo_user); db.session.delete(pre); db.session.commit()
            return render_template('auto_cadastro_sucesso.html', username=username, nome=pre.nome_previsto)
        else:
            return render_template('auto_cadastro.html', step=2, cpf=cpf, nome=pre.nome_previsto)
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, text
import io
import logging
import random
import string
from datetime import time, datetime, date
import pandas as pd 

# Importações do Projeto
from app.extensions import db
from app.models import User, PreCadastro, PontoResumo, PontoAjuste, PontoRegistro, Holerite, Recibo, ConfiguracaoEmpresa
from app.utils import (
    calcular_dia, 
    get_brasil_time, 
    format_minutes_to_hm, 
    time_to_minutes,
    gerar_login_automatico,
    master_required,
    permission_required
)

admin_bp = Blueprint('admin', __name__, template_folder='templates', url_prefix='/admin')
logger = logging.getLogger(__name__)

# --- GESTÃO DE UTILIZADORES ---

@admin_bp.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
@permission_required('USUARIOS')
def novo_usuario():
    gestores = User.query.filter(User.username != '12345678900', User.username != 'terminal').order_by(User.real_name).all()
    
    if request.method == 'POST':
        try:
            real_name = request.form.get('real_name')
            cpf = request.form.get('cpf', '').replace('.', '').replace('-', '').strip()
            
            if not real_name or not cpf:
                flash('Nome e CPF são obrigatórios.', 'error')
                return redirect(url_for('admin.novo_usuario'))

            if User.query.filter_by(cpf=cpf).first() or PreCadastro.query.filter_by(cpf=cpf).first():
                flash('CPF já cadastrado!', 'error')
                return redirect(url_for('admin.novo_usuario'))

            dt_adm_str = request.form.get('data_admissao')
            dt_admissao = datetime.strptime(dt_adm_str, '%Y-%m-%d').date() if dt_adm_str else None

            carga_hm = request.form.get('carga_horaria') or '08:48'
            carga_minutos = time_to_minutes(carga_hm)
            intervalo_min = int(request.form.get('tempo_intervalo') or 60)
            
            cpf_gestor = request.form.get('cpf_gestor', '').replace('.', '').replace('-', '').strip()

            novo_pre = PreCadastro(
                cpf=cpf,
                nome_previsto=real_name,
                cargo=request.form.get('role'),
                departamento=request.form.get('departamento'),
                cpf_gestor=cpf_gestor if cpf_gestor else None,
                salario=float(request.form.get('salario') or 0),
                razao_social=request.form.get('razao_social'),
                cnpj=request.form.get('cnpj'),
                data_admissao=dt_admissao,
                carga_horaria=carga_minutos,
                tempo_intervalo=intervalo_min,
                inicio_jornada_ideal=request.form.get('h_ent') or '08:00',
                escala=request.form.get('escala'),
                data_inicio_escala=request.form.get('dt_escala') if request.form.get('dt_escala') else None
            )
            
            db.session.add(novo_pre)
            db.session.commit()
            return render_template('admin/sucesso_usuario.html', nome_real=real_name, cpf=cpf)
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro interno: {str(e)}', 'error')
            
    return render_template('admin/novo_usuario.html', gestores=gestores)

@admin_bp.route('/usuarios')
@login_required
def gerenciar_usuarios():
    from app.utils import has_permission
    if not has_permission('USUARIOS'):
        flash('Sem acesso à gestão de utilizadores.', 'error')
        return redirect(url_for('main.dashboard'))

    page = request.args.get('page', 1, type=int)
    users_pagination = User.query.filter(
        User.username != '12345678900', 
        User.username != 'terminal'
    ).order_by(User.real_name).paginate(page=page, per_page=15, error_out=False)
    
    pendentes = PreCadastro.query.order_by(PreCadastro.nome_previsto).all()
    
    return render_template('admin/admin_usuarios.html', users_pagination=users_pagination, pendentes=pendentes)

@admin_bp.route('/liberar-acesso/excluir/<int:id>', methods=['GET'])
@login_required
@permission_required('USUARIOS')
def excluir_pre_cadastro(id):
    pre_cadastro = PreCadastro.query.get_or_404(id)
    try:
        nome = pre_cadastro.nome_previsto
        db.session.delete(pre_cadastro)
        db.session.commit()
        flash(f'O pré-cadastro de {nome} foi removido com sucesso.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {str(e)}', 'error')
    return redirect(url_for('admin.gerenciar_usuarios'))

@admin_bp.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    from app.utils import has_permission
    if not has_permission('USUARIOS'):
        flash('Sem acesso.', 'error')
        return redirect(url_for('main.dashboard'))

    user = User.query.get_or_404(id)
    user_carga_hm = format_minutes_to_hm(user.carga_horaria or 528)
    gestores = User.query.filter(User.username != '12345678900', User.username != 'terminal', User.id != user.id).order_by(User.real_name).all()
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        try:
            if acao == 'excluir':
                if user.username == '50097952800' or user.username == 'Thaynara':
                    flash('Impossível excluir Master.', 'error')
                else: 
                    subordinados = User.query.filter_by(gestor_id=user.id).all()
                    for sub in subordinados: sub.gestor_id = None
                    PontoRegistro.query.filter_by(user_id=user.id).delete()
                    PontoResumo.query.filter_by(user_id=user.id).delete()
                    Holerite.query.filter_by(user_id=user.id).delete()
                    Recibo.query.filter_by(user_id=user.id).delete()
                    db.session.delete(user)
                    db.session.commit()
                    flash('Utilizador excluído.', 'success')
                    return redirect(url_for('admin.gerenciar_usuarios'))

            elif acao == 'salvar':
                user.real_name = request.form.get('real_name')
                user.role = request.form.get('role')
                user.departamento = request.form.get('departamento')
                gestor_req = request.form.get('gestor_id')
                user.gestor_id = int(gestor_req) if gestor_req else None
                user.salario = float(request.form.get('salario') or 0)
                user.razao_social_empregadora = request.form.get('razao_social')
                user.cnpj_empregador = request.form.get('cnpj')
                
                dt_adm_str = request.form.get('data_admissao')
                if dt_adm_str: user.data_admissao = datetime.strptime(dt_adm_str, '%Y-%m-%d').date()
                
                user.carga_horaria = time_to_minutes(request.form.get('carga_horaria'))
                user.tempo_intervalo = int(request.form.get('tempo_intervalo') or 60)
                user.inicio_jornada_ideal = request.form.get('h_ent')
                user.escala = request.form.get('escala')
                if request.form.get('dt_escala'): user.data_inicio_escala = request.form.get('dt_escala')

                if user.username != '50097952800' and user.username != 'Thaynara':
                    lista_perms = request.form.getlist('perm_keys')
                    user.permissions = ",".join(lista_perms)
                
                db.session.commit()
                flash('Dados atualizados com sucesso.', 'success')
                return redirect(url_for('admin.gerenciar_usuarios'))
                
            elif acao == 'resetar_senha':
                senha_temporaria = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                user.set_password(senha_temporaria)
                user.is_first_access = True
                db.session.commit()
                flash(f'Senha resetada! Nova senha: {senha_temporaria}', 'success')
                
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {e}', 'error')

    return render_template('admin/editar_usuario.html', user=user, carga_hm=user_carga_hm, gestores=gestores)

@admin_bp.route('/solicitacoes', methods=['GET', 'POST'])
@login_required
@permission_required('PONTO') 
def admin_solicitacoes():
    if request.method == 'POST':
        solic = PontoAjuste.query.get(request.form.get('solic_id'))
        if solic:
            if request.form.get('decisao') == 'aprovar':
                solic.status = 'Aprovado'
                try:
                    if solic.tipo_solicitacao == 'Edicao' and solic.ponto_original_id:
                        reg = PontoRegistro.query.get(solic.ponto_original_id)
                        if reg:
                            h, m = map(int, solic.novo_horario.split(':'))
                            reg.hora_registro = time(h, m)
                            reg.tipo = solic.tipo_batida
                    elif solic.tipo_solicitacao == 'Inclusao':
                        h, m = map(int, solic.novo_horario.split(':'))
                        novo_ponto = PontoRegistro(user_id=solic.user_id, data_registro=solic.data_referencia, hora_registro=time(h, m), tipo=solic.tipo_batida, latitude='Ajuste Manual', longitude='Aprovado pelo Master')
                        db.session.add(novo_ponto)
                    elif solic.tipo_solicitacao == 'Exclusao' and solic.ponto_original_id:
                        reg = PontoRegistro.query.get(solic.ponto_original_id)
                        if reg: db.session.delete(reg)

                    db.session.flush()
                    calcular_dia(solic.user_id, solic.data_referencia)
                    flash('Aprovado.', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Erro: {e}', 'error')
            else:
                solic.status = 'Reprovado'
                solic.motivo_reprovacao = request.form.get('motivo_repro')
                flash('Reprovado.', 'warning')
            db.session.commit()
            
    extras = {}
    solicitacoes_pendentes = PontoAjuste.query.filter_by(status='Pendente').order_by(PontoAjuste.created_at.desc()).all()
    for s in solicitacoes_pendentes:
        if s.ponto_original_id:
            p_original = PontoRegistro.query.get(s.ponto_original_id)
            if p_original: extras[s.id] = p_original.hora_registro.strftime('%H:%M')
    return render_template('admin/solicitacoes.html', solicitacoes=solicitacoes_pendentes, extras=extras)

@admin_bp.route('/configuracoes', methods=['GET', 'POST'])
@login_required
@master_required
def configuracoes_sistema():
    config = ConfiguracaoEmpresa.query.get(1)
    if not config:
        config = ConfiguracaoEmpresa(id=1, token_seguranca_task='shahin_secret_token_123')
        db.session.add(config)
        db.session.commit()

    if request.method == 'POST':
        try:
            config.dia_cobranca_ponto = int(request.form.get('dia_ponto', 1))
            config.dia_cobranca_holerite = int(request.form.get('dia_holerite', 5))
            db.session.commit()
            flash('Configurações de automação atualizadas!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao salvar: {e}', 'error')

    return render_template('admin/configuracoes.html', config=config)


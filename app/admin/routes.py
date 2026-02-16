from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, text
import csv
import io
import logging

# Importações do Projeto
from app.extensions import db
from app.models import User, PreCadastro, PontoResumo, PontoAjuste, PontoRegistro, Holerite, Recibo
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

            carga_hm = request.form.get('carga_horaria') or '08:48'
            carga_minutos = time_to_minutes(carga_hm)
            intervalo_min = int(request.form.get('tempo_intervalo') or 60)

            novo_pre = PreCadastro(
                cpf=cpf,
                nome_previsto=real_name,
                cargo=request.form.get('role'),
                salario=float(request.form.get('salario') or 0),
                razao_social=request.form.get('razao_social'),
                cnpj=request.form.get('cnpj'),
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
            
    return render_template('admin/novo_usuario.html')

@admin_bp.route('/usuarios')
@login_required
def gerenciar_usuarios():
    from app.utils import has_permission
    if not has_permission('USUARIOS'):
        flash('Sem acesso à gestão de utilizadores.', 'error')
        return redirect(url_for('main.dashboard'))

    # FILTRO APLICADO AQUI: Remove o Terminal (CPF e nome antigo) da lista
    users = User.query.filter(User.username != '12345678900', User.username != 'terminal').order_by(User.real_name).all()
    
    pendentes = PreCadastro.query.order_by(PreCadastro.nome_previsto).all()
    return render_template('admin/admin_usuarios.html', users=users, pendentes=pendentes)

@admin_bp.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    from app.utils import has_permission
    if not has_permission('USUARIOS'):
        flash('Sem acesso.', 'error')
        return redirect(url_for('main.dashboard'))

    user = User.query.get_or_404(id)
    user_carga_hm = format_minutes_to_hm(user.carga_horaria or 528)
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        try:
            if acao == 'excluir':
                # Proteção extra para o Master (CPF) e o antigo Thaynara
                if user.username == '50097952800' or user.username == 'Thaynara': 
                    flash('Impossível excluir Master.', 'error')
                else: 
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
                user.salario = float(request.form.get('salario') or 0)
                user.razao_social_empregadora = request.form.get('razao_social')
                user.cnpj_empregador = request.form.get('cnpj')
                
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
                user.set_password('mudar123')
                user.is_first_access = True
                db.session.commit()
                flash('Senha resetada.', 'warning')
                
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {e}', 'error')

    return render_template('admin/editar_usuario.html', user=user, carga_hm=user_carga_hm)

@admin_bp.route('/usuarios/importar-csv', methods=['GET', 'POST'])
@login_required
@permission_required('USUARIOS')
def importar_csv():
    if request.method == 'POST':
        file = request.files.get('arquivo_csv')
        if not file: return redirect(url_for('admin.importar_csv'))
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream, delimiter=';')
            count = 0
            for row in csv_reader:
                cpf = row.get('CPF', '').replace('.', '').replace('-', '').strip()
                if not cpf: continue
                if PreCadastro.query.filter_by(cpf=cpf).first() or User.query.filter_by(cpf=cpf).first(): continue
                
                pre = PreCadastro(
                    cpf=cpf, nome_previsto=row.get('Nome', 'Funcionario'), cargo=row.get('Cargo', 'Colaborador'),
                    salario=float(row.get('Salario', 0).replace(',', '.') or 0),
                    razao_social="LA SHAHIN SERVIÇOS DE SEGURANÇA E PRONTA RESPOSTA LTDA", cnpj="50.537.235/0001-95",
                    carga_horaria=528, tempo_intervalo=60, inicio_jornada_ideal=row.get('Entrada', '07:12')
                )
                db.session.add(pre)
                count += 1
            db.session.commit()
            flash(f'{count} importados com sucesso.')
        except Exception as e: flash(f'Erro: {e}')
    return render_template('admin/admin_importar_csv.html')

@admin_bp.route('/liberar-acesso', methods=['POST'])
@login_required
@permission_required('USUARIOS')
def liberar_acesso():
    try:
        cpf = request.form.get('cpf', '').replace('.', '').replace('-', '').strip()
        if User.query.filter_by(cpf=cpf).first() or PreCadastro.query.filter_by(cpf=cpf).first(): flash('CPF já existe.', 'error')
        else:
            novo = PreCadastro(
                cpf=cpf, nome_previsto=request.form.get('nome'), cargo=request.form.get('cargo'),
                salario=float(request.form.get('salario') or 0),
                razao_social=request.form.get('razao_social'), cnpj=request.form.get('cnpj'),
                carga_horaria=528, tempo_intervalo=60, inicio_jornada_ideal=request.form.get('h_ent') or '08:00',
                escala=request.form.get('escala'), data_inicio_escala=request.form.get('dt_escala') if request.form.get('dt_escala') else None
            )
            db.session.add(novo)
            db.session.commit()
            flash('Acesso liberado.', 'success')
    except Exception as e: flash(f'Erro: {e}', 'error')
    return redirect(url_for('admin.gerenciar_usuarios'))

@admin_bp.route('/liberar-acesso/excluir/<int:id>')
@login_required
@permission_required('USUARIOS')
def excluir_liberacao(id):
    pre = PreCadastro.query.get(id)
    if pre: db.session.delete(pre); db.session.commit(); flash('Removido.')
    return redirect(url_for('admin.gerenciar_usuarios'))

@admin_bp.route('/solicitacoes', methods=['GET', 'POST'])
@login_required
@permission_required('PONTO')
def admin_solicitacoes():
    if request.method == 'POST':
        solic = PontoAjuste.query.get(request.form.get('solic_id'))
        if solic:
            if request.form.get('decisao') == 'aprovar': solic.status = 'Aprovado'; flash('Aprovado.', 'success')
            else: solic.status = 'Reprovado'; solic.motivo_reprovacao = request.form.get('motivo_repro'); flash('Reprovado.', 'warning')
            db.session.commit()
    return render_template('admin/solicitacoes.html', solicitacoes=PontoAjuste.query.filter_by(status='Pendente').order_by(PontoAjuste.created_at.desc()).all(), extras={})

@admin_bp.route('/ferramentas/limpeza', methods=['GET', 'POST'])
@login_required
@master_required
def admin_limpeza():
    if request.method == 'POST':
        acao = request.form.get('acao')
        try:
            if acao == 'limpar_testes_ponto': 
                PontoRegistro.query.delete()
                PontoResumo.query.delete()
            elif acao == 'limpar_holerites': 
                Holerite.query.delete()
                Recibo.query.delete()
            elif acao == 'limpar_usuarios_nao_master': 
                # Protege o Master CPF e o antigo Thaynara
                User.query.filter(User.username != '50097952800', User.username != 'Thaynara').delete()
                PreCadastro.query.delete()
            db.session.commit()
            return redirect(url_for('admin.admin_limpeza'))
        except: db.session.rollback()
    return render_template('admin/admin_limpeza.html')

@admin_bp.route('/sistema/atualizar-banco-neon', methods=['GET'])
@login_required
@master_required
def patch_banco_dados():
    return "Banco de dados já configurado."
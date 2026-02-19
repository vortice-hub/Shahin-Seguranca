from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, text
import io
import logging
from datetime import time, datetime, date
import pandas as pd 

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
    # Busca todos os utilizadores para listar como possíveis gestores no formulário
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
            
            # Captura a Estrutura Organizacional
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

    # NOVO: Puxa o número da página da URL (ex: ?page=2), por padrão é a 1
    page = request.args.get('page', 1, type=int)
    
    # NOVO: O '.paginate()' quebra o banco de dados em lotes de 15 funcionários
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
        flash(f'O pré-cadastro de {nome} foi removido com sucesso da fila.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao tentar remover: {str(e)}', 'error')
    
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
    
    # Lista de gestores (excluindo a própria pessoa para ela não ser chefe de si mesma)
    gestores = User.query.filter(User.username != '12345678900', User.username != 'terminal', User.id != user.id).order_by(User.real_name).all()
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        try:
            if acao == 'excluir':
                if user.username == '50097952800' or user.username == 'Thaynara':
                    flash('Impossível excluir Master.', 'error')
                else: 
                    # Desvincula quem era subordinado desta pessoa antes de apagar
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
                
                # Salvando Estrutura Organizacional
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
                user.set_password('mudar123')
                user.is_first_access = True
                db.session.commit()
                flash('Senha resetada.', 'warning')
                
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
                    flash('Aprovado e refletido no espelho.', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Erro ao aplicar ajuste: {e}', 'error')
                    return redirect(url_for('admin.admin_solicitacoes'))
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
                User.query.filter(User.username != '50097952800', User.username != 'Thaynara').delete()
                PreCadastro.query.delete()
            db.session.commit()
            return redirect(url_for('admin.admin_limpeza'))
        except: db.session.rollback()
    return render_template('admin/admin_limpeza.html')

# --- LEITOR INTELIGENTE DE EXCEL NATIVO ---
@admin_bp.route('/usuarios/importar-excel', methods=['POST'])
@login_required
@permission_required('USUARIOS')
def importar_excel_usuarios():
    if 'arquivo_excel' not in request.files:
        flash('Nenhum arquivo enviado.', 'error')
        return redirect(url_for('admin.gerenciar_usuarios'))
    
    file = request.files['arquivo_excel']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('admin.gerenciar_usuarios'))
        
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Formato inválido. Por favor, envie uma planilha real do Excel (.xlsx ou .xls)', 'error')
        return redirect(url_for('admin.gerenciar_usuarios'))

    try:
        df = pd.read_excel(file)
        df = df.fillna('') 
        df.columns = [str(c).strip().lower() for c in df.columns] 
        
        records = df.to_dict('records') 
        sucesso, falhas = 0, 0
        
        for row in records:
            nome = str(row.get('nome', '')).strip()
            
            cpf_raw = str(row.get('cpf', '')).replace('.', '').replace('-', '').strip()
            if cpf_raw.endswith('.0'): cpf_raw = cpf_raw[:-2]
            cpf = cpf_raw
            
            cargo = str(row.get('cargo', '')).strip()
            
            # Captura a Estrutura Organizacional vinda do Excel
            departamento = str(row.get('departamento', '')).strip()
            cpf_gestor_raw = str(row.get('cpf_gestor', '')).replace('.', '').replace('-', '').strip()
            if cpf_gestor_raw.endswith('.0'): cpf_gestor_raw = cpf_gestor_raw[:-2]
            
            if not nome or not cpf:
                falhas += 1
                continue
                
            if User.query.filter_by(cpf=cpf).first() or PreCadastro.query.filter_by(cpf=cpf).first():
                falhas += 1
                continue

            dt_admissao = None
            dt_adm_raw = row.get('data_admissao', '')
            if dt_adm_raw:
                if isinstance(dt_adm_raw, (datetime, date)):
                    dt_admissao = dt_adm_raw if isinstance(dt_adm_raw, date) else dt_adm_raw.date()
                elif isinstance(dt_adm_raw, pd.Timestamp):
                    dt_admissao = dt_adm_raw.date()
                else:
                    dt_adm_str = str(dt_adm_raw).strip()
                    if ' ' in dt_adm_str: dt_adm_str = dt_adm_str.split(' ')[0]
                    try:
                        if '/' in dt_adm_str: dt_admissao = datetime.strptime(dt_adm_str, '%d/%m/%Y').date()
                        else: dt_admissao = datetime.strptime(dt_adm_str, '%Y-%m-%d').date()
                    except ValueError: pass

            try: salario = float(row.get('salario', 0))
            except: salario = 0.0

            escala = str(row.get('escala', 'Livre')).strip()
            dt_escala = None
            if escala == '12x36':
                dt_esc_raw = row.get('data_escala', '')
                if dt_esc_raw:
                    if isinstance(dt_esc_raw, (datetime, date)):
                        dt_escala = dt_esc_raw if isinstance(dt_esc_raw, date) else dt_esc_raw.date()
                    elif isinstance(dt_esc_raw, pd.Timestamp):
                        dt_escala = dt_esc_raw.date()
                    else:
                        dt_esc_str = str(dt_esc_raw).strip()
                        if ' ' in dt_esc_str: dt_esc_str = dt_esc_str.split(' ')[0]
                        try:
                            if '/' in dt_esc_str: dt_escala = datetime.strptime(dt_esc_str, '%d/%m/%Y').date()
                            else: dt_escala = datetime.strptime(dt_esc_str, '%Y-%m-%d').date()
                        except ValueError: pass

            carga_raw = row.get('carga_horaria', '08:48')
            if isinstance(carga_raw, time): carga_hm = carga_raw.strftime('%H:%M')
            else: carga_hm = str(carga_raw).strip() or '08:48'
            carga_min = time_to_minutes(carga_hm)
            
            try: intervalo = int(float(row.get('intervalo', 60)))
            except: intervalo = 60
            
            entrada_raw = row.get('entrada_ideal', '08:00')
            if isinstance(entrada_raw, time): entrada = entrada_raw.strftime('%H:%M')
            else: entrada = str(entrada_raw).strip() or '08:00'

            novo_pre = PreCadastro(
                cpf=cpf,
                nome_previsto=nome,
                cargo=cargo,
                departamento=departamento if departamento else None,
                cpf_gestor=cpf_gestor_raw if cpf_gestor_raw else None,
                salario=salario,
                data_admissao=dt_admissao,
                escala=escala,
                data_inicio_escala=dt_escala,
                carga_horaria=carga_min,
                tempo_intervalo=intervalo,
                inicio_jornada_ideal=entrada,
                razao_social="LA SHAHIN SERVIÇOS DE SEGURANÇA LTDA",
                cnpj="50.537.235/0001-95"
            )
            db.session.add(novo_pre)
            sucesso += 1

        db.session.commit()
        if sucesso > 0:
            flash(f'Importação Mágica concluída: {sucesso} lidos do Excel. {falhas} ignorados.', 'success')
        else:
            flash('Nenhum registro válido encontrado. Verifique se a planilha tem os títulos das colunas corretos.', 'error')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao ler arquivo do Excel: {str(e)}', 'error')

    return redirect(url_for('admin.gerenciar_usuarios'))


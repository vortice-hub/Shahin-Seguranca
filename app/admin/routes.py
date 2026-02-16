from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
import csv
import io
import logging

# Importações do Projeto
from app.extensions import db
from app.models import User, PreCadastro, PontoResumo, PontoAjuste, PontoRegistro, Holerite
from app.utils import (
    calcular_dia, 
    get_brasil_time, 
    format_minutes_to_hm, 
    gerar_login_automatico,
    master_required  # Novo decorator importado
)

admin_bp = Blueprint('admin', __name__, template_folder='templates', url_prefix='/admin')
logger = logging.getLogger(__name__)

# --- GESTÃO DE USUÁRIOS ---

@admin_bp.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
@master_required
def novo_usuario():
    if request.method == 'POST':
        try:
            # Coleta de dados do formulário
            real_name = request.form.get('real_name')
            cpf_raw = request.form.get('cpf', '')
            cpf = cpf_raw.replace('.', '').replace('-', '').strip()
            
            # Validação básica
            if not real_name or not cpf:
                flash('Nome e CPF são obrigatórios.', 'error')
                return redirect(url_for('admin.novo_usuario'))

            # Verifica duplicidade
            usuario_existente = User.query.filter_by(cpf=cpf).first()
            pre_cadastro_existente = PreCadastro.query.filter_by(cpf=cpf).first()
            
            if usuario_existente or pre_cadastro_existente:
                flash('CPF já cadastrado no sistema!', 'error')
                return redirect(url_for('admin.novo_usuario'))

            # Criação do Pré-Cadastro
            novo_pre = PreCadastro(
                cpf=cpf,
                nome_previsto=real_name,
                cargo=request.form.get('role'),
                salario=float(request.form.get('salario') or 0),
                horario_entrada=request.form.get('h_ent'),
                horario_almoco_inicio=request.form.get('h_alm_ini'),
                horario_almoco_fim=request.form.get('h_alm_fim'),
                horario_saida=request.form.get('h_sai'),
                escala=request.form.get('escala'),
                data_inicio_escala=request.form.get('dt_escala') if request.form.get('dt_escala') else None
            )
            
            db.session.add(novo_pre)
            db.session.commit()
            
            return render_template('admin/sucesso_usuario.html', nome_real=real_name, cpf=cpf)
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao criar usuário: {e}")
            flash(f'Erro interno ao processar cadastro: {str(e)}', 'error')
            
    return render_template('admin/novo_usuario.html')

@admin_bp.route('/usuarios')
@login_required
@master_required
def gerenciar_usuarios():
    users = User.query.order_by(User.real_name).all()
    pendentes = PreCadastro.query.order_by(PreCadastro.nome_previsto).all()
    return render_template('admin/admin_usuarios.html', users=users, pendentes=pendentes)

@admin_bp.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@master_required
def editar_usuario(id):
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        try:
            if acao == 'excluir':
                if user.username == 'Thaynara':
                    flash('Ação Proibida: Não é possível excluir o usuário Master.', 'error')
                else: 
                    # Limpeza em cascata manual (se não configurado no DB)
                    PontoRegistro.query.filter_by(user_id=user.id).delete()
                    PontoResumo.query.filter_by(user_id=user.id).delete()
                    Holerite.query.filter_by(user_id=user.id).delete()
                    
                    db.session.delete(user)
                    db.session.commit()
                    flash('Usuário excluído com sucesso.', 'success')
                    return redirect(url_for('admin.gerenciar_usuarios'))

            elif acao == 'salvar':
                user.real_name = request.form.get('real_name')
                user.role = request.form.get('role')
                user.salario = float(request.form.get('salario') or 0)
                
                # Atualização de Jornada
                user.horario_entrada = request.form.get('h_ent')
                user.horario_almoco_inicio = request.form.get('h_alm_ini')
                user.horario_almoco_fim = request.form.get('h_alm_fim')
                user.horario_saida = request.form.get('h_sai')
                user.escala = request.form.get('escala')
                
                dt_escala = request.form.get('dt_escala')
                if dt_escala:
                    user.data_inicio_escala = dt_escala
                
                db.session.commit()
                flash('Dados atualizados com sucesso.', 'success')
                return redirect(url_for('admin.gerenciar_usuarios'))
                
            elif acao == 'resetar_senha':
                # Reseta para uma senha padrão temporária (ex: mudar123)
                user.set_password('mudar123')
                user.is_first_access = True
                db.session.commit()
                flash(f'Senha resetada para "mudar123". O usuário deverá trocá-la no próximo login.', 'warning')
                
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao salvar alterações: {e}', 'error')

    return render_template('admin/editar_usuario.html', user=user)

@admin_bp.route('/usuarios/importar-csv', methods=['GET', 'POST'])
@login_required
@master_required
def importar_csv():
    if request.method == 'POST':
        file = request.files.get('arquivo_csv')
        if not file:
            return redirect(url_for('admin.importar_csv'))
            
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream, delimiter=';')
            
            count_sucesso = 0
            count_ignorado = 0
            
            for row in csv_reader:
                cpf_bruto = row.get('CPF', '')
                cpf_limpo = cpf_bruto.replace('.', '').replace('-', '').strip()
                
                if not cpf_limpo:
                    continue
                    
                # Verifica existência
                if PreCadastro.query.filter_by(cpf=cpf_limpo).first() or User.query.filter_by(cpf=cpf_limpo).first():
                    count_ignorado += 1
                    continue
                
                # Tratamento de valores numéricos
                salario_str = row.get('Salario', '0').replace(',', '.')
                try:
                    salario_float = float(salario_str)
                except ValueError:
                    salario_float = 0.0

                pre = PreCadastro(
                    cpf=cpf_limpo,
                    nome_previsto=row.get('Nome', 'Funcionario'),
                    cargo=row.get('Cargo', 'Colaborador'),
                    salario=salario_float,
                    horario_entrada=row.get('Entrada', '07:12'),
                    horario_saida=row.get('Saida', '17:00'),
                    horario_almoco_inicio='12:00',
                    horario_almoco_fim='13:00',
                    escala='5x2'
                )
                db.session.add(pre)
                count_sucesso += 1
                
            db.session.commit()
            flash(f'Processamento concluído: {count_sucesso} importados, {count_ignorado} duplicados ignorados.', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao processar arquivo CSV: {e}', 'error')
            
    return render_template('admin/admin_importar_csv.html')

# --- GESTÃO DE ACESSOS E LIBERAÇÕES ---

@admin_bp.route('/liberar-acesso', methods=['POST'])
@login_required
@master_required
def liberar_acesso():
    try:
        cpf_raw = request.form.get('cpf', '')
        cpf = cpf_raw.replace('.', '').replace('-', '').strip()
        
        # Verifica duplicidade
        if User.query.filter_by(cpf=cpf).first() or PreCadastro.query.filter_by(cpf=cpf).first():
            flash('Este CPF já possui cadastro ou liberação pendente.', 'error')
        else:
            novo = PreCadastro(
                cpf=cpf,
                nome_previsto=request.form.get('nome'),
                cargo=request.form.get('cargo'),
                salario=float(request.form.get('salario') or 0),
                horario_entrada=request.form.get('h_ent'),
                horario_almoco_inicio=request.form.get('h_alm_ini'),
                horario_almoco_fim=request.form.get('h_alm_fim'),
                horario_saida=request.form.get('h_sai'),
                escala=request.form.get('escala'),
                data_inicio_escala=request.form.get('dt_escala') if request.form.get('dt_escala') else None
            )
            db.session.add(novo)
            db.session.commit()
            flash('Acesso liberado com sucesso! O funcionário já pode criar a conta.', 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao liberar acesso: {e}', 'error')
        
    # Redireciona para a lista geral para ver o resultado
    return redirect(url_for('admin.gerenciar_usuarios'))

@admin_bp.route('/liberar-acesso/excluir/<int:id>')
@login_required
@master_required
def excluir_liberacao(id):
    pre = PreCadastro.query.get(id)
    if pre:
        db.session.delete(pre)
        db.session.commit()
        flash('Pré-cadastro removido da fila.', 'success')
    return redirect(url_for('admin.gerenciar_usuarios'))

# --- SOLICITAÇÕES DE PONTO ---

@admin_bp.route('/solicitacoes', methods=['GET', 'POST'])
@login_required
@master_required
def admin_solicitacoes():
    if request.method == 'POST':
        solic_id = request.form.get('solic_id')
        decisao = request.form.get('decisao')
        motivo = request.form.get('motivo_repro')
        
        solic = PontoAjuste.query.get(solic_id)
        if solic:
            if decisao == 'aprovar':
                solic.status = 'Aprovado'
                
                # Se for Inclusão, cria o registro no ponto
                if solic.tipo_solicitacao == 'Inclusao':
                    # Lógica futura: Converter string HH:MM para Time e salvar
                    pass
                # Se for Edição, atualiza o registro existente
                elif solic.tipo_solicitacao == 'Edicao' and solic.ponto_original_id:
                    # Lógica futura: Atualizar PontoRegistro
                    pass
                
                flash('Solicitação Aprovada.', 'success')
            else:
                solic.status = 'Reprovado'
                solic.motivo_reprovacao = motivo
                flash('Solicitação Reprovada.', 'warning')
                
            db.session.commit()
            
    solicitacoes = PontoAjuste.query.filter_by(status='Pendente').order_by(PontoAjuste.created_at.desc()).all()
    
    # Busca dados extras para exibição (ex: horário original antes da edição)
    extras = {}
    for s in solicitacoes:
        if s.ponto_original_id:
            ponto = PontoRegistro.query.get(s.ponto_original_id)
            if ponto:
                extras[s.id] = ponto.hora_registro.strftime('%H:%M')
                
    return render_template('admin/solicitacoes.html', solicitacoes=solicitacoes, extras=extras)

# --- FERRAMENTAS E RELATÓRIOS ---

@admin_bp.route('/relatorio-folha', methods=['GET', 'POST'])
@login_required
@master_required
def admin_relatorio_folha():
    # Define mês de referência (Padrão: Atual)
    mes_ref = request.form.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    
    try: 
        ano, mes = map(int, mes_ref.split('-'))
    except ValueError: 
        hoje = get_brasil_time()
        ano, mes = hoje.year, hoje.month
        mes_ref = hoje.strftime('%Y-%m')
    
    users = User.query.order_by(User.real_name).all()
    relatorio = []
    
    for u in users:
        # Calcula saldo total do mês para cada usuário
        resumos = PontoResumo.query.filter(
            PontoResumo.user_id == u.id, 
            func.extract('year', PontoResumo.data_referencia) == ano, 
            func.extract('month', PontoResumo.data_referencia) == mes
        ).all()
        
        total_saldo = sum(r.minutos_saldo for r in resumos)
        
        relatorio.append({
            'id': u.id,
            'nome': u.real_name,
            'cargo': u.role,
            'saldo_formatado': format_minutes_to_hm(total_saldo),
            'sinal': 'text-emerald-600' if total_saldo >= 0 else 'text-red-600'
        })
        
    return render_template('admin/admin_relatorio_folha.html', relatorio=relatorio, mes_ref=mes_ref)

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
                flash('Todos os registros de ponto foram apagados.', 'warning')
                
            elif acao == 'limpar_holerites':
                Holerite.query.delete()
                flash('Todos os holerites foram removidos do banco.', 'warning')
                
            elif acao == 'limpar_usuarios_nao_master':
                # Remove todos exceto quem tem 'Master' no username ou role
                User.query.filter(User.username != 'Thaynara').delete()
                PreCadastro.query.delete()
                flash('Usuários de teste removidos com sucesso.', 'warning')
            
            db.session.commit()
            return redirect(url_for('admin.admin_limpeza'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro durante a limpeza: {e}', 'error')
            
    return render_template('admin/admin_limpeza.html')



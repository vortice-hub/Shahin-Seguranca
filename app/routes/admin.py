from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, PreCadastro, PontoResumo, PontoAjuste, PontoRegistro
from app.utils import calcular_dia, get_brasil_time
import secrets
import csv
import io
from datetime import datetime, time
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/usuarios/importar-csv', methods=['GET', 'POST'])
@login_required
def importar_csv():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        file = request.files.get('arquivo_csv')
        if not file:
            flash('Selecione um arquivo CSV.')
            return redirect(url_for('admin.importar_csv'))
            
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream, delimiter=';') # Padrão Excel BR
            
            count = 0
            for row in csv_reader:
                # Espera colunas: Nome;CPF;Cargo;Salario;Entrada;Saida
                cpf_limpo = row.get('CPF', '').replace('.', '').replace('-', '').strip()
                if not cpf_limpo: continue
                
                # Verifica duplicidade
                if PreCadastro.query.filter_by(cpf=cpf_limpo).first() or User.query.filter_by(cpf=cpf_limpo).first():
                    continue
                    
                pre = PreCadastro(
                    cpf=cpf_limpo,
                    nome_previsto=row.get('Nome', 'Funcionario Importado'),
                    cargo=row.get('Cargo', 'Colaborador'),
                    salario=float(row.get('Salario', 0).replace(',', '.') or 0),
                    horario_entrada=row.get('Entrada', '07:12'),
                    horario_saida=row.get('Saida', '17:00'),
                    # Defaults
                    horario_almoco_inicio='12:00',
                    horario_almoco_fim='13:00',
                    escala='5x2'
                )
                db.session.add(pre)
                count += 1
                
            db.session.commit()
            flash(f'Importação concluída! {count} novos CPFs liberados na lista de espera.')
            return redirect(url_for('admin.gerenciar_usuarios'))
            
        except Exception as e:
            flash(f'Erro ao ler CSV: {e}')
            
    return render_template('admin_importar_csv.html')

@admin_bp.route('/usuarios')
@login_required
def gerenciar_usuarios():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    users = User.query.all(); pendentes = PreCadastro.query.all()
    return render_template('admin_usuarios.html', users=users, pendentes=pendentes)

@admin_bp.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
def novo_usuario():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        try:
            cpf = request.form.get('cpf').replace('.', '').replace('-', '').strip()
            if User.query.filter_by(cpf=cpf).first(): flash('Erro: CPF já existe.'); return redirect(url_for('admin.novo_usuario'))
            dt_escala = None
            if request.form.get('dt_escala'): dt_escala = datetime.strptime(request.form.get('dt_escala'), '%Y-%m-%d').date()
            pre = PreCadastro(cpf=cpf, nome_previsto=request.form.get('real_name'), cargo=request.form.get('role'), salario=float(request.form.get('salario') or 0), horario_entrada=request.form.get('h_ent'), horario_almoco_inicio=request.form.get('h_alm_ini'), horario_almoco_fim=request.form.get('h_alm_fim'), horario_saida=request.form.get('h_sai'), escala=request.form.get('escala'), data_inicio_escala=dt_escala)
            db.session.add(pre); db.session.commit()
            return render_template('sucesso_usuario.html', nome_real=request.form.get('real_name'), cpf=cpf)
        except Exception as e: db.session.rollback(); flash(f"Erro: {e}"); return redirect(url_for('admin.novo_usuario'))
    return render_template('novo_usuario.html')

@admin_bp.route('/liberar-acesso/excluir/<int:id>')
@login_required
def excluir_pre_cadastro(id):
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    pre = PreCadastro.query.get(id)
    if pre: db.session.delete(pre); db.session.commit(); flash('Removido.')
    return redirect(url_for('admin.gerenciar_usuarios'))

@admin_bp.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        try:
            acao = request.form.get('acao')
            if acao == 'excluir':
                if user.username == 'Thaynara': flash('Erro master.')
                else: 
                    PontoRegistro.query.filter_by(user_id=user.id).delete(); PontoResumo.query.filter_by(user_id=user.id).delete(); PontoAjuste.query.filter_by(user_id=user.id).delete(); db.session.delete(user); db.session.commit(); flash('Excluido.')
                return redirect(url_for('admin.gerenciar_usuarios'))
            elif acao == 'resetar_senha': nova = secrets.token_hex(3); user.set_password(nova); user.is_first_access = True; db.session.commit(); flash(f'Senha: {nova}'); return redirect(url_for('admin.editar_usuario', id=id))
            else:
                user.real_name = request.form.get('real_name'); user.username = request.form.get('username')
                if user.username != 'Thaynara': user.role = request.form.get('role')
                user.salario = float(request.form.get('salario') or 0); user.horario_entrada = request.form.get('h_ent'); user.horario_almoco_inicio = request.form.get('h_alm_ini'); user.horario_almoco_fim = request.form.get('h_alm_fim'); user.horario_saida = request.form.get('h_sai'); user.escala = request.form.get('escala')
                if request.form.get('dt_escala'): user.data_inicio_escala = datetime.strptime(request.form.get('dt_escala'), '%Y-%m-%d').date()
                db.session.commit(); flash('Atualizado.')
                return redirect(url_for('admin.gerenciar_usuarios'))
        except Exception as e: db.session.rollback(); flash(f'Erro: {e}'); return redirect(url_for('admin.editar_usuario', id=id))
    return render_template('editar_usuario.html', user=user)

@admin_bp.route('/solicitacoes', methods=['GET', 'POST'])
@login_required
def admin_solicitacoes():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        try:
            solic = PontoAjuste.query.get(request.form.get('solic_id'))
            decisao = request.form.get('decisao')
            if decisao == 'aprovar':
                solic.status = 'Aprovado'
                if solic.tipo_solicitacao == 'Exclusao':
                    if solic.ponto_original_id: db.session.delete(PontoRegistro.query.get(solic.ponto_original_id))
                elif solic.tipo_solicitacao == 'Edicao':
                    p = PontoRegistro.query.get(solic.ponto_original_id)
                    h, m = map(int, solic.novo_horario.split(':'))
                    p.hora_registro = time(h, m); p.tipo = solic.tipo_batida
                elif solic.tipo_solicitacao == 'Inclusao':
                    h, m = map(int, solic.novo_horario.split(':'))
                    db.session.add(PontoRegistro(user_id=solic.user_id, data_registro=solic.data_referencia, hora_registro=time(h, m), tipo=solic.tipo_batida, latitude='Ajuste', longitude='Manual'))
                db.session.commit(); calcular_dia(solic.user_id, solic.data_referencia); flash('Aprovado.')
            elif decisao == 'reprovar':
                solic.status = 'Reprovado'; solic.motivo_reprovacao = request.form.get('motivo_repro'); db.session.commit(); flash('Reprovado.')
        except Exception as e: db.session.rollback(); flash(f'Erro: {e}')
        return redirect(url_for('admin.admin_solicitacoes'))
    pendentes = PontoAjuste.query.filter_by(status='Pendente').order_by(PontoAjuste.created_at).all()
    dados_extras = {}
    for p in pendentes:
        if p.ponto_original_id:
            original = PontoRegistro.query.get(p.ponto_original_id)
            if original: dados_extras[p.id] = original.hora_registro.strftime('%H:%M')
    return render_template('admin_solicitacoes.html', solicitacoes=pendentes, extras=dados_extras)

@admin_bp.route('/relatorio-folha', methods=['GET', 'POST'])
@login_required
def admin_relatorio_folha():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    mes_ref = request.form.get('mes_ref') or datetime.now().strftime('%Y-%m')
    try: ano, mes = map(int, mes_ref.split('-'))
    except: hoje = datetime.now(); ano, mes = hoje.year, hoje.month; mes_ref = hoje.strftime('%Y-%m')
    if request.method == 'POST' and not request.form.get('acao_zerar'): flash(f'Exibindo dados de {mes_ref}')
    users = User.query.order_by(User.real_name).all()
    relatorio = []
    for u in users:
        try:
            resumos = PontoResumo.query.filter(PontoResumo.user_id == u.id, func.extract('year', PontoResumo.data_referencia) == ano, func.extract('month', PontoResumo.data_referencia) == mes).all()
            total_saldo = sum(r.minutos_saldo for r in resumos)
            sinal = "+" if total_saldo >= 0 else "-"
            abs_s = abs(total_saldo)
            sal_val = u.salario if u.salario else 0.0
            relatorio.append({'nome': u.real_name, 'cargo': u.role, 'salario': sal_val, 'saldo_minutos': total_saldo, 'saldo_formatado': f"{sinal}{abs_s // 60:02d}:{abs_s % 60:02d}", 'status': 'Crédito' if total_saldo >= 0 else 'Débito'})
        except: continue
    return render_template('admin_relatorio_folha.html', relatorio=relatorio, mes_ref=mes_ref)

@admin_bp.route('/relatorio-folha/zerar', methods=['POST'])
@login_required
def zerar_relatorio():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    mes_ref = request.form.get('mes_ref')
    if not mes_ref: return redirect(url_for('admin.admin_relatorio_folha'))
    try:
        ano, mes = map(int, mes_ref.split('-'))
        PontoResumo.query.filter(func.extract('year', PontoResumo.data_referencia) == ano, func.extract('month', PontoResumo.data_referencia) == mes).delete(synchronize_session=False)
        db.session.commit(); flash(f'Relatório de {mes_ref} zerado.')
    except Exception as e: db.session.rollback(); flash(f'Erro: {e}')
    return redirect(url_for('admin.admin_relatorio_folha'))
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, text
import csv
import io
import logging

from app.extensions import db
from app.models import User, PreCadastro, PontoResumo, PontoAjuste, PontoRegistro, Holerite, Recibo
from app.utils import (
    calcular_dia, 
    get_brasil_time, 
    format_minutes_to_hm, 
    time_to_minutes,
    gerar_login_automatico,
    master_required
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
            real_name = request.form.get('real_name')
            cpf = request.form.get('cpf', '').replace('.', '').replace('-', '').strip()
            
            if not real_name or not cpf:
                flash('Nome e CPF são obrigatórios.', 'error'); return redirect(url_for('admin.novo_usuario'))

            if User.query.filter_by(cpf=cpf).first() or PreCadastro.query.filter_by(cpf=cpf).first():
                flash('CPF já cadastrado!', 'error'); return redirect(url_for('admin.novo_usuario'))

            # CONVERSÃO DE CARGA HORÁRIA (HH:MM -> Minutos)
            carga_hm = request.form.get('carga_horaria') or '08:48'
            carga_minutos = time_to_minutes(carga_hm)
            
            intervalo_min = int(request.form.get('tempo_intervalo') or 60)

            novo_pre = PreCadastro(
                cpf=cpf,
                nome_previsto=real_name,
                cargo=request.form.get('role'),
                salario=float(request.form.get('salario') or 0),
                
                # Dados Empresa
                razao_social=request.form.get('razao_social'),
                cnpj=request.form.get('cnpj'),
                
                # JORNADA FLEXÍVEL
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
            db.session.rollback(); logger.error(f"Erro: {e}"); flash(f'Erro interno: {str(e)}', 'error')
            
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
    
    # Converte minutos para HH:MM para exibir no formulário
    user_carga_hm = format_minutes_to_hm(user.carga_horaria or 528)
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        try:
            if acao == 'excluir':
                if user.username == 'Thaynara': flash('Não pode excluir Master.', 'error')
                else: 
                    PontoRegistro.query.filter_by(user_id=user.id).delete()
                    PontoResumo.query.filter_by(user_id=user.id).delete()
                    Holerite.query.filter_by(user_id=user.id).delete()
                    Recibo.query.filter_by(user_id=user.id).delete()
                    db.session.delete(user); db.session.commit()
                    flash('Usuário excluído.', 'success')
                    return redirect(url_for('admin.gerenciar_usuarios'))

            elif acao == 'salvar':
                user.real_name = request.form.get('real_name')
                user.role = request.form.get('role')
                user.salario = float(request.form.get('salario') or 0)
                user.razao_social_empregadora = request.form.get('razao_social')
                user.cnpj_empregador = request.form.get('cnpj')
                
                # ATUALIZAÇÃO JORNADA
                carga_hm = request.form.get('carga_horaria')
                user.carga_horaria = time_to_minutes(carga_hm)
                user.tempo_intervalo = int(request.form.get('tempo_intervalo') or 60)
                user.inicio_jornada_ideal = request.form.get('h_ent')
                
                user.escala = request.form.get('escala')
                if request.form.get('dt_escala'): user.data_inicio_escala = request.form.get('dt_escala')
                
                db.session.commit()
                flash('Dados atualizados.', 'success')
                return redirect(url_for('admin.gerenciar_usuarios'))
                
            elif acao == 'resetar_senha':
                user.set_password('mudar123'); user.is_first_access = True
                db.session.commit(); flash('Senha resetada.', 'warning')
                
        except Exception as e:
            db.session.rollback(); flash(f'Erro: {e}', 'error')

    return render_template('admin/editar_usuario.html', user=user, carga_hm=user_carga_hm)

# (Mantenha as rotas importar_csv, liberar_acesso, solicitacoes, relatorio, limpeza e patch iguais)
# Para economizar espaço, assumo que você manterá o resto do arquivo que já estava correto.
# Se precisar que eu reenvie o arquivo INTEIRO com essas mudanças + o resto, me avise.
# O foco aqui foi alterar 'novo_usuario' e 'editar_usuario'.

@admin_bp.route('/usuarios/importar-csv', methods=['GET', 'POST'])
@login_required
@master_required
def importar_csv():
    # ... (Código Mantido)
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
                db.session.add(pre); count += 1
            db.session.commit(); flash(f'{count} importados.')
        except Exception as e: flash(f'Erro: {e}')
    return render_template('admin/admin_importar_csv.html')

@admin_bp.route('/liberar-acesso', methods=['POST'])
@login_required
@master_required
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
            db.session.add(novo); db.session.commit(); flash('Acesso liberado.', 'success')
    except Exception as e: flash(f'Erro: {e}', 'error')
    return redirect(url_for('admin.gerenciar_usuarios'))

@admin_bp.route('/liberar-acesso/excluir/<int:id>')
@login_required
@master_required
def excluir_liberacao(id):
    pre = PreCadastro.query.get(id)
    if pre: db.session.delete(pre); db.session.commit(); flash('Removido.')
    return redirect(url_for('admin.gerenciar_usuarios'))

@admin_bp.route('/solicitacoes', methods=['GET', 'POST'])
@login_required
@master_required
def admin_solicitacoes():
    if request.method == 'POST':
        solic = PontoAjuste.query.get(request.form.get('solic_id'))
        if solic:
            if request.form.get('decisao') == 'aprovar': solic.status = 'Aprovado'; flash('Aprovado.', 'success')
            else: solic.status = 'Reprovado'; solic.motivo_reprovacao = request.form.get('motivo_repro'); flash('Reprovado.', 'warning')
            db.session.commit()
    return render_template('admin/solicitacoes.html', solicitacoes=PontoAjuste.query.filter_by(status='Pendente').order_by(PontoAjuste.created_at.desc()).all(), extras={})

@admin_bp.route('/relatorio-folha', methods=['GET', 'POST'])
@login_required
@master_required
def admin_relatorio_folha():
    mes_ref = request.form.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    try: ano, mes = map(int, mes_ref.split('-'))
    except: hoje = get_brasil_time(); ano, mes = hoje.year, hoje.month
    users = User.query.order_by(User.real_name).all()
    relatorio = []
    for u in users:
        resumos = PontoResumo.query.filter(PontoResumo.user_id == u.id, func.extract('year', PontoResumo.data_referencia) == ano, func.extract('month', PontoResumo.data_referencia) == mes).all()
        total = sum(r.minutos_saldo for r in resumos)
        relatorio.append({'id': u.id, 'nome': u.real_name, 'cargo': u.role, 'saldo_formatado': format_minutes_to_hm(total), 'sinal': 'text-emerald-600' if total >= 0 else 'text-red-600'})
    return render_template('admin/admin_relatorio_folha.html', relatorio=relatorio, mes_ref=mes_ref)

@admin_bp.route('/ferramentas/limpeza', methods=['GET', 'POST'])
@login_required
@master_required
def admin_limpeza():
    if request.method == 'POST':
        acao = request.form.get('acao')
        try:
            if acao == 'limpar_testes_ponto': PontoRegistro.query.delete(); PontoResumo.query.delete()
            elif acao == 'limpar_holerites': Holerite.query.delete(); Recibo.query.delete()
            elif acao == 'limpar_usuarios_nao_master': User.query.filter(User.username != 'Thaynara').delete(); PreCadastro.query.delete()
            db.session.commit(); return redirect(url_for('admin.admin_limpeza'))
        except: db.session.rollback()
    return render_template('admin/admin_limpeza.html')

@admin_bp.route('/sistema/atualizar-banco-neon', methods=['GET'])
@login_required
@master_required
def patch_banco_dados():
    # Rota Mantida para garantir compatibilidade
    return "Banco já atualizado."




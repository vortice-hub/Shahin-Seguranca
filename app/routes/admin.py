from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, PreCadastro, PontoResumo, PontoAjuste, PontoRegistro
from app.utils import calcular_dia, get_brasil_time, format_minutes_to_hm
import secrets
import csv
import io
from datetime import datetime, time
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/relatorio-folha', methods=['GET', 'POST'])
@login_required
def admin_relatorio_folha():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    mes_ref = request.form.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    try: ano, mes = map(int, mes_ref.split('-'))
    except: hoje = get_brasil_time(); ano, mes = hoje.year, hoje.month; mes_ref = hoje.strftime('%Y-%m')
    
    users = User.query.order_by(User.real_name).all()
    relatorio = []
    for u in users:
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
    return render_template('admin_relatorio_folha.html', relatorio=relatorio, mes_ref=mes_ref)

@admin_bp.route('/usuarios/importar-csv', methods=['GET', 'POST'])
@login_required
def importar_csv():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        file = request.files.get('arquivo_csv')
        if not file: return redirect(url_for('admin.importar_csv'))
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream, delimiter=';')
            count = 0
            for row in csv_reader:
                cpf_limpo = row.get('CPF', '').replace('.', '').replace('-', '').strip()
                if not cpf_limpo: continue
                if PreCadastro.query.filter_by(cpf=cpf_limpo).first() or User.query.filter_by(cpf=cpf_limpo).first(): continue
                pre = PreCadastro(
                    cpf=cpf_limpo,
                    nome_previsto=row.get('Nome', 'Funcionario'),
                    cargo=row.get('Cargo', 'Colaborador'),
                    salario=float(row.get('Salario', 0).replace(',', '.') or 0),
                    horario_entrada=row.get('Entrada', '07:12'),
                    horario_saida=row.get('Saida', '17:00'),
                    horario_almoco_inicio='12:00', horario_almoco_fim='13:00', escala='5x2'
                )
                db.session.add(pre); count += 1
            db.session.commit()
            flash(f'Importados {count} CPFs.')
        except Exception as e: flash(f'Erro: {e}')
    return render_template('admin_importar_csv.html')

@admin_bp.route('/usuarios')
@login_required
def gerenciar_usuarios():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    users = User.query.all(); pendentes = PreCadastro.query.all()
    return render_template('admin_usuarios.html', users=users, pendentes=pendentes)

@admin_bp.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        try:
            acao = request.form.get('acao')
            if acao == 'excluir':
                if user.username == 'Thaynara': flash('Erro.')
                else: 
                    PontoRegistro.query.filter_by(user_id=user.id).delete(); db.session.delete(user); db.session.commit()
                return redirect(url_for('admin.gerenciar_usuarios'))
            user.real_name = request.form.get('real_name'); user.role = request.form.get('role')
            user.salario = float(request.form.get('salario') or 0); user.horario_entrada = request.form.get('h_ent')
            user.horario_almoco_inicio = request.form.get('h_alm_ini'); user.horario_almoco_fim = request.form.get('h_alm_fim')
            user.horario_saida = request.form.get('h_sai'); user.escala = request.form.get('escala')
            db.session.commit(); flash('Salvo.'); return redirect(url_for('admin.gerenciar_usuarios'))
        except Exception as e: flash(f'Erro: {e}')
    return render_template('editar_usuario.html', user=user)

@admin_bp.route('/solicitacoes', methods=['GET', 'POST'])
@login_required
def admin_solicitacoes():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    pendentes = PontoAjuste.query.filter_by(status='Pendente').all()
    return render_template('admin_solicitacoes.html', solicitacoes=pendentes)
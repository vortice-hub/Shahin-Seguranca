from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import PontoRegistro, PontoResumo, User
from app.utils import get_brasil_time, calcular_dia, format_minutes_to_hm
from datetime import datetime, date

ponto_bp = Blueprint('ponto', __name__, url_prefix='/ponto')

@ponto_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    hoje = get_brasil_time().date()
    if request.method == 'POST':
        tipo = request.form.get('tipo')
        lat = request.form.get('lat'); lon = request.form.get('lon')
        novo = PontoRegistro(user_id=current_user.id, data_registro=hoje, tipo=tipo, latitude=lat, longitude=lon)
        db.session.add(novo); db.session.commit()
        calcular_dia(current_user.id, hoje)
        flash(f'Ponto de {tipo} registrado!')
        return redirect(url_for('main.dashboard'))
    registros = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).all()
    return render_template('registrar_ponto.html', registros=registros)

@ponto_bp.route('/espelho')
@login_required
def espelho_ponto():
    # Se for Master, pode passar user_id pela URL para auditar outros
    target_user_id = request.args.get('user_id', type=int) or current_user.id
    if target_user_id != current_user.id and current_user.role != 'Master':
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(target_user_id)
    mes_ref = request.args.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    ano, mes = map(int, mes_ref.split('-'))
    
    resumos = PontoResumo.query.filter(
        PontoResumo.user_id == target_user_id,
        func.extract('year', PontoResumo.data_referencia) == ano,
        func.extract('month', PontoResumo.data_referencia) == mes
    ).order_by(PontoResumo.data_referencia).all()
    
    # Detalhes de batidas para cada dia para o Master ver
    detalhes = {}
    for r in resumos:
        batidas = PontoRegistro.query.filter_by(user_id=target_user_id, data_registro=r.data_referencia).order_by(PontoRegistro.hora_registro).all()
        detalhes[r.id] = [b.hora_registro.strftime('%H:%M') for b in batidas]

    return render_template('ponto_espelho.html', resumos=resumos, user=user, detalhes=detalhes, format_hm=format_minutes_to_hm, mes_ref=mes_ref)
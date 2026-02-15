from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import PontoRegistro, PontoResumo, User, PontoAjuste
from app.utils import get_brasil_time, calcular_dia, format_minutes_to_hm
from datetime import datetime, date
from sqlalchemy import func

ponto_bp = Blueprint('ponto', __name__, template_folder='templates', url_prefix='/ponto')

@ponto_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    hoje = get_brasil_time().date()
    if request.method == 'POST':
        tipo = request.form.get('tipo')
        lat = request.form.get('lat')
        lon = request.form.get('lon')
        
        # Validação simples
        if not tipo:
            flash('Selecione um tipo de registro.', 'error')
            return redirect(url_for('ponto.registrar_ponto'))

        novo = PontoRegistro(
            user_id=current_user.id, 
            data_registro=hoje, 
            tipo=tipo, 
            latitude=lat, 
            longitude=lon
        )
        db.session.add(novo)
        try:
            db.session.commit()
            calcular_dia(current_user.id, hoje)
            flash(f'Ponto de {tipo} registrado com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao registrar: {str(e)}', 'error')
            
        return redirect(url_for('main.dashboard'))
    
    # Busca histórico do dia para exibir
    registros = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
    return render_template('ponto_registro.html', registros=registros)

@ponto_bp.route('/espelho')
@login_required
def espelho_ponto():
    target_user_id = request.args.get('user_id', type=int) or current_user.id
    if target_user_id != current_user.id and current_user.role != 'Master':
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(target_user_id)
    mes_ref = request.args.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    try:
        ano, mes = map(int, mes_ref.split('-'))
    except:
        hoje = get_brasil_time()
        ano, mes = hoje.year, hoje.month
        mes_ref = hoje.strftime('%Y-%m')
    
    resumos = PontoResumo.query.filter(
        PontoResumo.user_id == target_user_id,
        func.extract('year', PontoResumo.data_referencia) == ano,
        func.extract('month', PontoResumo.data_referencia) == mes
    ).order_by(PontoResumo.data_referencia).all()
    
    detalhes = {}
    for r in resumos:
        batidas = PontoRegistro.query.filter_by(user_id=target_user_id, data_registro=r.data_referencia).order_by(PontoRegistro.hora_registro).all()
        detalhes[r.id] = [b.hora_registro.strftime('%H:%M') for b in batidas]

    # Dicionário de Tradução dos Dias (Fix para idioma Inglês no Server)
    dias_semana = {0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex', 5: 'Sáb', 6: 'Dom'}

    return render_template('ponto/ponto_espelho.html', 
                         resumos=resumos, 
                         user=user, 
                         detalhes=detalhes, 
                         format_hm=format_minutes_to_hm, 
                         mes_ref=mes_ref,
                         dias_semana=dias_semana)

@ponto_bp.route('/solicitar-ajuste', methods=['GET', 'POST'])
@login_required
def solicitar_ajuste():
    data_sel = None
    pontos = []
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        if acao == 'buscar':
            data_busca = request.form.get('data_busca')
            if data_busca:
                try:
                    data_sel = datetime.strptime(data_busca, '%Y-%m-%d').date()
                    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=data_sel).order_by(PontoRegistro.hora_registro).all()
                except:
                    flash('Data inválida.', 'error')
        
        elif acao == 'enviar':
            try:
                # Logica simplificada de ajuste (expansível)
                ajuste = PontoAjuste(
                    user_id=current_user.id,
                    data_referencia=request.form.get('data_ref'),
                    ponto_original_id=request.form.get('ponto_id') or None,
                    novo_horario=request.form.get('novo_horario'),
                    tipo_batida=request.form.get('tipo_batida'),
                    tipo_solicitacao=request.form.get('tipo_solicitacao'),
                    justificativa=request.form.get('justificativa')
                )
                db.session.add(ajuste)
                db.session.commit()
                flash('Solicitação enviada!', 'success')
                return redirect(url_for('ponto.solicitar_ajuste'))
            except Exception as e:
                db.session.rollback()
                flash(f'Erro: {e}', 'error')

    # Histórico de Ajustes
    meus_ajustes = PontoAjuste.query.filter_by(user_id=current_user.id).order_by(PontoAjuste.created_at.desc()).limit(10).all()
    extras = {}
    for a in meus_ajustes:
        if a.ponto_original_id:
            p = PontoRegistro.query.get(a.ponto_original_id)
            if p: extras[a.id] = f"{p.hora_registro.strftime('%H:%M')} ({p.tipo})"
    
    return render_template('ponto/solicitar_ajuste.html', 
                         data_sel=data_sel, 
                         pontos=pontos, 
                         meus_ajustes=meus_ajustes, 
                         extras=extras)

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import ItemEstoque, HistoricoEntrada, HistoricoSaida
from app.utils import get_brasil_time
from datetime import datetime

estoque_bp = Blueprint('estoque', __name__, template_folder='templates')

@estoque_bp.route('/controle-uniforme')
@login_required
def controle_uniforme(): return render_template('estoque/controle_uniforme.html', itens=ItemEstoque.query.all()) if current_user.role == 'Master' else redirect(url_for('main.dashboard'))

@estoque_bp.route('/entrada', methods=['GET', 'POST'])
@login_required
def entrada(): 
    if request.method == 'POST':
        try:
            nome = request.form.get('nome_outros') if request.form.get('nome_select') == 'Outros' else request.form.get('nome_select')
            item = ItemEstoque.query.filter_by(nome=nome, tamanho=request.form.get('tamanho'), genero=request.form.get('genero')).first()
            qtd = int(request.form.get('quantidade') or 1)
            if item:
                item.quantidade += qtd
                item.estoque_minimo = int(request.form.get('estoque_minimo') or 5)
                item.estoque_ideal = int(request.form.get('estoque_ideal') or 20)
                item.data_atualizacao = get_brasil_time()
            else:
                novo = ItemEstoque(nome=nome, tamanho=request.form.get('tamanho'), genero=request.form.get('genero'), quantidade=qtd, estoque_minimo=int(request.form.get('estoque_minimo') or 5), estoque_ideal=int(request.form.get('estoque_ideal') or 20))
                novo.data_atualizacao = get_brasil_time()
                db.session.add(novo)
            db.session.add(HistoricoEntrada(item_nome=f"{nome} ({request.form.get('genero')}-{request.form.get('tamanho')})", quantidade=qtd, data_hora=get_brasil_time()))
            db.session.commit(); return redirect(url_for('estoque.controle_uniforme'))
        except: db.session.rollback()
    return render_template('estoque/entrada.html')

@estoque_bp.route('/saida', methods=['GET', 'POST'])
@login_required
def saida(): 
    if request.method == 'POST': 
        item = ItemEstoque.query.get(request.form.get('item_id'))
        qtd = int(request.form.get('quantidade') or 1)
        if item and item.quantidade >= qtd:
            item.quantidade -= qtd
            item.data_atualizacao = get_brasil_time()
            try: dt = datetime.strptime(request.form.get('data'), '%Y-%m-%d')
            except: dt = get_brasil_time()
            db.session.add(HistoricoSaida(coordenador=request.form.get('coordenador'), colaborador=request.form.get('colaborador'), item_nome=item.nome, tamanho=item.tamanho, genero=item.genero, quantidade=qtd, data_entrega=dt))
            db.session.commit()
            return redirect(url_for('estoque.controle_uniforme'))
        flash('Erro estoque.')
    return render_template('estoque/saida.html', itens=ItemEstoque.query.all())

@estoque_bp.route('/gerenciar/selecao', methods=['GET', 'POST'])
@login_required
def selecionar_edicao():
    if request.method == 'POST': return redirect(url_for('estoque.editar_item', id=request.form.get('item_id')))
    return render_template('estoque/selecionar_edicao.html', itens=ItemEstoque.query.order_by(ItemEstoque.nome).all())

@estoque_bp.route('/gerenciar/item/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_item(id):
    item = ItemEstoque.query.get_or_404(id)
    if request.method == 'POST':
        if request.form.get('acao') == 'excluir': db.session.delete(item); db.session.commit()
        else: item.nome = request.form.get('nome'); item.quantidade = int(request.form.get('quantidade')); db.session.commit()
        return redirect(url_for('estoque.controle_uniforme'))
    return render_template('estoque/editar_item.html', item=item)

@estoque_bp.route('/historico/entrada')
@login_required
def view_historico_entrada(): return render_template('estoque/historico_entrada.html', logs=HistoricoEntrada.query.all())

@estoque_bp.route('/historico/saida')
@login_required
def view_historico_saida(): return render_template('estoque/historico_saida.html', logs=HistoricoSaida.query.all())

@estoque_bp.route('/historico/entrada/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_historico_entrada(id):
    log = HistoricoEntrada.query.get_or_404(id)
    if request.method == 'POST':
        if request.form.get('acao') == 'excluir': db.session.delete(log); db.session.commit(); return redirect(url_for('estoque.view_historico_entrada'))
        log.item_nome = request.form.get('item_nome'); log.quantidade = int(request.form.get('quantidade')); db.session.commit(); return redirect(url_for('estoque.view_historico_entrada'))
    return render_template('estoque/editar_log_entrada.html', log=log)

@estoque_bp.route('/historico/saida/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_historico_saida(id):
    log = HistoricoSaida.query.get_or_404(id)
    if request.method == 'POST':
        if request.form.get('acao') == 'excluir': db.session.delete(log); db.session.commit(); return redirect(url_for('estoque.view_historico_saida'))
        log.colaborador = request.form.get('colaborador'); log.quantidade = int(request.form.get('quantidade')); db.session.commit(); return redirect(url_for('estoque.view_historico_saida'))
    return render_template('estoque/editar_log_saida.html', log=log)
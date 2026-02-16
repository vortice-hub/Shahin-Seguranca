from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import ItemEstoque, HistoricoEntrada, HistoricoSaida
from app.utils import get_brasil_time, permission_required

estoque_bp = Blueprint('estoque', __name__, template_folder='templates')

@estoque_bp.route('/controle-uniforme')
@login_required
@permission_required('ESTOQUE') # Guardião do Stock
def gerenciar_estoque():
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('estoque/admin_estoque.html', itens=itens)

@estoque_bp.route('/estoque/novo', methods=['POST'])
@login_required
@permission_required('ESTOQUE')
def novo_item():
    nome = request.form.get('nome')
    tamanho = request.form.get('tamanho')
    genero = request.form.get('genero')
    if nome:
        item = ItemEstoque(nome=nome, tamanho=tamanho, genero=genero, quantidade=0)
        db.session.add(item); db.session.commit()
        flash('Item adicionado.', 'success')
    return redirect(url_for('estoque.gerenciar_estoque'))

@estoque_bp.route('/estoque/entrada', methods=['POST'])
@login_required
@permission_required('ESTOQUE')
def entrada_estoque():
    item_id = request.form.get('item_id')
    qtd = int(request.form.get('quantidade') or 0)
    item = ItemEstoque.query.get(item_id)
    if item and qtd > 0:
        item.quantidade += qtd
        hist = HistoricoEntrada(item_nome=f"{item.nome} ({item.tamanho})", quantidade=qtd)
        db.session.add(hist); db.session.commit(); flash('Entrada registada.', 'success')
    return redirect(url_for('estoque.gerenciar_estoque'))

@estoque_bp.route('/estoque/saida', methods=['POST'])
@login_required
@permission_required('ESTOQUE')
def saida_estoque():
    item_id = request.form.get('item_id')
    qtd = int(request.form.get('quantidade') or 0)
    colaborador = request.form.get('colaborador')
    item = ItemEstoque.query.get(item_id)
    if item and qtd > 0 and item.quantidade >= qtd:
        item.quantidade -= qtd
        hist = HistoricoSaida(coordenador=current_user.real_name, colaborador=colaborador, item_nome=item.nome, tamanho=item.tamanho, genero=item.genero, quantidade=qtd)
        db.session.add(hist); db.session.commit(); flash('Saída registada.', 'success')
    else: flash('Stock insuficiente.', 'error')
    return redirect(url_for('estoque.gerenciar_estoque'))

@estoque_bp.route('/estoque/excluir/<int:id>')
@login_required
@permission_required('ESTOQUE')
def excluir_item(id):
    item = ItemEstoque.query.get(id)
    if item: db.session.delete(item); db.session.commit(); flash('Item removido.', 'warning')
    return redirect(url_for('estoque.gerenciar_estoque'))



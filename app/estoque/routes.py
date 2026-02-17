from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import ItemEstoque, HistoricoEntrada, HistoricoSaida
from app.utils import get_brasil_time, permission_required

estoque_bp = Blueprint('estoque', __name__, template_folder='templates')

@estoque_bp.route('/controle-uniforme')
@login_required
@permission_required('ESTOQUE')
def gerenciar_estoque():
    """Lista o inventário atual de uniformes."""
    # CORREÇÃO: O template correto é 'estoque/controle_uniforme.html'
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('estoque/controle_uniforme.html', itens=itens)

@estoque_bp.route('/entrada', methods=['GET', 'POST'])
@login_required
@permission_required('ESTOQUE')
def entrada_estoque():
    """Gerencia a chegada de novos itens ao estoque."""
    if request.method == 'POST':
        nome = request.form.get('nome_outros') if request.form.get('nome_select') == 'Outros' else request.form.get('nome_select')
        tamanho = request.form.get('tamanho')
        genero = request.form.get('genero')
        qtd = int(request.form.get('quantidade') or 0)
        
        # Procura se o item já existe para atualizar ou criar novo
        item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
        if not item:
            item = ItemEstoque(
                nome=nome, tamanho=tamanho, genero=genero, 
                quantidade=0, 
                estoque_minimo=int(request.form.get('estoque_minimo') or 5),
                estoque_ideal=int(request.form.get('estoque_ideal') or 20)
            )
            db.session.add(item)
        
        item.quantidade += qtd
        hist = HistoricoEntrada(item_nome=f"{nome} ({tamanho})", quantidade=qtd, data_hora=get_brasil_time())
        db.session.add(hist)
        db.session.commit()
        flash(f'Entrada de {qtd} unidade(s) registrada.', 'success')
        return redirect(url_for('estoque.gerenciar_estoque'))
        
    return render_template('estoque/entrada.html')

@estoque_bp.route('/saida', methods=['GET', 'POST'])
@login_required
@permission_required('ESTOQUE')
def saida_estoque():
    """Registra a entrega de uniforme para um colaborador."""
    itens = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).all()
    
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        qtd = int(request.form.get('quantidade') or 0)
        colaborador = request.form.get('colaborador')
        coordenador = request.form.get('coordenador')
        
        item = ItemEstoque.query.get(item_id)
        if item and item.quantidade >= qtd:
            item.quantidade -= qtd
            hist = HistoricoSaida(
                coordenador=coordenador, 
                colaborador=colaborador, 
                item_nome=item.nome, 
                tamanho=item.tamanho, 
                genero=item.genero, 
                quantidade=qtd,
                data_entrega=get_brasil_time().date()
            )
            db.session.add(hist)
            db.session.commit()
            flash('Saída registrada com sucesso.', 'success')
            return redirect(url_for('estoque.gerenciar_estoque'))
        else:
            flash('Estoque insuficiente para esta operação.', 'error')
            
    return render_template('estoque/saida.html', itens=itens)

@estoque_bp.route('/historico/entrada')
@login_required
@permission_required('ESTOQUE')
def ver_historico_entrada():
    logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).limit(100).all()
    return render_template('estoque/historico_entrada.html', logs=logs)

@estoque_bp.route('/historico/saida')
@login_required
@permission_required('ESTOQUE')
def ver_historico_saida():
    logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).limit(100).all()
    return render_template('estoque/historico_saida.html', logs=logs)

@estoque_bp.route('/gerenciar/item/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('ESTOQUE')
def editar_item(id):
    item = ItemEstoque.query.get_or_404(id)
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            db.session.delete(item)
            db.session.commit()
            flash('Item removido do inventário.', 'warning')
            return redirect(url_for('estoque.gerenciar_estoque'))
        
        item.nome = request.form.get('nome')
        item.tamanho = request.form.get('tamanho')
        item.genero = request.form.get('genero')
        item.quantidade = int(request.form.get('quantidade'))
        item.estoque_minimo = int(request.form.get('estoque_minimo'))
        item.estoque_ideal = int(request.form.get('estoque_ideal'))
        db.session.commit()
        flash('Alterações salvas.', 'success')
        return redirect(url_for('estoque.gerenciar_estoque'))
        
    return render_template('estoque/editar_item.html', item=item)


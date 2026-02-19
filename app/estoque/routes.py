from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import ItemEstoque, HistoricoEntrada, HistoricoSaida
from app.utils import get_brasil_time, permission_required
import pandas as pd
import logging

estoque_bp = Blueprint('estoque', __name__, template_folder='templates')
logger = logging.getLogger(__name__)

@estoque_bp.route('/controle-uniforme')
@login_required
@permission_required('ESTOQUE')
def gerenciar_estoque():
    """Lista o inventário atual de uniformes."""
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

# --- IMPORTAÇÃO DE INVENTÁRIO VIA EXCEL ---
@estoque_bp.route('/controle-uniforme/importar-excel', methods=['POST'])
@login_required
@permission_required('ESTOQUE')
def importar_excel_estoque():
    if 'arquivo_excel' not in request.files:
        flash('Nenhum arquivo enviado.', 'error')
        return redirect(url_for('estoque.gerenciar_estoque'))
    
    file = request.files['arquivo_excel']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('estoque.gerenciar_estoque'))
        
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Formato inválido. Envie uma planilha do Excel (.xlsx ou .xls)', 'error')
        return redirect(url_for('estoque.gerenciar_estoque'))

    try:
        df = pd.read_excel(file)
        df = df.fillna('')
        df.columns = [str(c).strip().lower() for c in df.columns] 
        
        records = df.to_dict('records')
        sucesso_novos, sucesso_atualizados, falhas = 0, 0, 0
        
        for row in records:
            descricao = str(row.get('descricao', '')).strip()
            tamanho = str(row.get('tamanho', '')).strip()
            genero = str(row.get('genero', '')).strip()
            
            if not descricao or not tamanho:
                falhas += 1
                continue
            
            # Converte valores numéricos (com fallback seguro)
            try: quantidade = int(float(row.get('quantidade', 0)))
            except: quantidade = 0
            try: minimo = int(float(row.get('minimo', 5)))
            except: minimo = 5
            try: ideal = int(float(row.get('ideal', 20)))
            except: ideal = 20

            # Verifica se o item já existe na base (combinação exata de Nome + Tamanho + Genero)
            item_existente = ItemEstoque.query.filter_by(nome=descricao, tamanho=tamanho, genero=genero).first()
            
            if item_existente:
                # Sincroniza (substitui) o estoque atual pelos dados da planilha
                item_existente.quantidade = quantidade
                item_existente.estoque_minimo = minimo
                item_existente.estoque_ideal = ideal
                sucesso_atualizados += 1
            else:
                # Cria um novo item no inventário
                novo_item = ItemEstoque(
                    nome=descricao, tamanho=tamanho, genero=genero,
                    quantidade=quantidade, estoque_minimo=minimo, estoque_ideal=ideal
                )
                db.session.add(novo_item)
                sucesso_novos += 1

        db.session.commit()
        
        if sucesso_novos > 0 or sucesso_atualizados > 0:
            flash(f'Inventário sincronizado! {sucesso_novos} novos itens. {sucesso_atualizados} atualizados. {falhas} ignorados.', 'success')
        else:
            flash('Nenhum item válido encontrado na planilha. Verifique os nomes das colunas.', 'error')
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro no import de estoque: {e}")
        flash(f'Erro ao processar o arquivo: {str(e)}', 'error')

    return redirect(url_for('estoque.gerenciar_estoque'))


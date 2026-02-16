from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime

# Importações do Projeto
from app.extensions import db
from app.models import ItemEstoque, HistoricoEntrada, HistoricoSaida
from app.utils import get_brasil_time, master_required

estoque_bp = Blueprint('estoque', __name__, template_folder='templates')

# --- VISUALIZAÇÃO GERAL ---

@estoque_bp.route('/controle-uniforme')
@login_required
@master_required
def controle_uniforme():
    itens = ItemEstoque.query.order_by(ItemEstoque.nome, ItemEstoque.tamanho).all()
    return render_template('estoque/controle_uniforme.html', itens=itens)

# --- MOVIMENTAÇÕES DE ESTOQUE ---

@estoque_bp.route('/entrada', methods=['GET', 'POST'])
@login_required
@master_required
def entrada():
    if request.method == 'POST':
        try:
            # Lógica para pegar nome (Select ou Campo Texto 'Outros')
            nome_select = request.form.get('nome_select')
            nome_outros = request.form.get('nome_outros')
            
            nome_final = nome_outros if nome_select == 'Outros' else nome_select
            
            tamanho = request.form.get('tamanho')
            genero = request.form.get('genero')
            
            # Tratamento de inteiros
            try:
                qtd = int(request.form.get('quantidade') or 1)
                est_min = int(request.form.get('estoque_minimo') or 5)
                est_ideal = int(request.form.get('estoque_ideal') or 20)
            except ValueError:
                flash('Valores numéricos inválidos.', 'error')
                return redirect(url_for('estoque.entrada'))

            # Verifica se o item já existe no banco
            item = ItemEstoque.query.filter_by(
                nome=nome_final, 
                tamanho=tamanho, 
                genero=genero
            ).first()

            if item:
                # Atualiza existente
                item.quantidade += qtd
                item.estoque_minimo = est_min
                item.estoque_ideal = est_ideal
                item.data_atualizacao = get_brasil_time()
            else:
                # Cria novo item
                novo_item = ItemEstoque(
                    nome=nome_final,
                    tamanho=tamanho,
                    genero=genero,
                    quantidade=qtd,
                    estoque_minimo=est_min,
                    estoque_ideal=est_ideal,
                    data_atualizacao=get_brasil_time()
                )
                db.session.add(novo_item)

            # Registro de Log
            log = HistoricoEntrada(
                item_nome=f"{nome_final} ({genero}-{tamanho})",
                quantidade=qtd,
                data_hora=get_brasil_time()
            )
            db.session.add(log)
            
            db.session.commit()
            flash(f'Entrada de {qtd} itens registrada com sucesso.', 'success')
            return redirect(url_for('estoque.controle_uniforme'))

        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao registrar entrada: {e}', 'error')
            
    return render_template('estoque/entrada.html')

@estoque_bp.route('/saida', methods=['GET', 'POST'])
@login_required
@master_required
def saida():
    if request.method == 'POST':
        try:
            item_id = request.form.get('item_id')
            qtd_str = request.form.get('quantidade') or '1'
            qtd = int(qtd_str)
            
            item = ItemEstoque.query.get(item_id)
            
            if not item:
                flash('Item não encontrado.', 'error')
            elif item.quantidade < qtd:
                flash(f'Estoque insuficiente. Disponível: {item.quantidade}', 'error')
            else:
                # Processa a saída
                item.quantidade -= qtd
                item.data_atualizacao = get_brasil_time()
                
                # Data da entrega
                data_input = request.form.get('data')
                try:
                    dt_entrega = datetime.strptime(data_input, '%Y-%m-%d') if data_input else get_brasil_time()
                except ValueError:
                    dt_entrega = get_brasil_time()

                log = HistoricoSaida(
                    coordenador=request.form.get('coordenador'),
                    colaborador=request.form.get('colaborador'),
                    item_nome=item.nome,
                    tamanho=item.tamanho,
                    genero=item.genero,
                    quantidade=qtd,
                    data_entrega=dt_entrega
                )
                db.session.add(log)
                db.session.commit()
                
                flash('Saída registrada com sucesso.', 'success')
                return redirect(url_for('estoque.controle_uniforme'))
                
        except ValueError:
            flash('Erro nos valores numéricos.', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro na saída: {e}', 'error')

    itens = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).order_by(ItemEstoque.nome).all()
    return render_template('estoque/saida.html', itens=itens)

# --- GERENCIAMENTO DE ITENS ---

@estoque_bp.route('/gerenciar/selecao', methods=['GET', 'POST'])
@login_required
@master_required
def selecionar_edicao():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        if item_id:
            return redirect(url_for('estoque.editar_item', id=item_id))
            
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('estoque/selecionar_edicao.html', itens=itens)

@estoque_bp.route('/gerenciar/item/<int:id>', methods=['GET', 'POST'])
@login_required
@master_required
def editar_item(id):
    item = ItemEstoque.query.get_or_404(id)
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        try:
            if acao == 'excluir':
                db.session.delete(item)
                db.session.commit()
                flash('Item excluído do estoque.', 'success')
                return redirect(url_for('estoque.controle_uniforme'))
            
            elif acao == 'salvar':
                item.nome = request.form.get('nome')
                item.tamanho = request.form.get('tamanho')
                item.genero = request.form.get('genero')
                
                # Atualização de valores numéricos
                item.quantidade = int(request.form.get('quantidade'))
                item.estoque_minimo = int(request.form.get('estoque_minimo'))
                item.estoque_ideal = int(request.form.get('estoque_ideal'))
                
                db.session.commit()
                flash('Item atualizado com sucesso.', 'success')
                return redirect(url_for('estoque.controle_uniforme'))
                
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar item: {e}', 'error')
            
    return render_template('estoque/editar_item.html', item=item)

# --- HISTÓRICO ---

@estoque_bp.route('/historico/entrada')
@login_required
@master_required
def view_historico_entrada():
    logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all()
    return render_template('estoque/historico_entrada.html', logs=logs)

@estoque_bp.route('/historico/saida')
@login_required
@master_required
def view_historico_saida():
    logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all()
    return render_template('estoque/historico_saida.html', logs=logs)

@estoque_bp.route('/historico/entrada/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@master_required
def editar_historico_entrada(id):
    log = HistoricoEntrada.query.get_or_404(id)
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        try:
            if acao == 'excluir':
                db.session.delete(log)
                db.session.commit()
                flash('Registro de histórico removido.', 'success')
                return redirect(url_for('estoque.view_historico_entrada'))
            
            elif acao == 'salvar':
                log.item_nome = request.form.get('item_nome')
                log.quantidade = int(request.form.get('quantidade'))
                
                dt_str = request.form.get('data')
                if dt_str:
                    log.data_hora = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M')
                    
                db.session.commit()
                flash('Registro de histórico corrigido.', 'success')
                return redirect(url_for('estoque.view_historico_entrada'))
                
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {e}', 'error')

    return render_template('estoque/editar_log_entrada.html', log=log)

@estoque_bp.route('/historico/saida/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@master_required
def editar_historico_saida(id):
    log = HistoricoSaida.query.get_or_404(id)
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        try:
            if acao == 'excluir':
                db.session.delete(log)
                db.session.commit()
                flash('Registro de entrega removido.', 'success')
                return redirect(url_for('estoque.view_historico_saida'))
            
            elif acao == 'salvar':
                log.coordenador = request.form.get('coordenador')
                log.colaborador = request.form.get('colaborador')
                log.item_nome = request.form.get('item_nome')
                log.quantidade = int(request.form.get('quantidade'))
                
                dt_str = request.form.get('data')
                if dt_str:
                    log.data_entrega = datetime.strptime(dt_str, '%Y-%m-%d')
                
                db.session.commit()
                flash('Registro de entrega corrigido.', 'success')
                return redirect(url_for('estoque.view_historico_saida'))
                
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {e}', 'error')

    return render_template('estoque/editar_log_saida.html', log=log)


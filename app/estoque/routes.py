from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
import logging

from app.extensions import db
from app.utils import permission_required, requires_plan

# --- IMPORTAÇÃO DOS NOVOS SERVICES E REPOSITORIES ---
from app.services.estoque_service import EstoqueService
from app.repositories.estoque_repository import (ItemEstoqueRepository, HistoricoEntradaRepository, 
                                                 HistoricoSaidaRepository, SolicitacaoUniformeRepository)

estoque_bp = Blueprint('estoque', __name__, template_folder='templates', url_prefix='/estoque')
logger = logging.getLogger(__name__)

@estoque_bp.route('/gerenciar')
@login_required
@requires_plan('Pro')
@permission_required('ESTOQUE')
def gerenciar_estoque():
    item_repo = ItemEstoqueRepository()
    itens = item_repo.get_all_ordered()
    return render_template('estoque/controle_uniforme.html', itens=itens)

@estoque_bp.route('/entrada', methods=['GET', 'POST'])
@login_required
@requires_plan('Pro')
@permission_required('ESTOQUE')
def entrada_estoque():
    if request.method == 'POST':
        estoque_service = EstoqueService()
        try:
            qtd = estoque_service.registrar_entrada(request.form)
            flash(f'Entrada de {qtd} unidade(s) registrada.', 'success')
            return redirect(url_for('estoque.gerenciar_estoque'))
        except Exception as e:
            flash(f'Erro interno: {e}', 'error')
            
    return render_template('estoque/entrada.html')

@estoque_bp.route('/saida', methods=['GET', 'POST'])
@login_required
@requires_plan('Pro')
@permission_required('ESTOQUE')
def saida_estoque():
    item_repo = ItemEstoqueRepository()
    itens = item_repo.get_disponiveis()
    
    if request.method == 'POST':
        estoque_service = EstoqueService()
        try:
            estoque_service.registrar_saida(request.form)
            flash('Saída registrada com sucesso.', 'success')
            return redirect(url_for('estoque.gerenciar_estoque'))
        except ValueError as ve:
            flash(str(ve), 'error')
        except Exception as e:
            flash(f'Erro interno: {e}', 'error')
            
    return render_template('estoque/saida.html', itens=itens)

@estoque_bp.route('/historico/entrada')
@login_required
@requires_plan('Pro')
@permission_required('ESTOQUE')
def ver_historico_entrada():
    entrada_repo = HistoricoEntradaRepository()
    logs = entrada_repo.get_recentes()
    return render_template('estoque/historico_entrada.html', logs=logs)

@estoque_bp.route('/historico/saida')
@login_required
@requires_plan('Pro')
@permission_required('ESTOQUE')
def ver_historico_saida():
    saida_repo = HistoricoSaidaRepository()
    logs = saida_repo.get_recentes()
    return render_template('estoque/historico_saida.html', logs=logs)

@estoque_bp.route('/gerenciar/item/<int:id>', methods=['GET', 'POST'])
@login_required
@requires_plan('Pro')
@permission_required('ESTOQUE')
def editar_item(id):
    item_repo = ItemEstoqueRepository()
    item = item_repo.get_by_id(id)
    if not item: return redirect(url_for('estoque.gerenciar_estoque'))

    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'excluir':
            item_repo.delete(item)
            item_repo.commit()
            flash('Item removido do inventário.', 'warning')
            return redirect(url_for('estoque.gerenciar_estoque'))
        
        item.nome = request.form.get('nome')
        item.tamanho = request.form.get('tamanho')
        item.genero = request.form.get('genero')
        item.quantidade = int(request.form.get('quantidade'))
        item.estoque_minimo = int(request.form.get('estoque_minimo'))
        item.estoque_ideal = int(request.form.get('estoque_ideal'))
        item_repo.commit()
        flash('Alterações salvas.', 'success')
        return redirect(url_for('estoque.gerenciar_estoque'))
        
    return render_template('estoque/editar_item.html', item=item)

@estoque_bp.route('/controle-uniforme/importar-excel', methods=['POST'])
@login_required
@requires_plan('Pro')
@permission_required('ESTOQUE')
def importar_excel_estoque():
    if 'arquivo_excel' not in request.files or request.files['arquivo_excel'].filename == '':
        flash('Nenhum arquivo válido selecionado.', 'error')
        return redirect(url_for('estoque.gerenciar_estoque'))
        
    file = request.files['arquivo_excel']
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Formato inválido. Envie uma planilha do Excel (.xlsx ou .xls)', 'error')
        return redirect(url_for('estoque.gerenciar_estoque'))

    try:
        estoque_service = EstoqueService()
        novos, atualizados, falhas = estoque_service.processar_planilha_excel(file.read())
        if novos > 0 or atualizados > 0:
            flash(f'Inventário sincronizado! {novos} novos itens. {atualizados} atualizados. {falhas} ignorados.', 'success')
        else:
            flash('Nenhum item válido encontrado na planilha. Verifique os nomes das colunas.', 'error')
    except Exception as e:
        logger.error(f"Erro no import de estoque: {e}")
        flash(f'Erro ao processar o arquivo: {str(e)}', 'error')

    return redirect(url_for('estoque.gerenciar_estoque'))

@estoque_bp.route('/api/tamanhos', methods=['GET'])
@login_required
@requires_plan('Pro')
def api_buscar_tamanhos():
    nome_item = request.args.get('nome')
    if not nome_item: return jsonify([])
    
    item_repo = ItemEstoqueRepository()
    itens = item_repo.get_tamanhos_por_nome(nome_item)
    
    resultados = [{'id': item.id, 'tamanho': item.tamanho, 'genero': item.genero, 'quantidade': item.quantidade} for item in itens]
    return jsonify(resultados)

@estoque_bp.route('/solicitar-uniforme', methods=['GET', 'POST'])
@login_required
@requires_plan('Pro')
def solicitar_uniforme():
    item_repo = ItemEstoqueRepository()
    solic_repo = SolicitacaoUniformeRepository()
    
    if request.method == 'POST':
        estoque_service = EstoqueService()
        try:
            estoque_service.solicitar_uniforme_colaborador(current_user, request.form)
            flash('O seu pedido foi enviado ao Departamento de RH! Aguarde a aprovação.', 'success')
        except ValueError as ve:
            flash(f'Erro: {str(ve)}', 'error')
        except Exception as e:
            flash(f'Erro interno: {str(e)}', 'error')
            
        return redirect(url_for('estoque.solicitar_uniforme'))
    
    nomes_disponiveis = item_repo.get_nomes_disponiveis()
    minhas_solicitacoes = solic_repo.get_by_user(current_user.id)
    
    return render_template('estoque/solicitar_uniforme.html', nomes_disponiveis=nomes_disponiveis, solicitacoes=minhas_solicitacoes)

@estoque_bp.route('/admin/solicitacoes', methods=['GET', 'POST'])
@login_required
@requires_plan('Pro')
@permission_required('ESTOQUE')
def gestao_solicitacoes():
    solic_repo = SolicitacaoUniformeRepository()
    
    if request.method == 'POST':
        estoque_service = EstoqueService()
        try:
            estoque_service.avaliar_solicitacao(current_user, request.form.get('solicitacao_id'), request.form.get('acao'))
            if request.form.get('acao') == 'aprovar':
                flash('Pedido APROVADO com sucesso! O inventário foi deduzido automaticamente.', 'success')
            else:
                flash('Pedido de EPI Recusado.', 'warning')
        except ValueError as ve:
            flash(str(ve), 'error')
        except Exception as e:
            flash(f'Erro interno: {str(e)}', 'error')
            
        return redirect(url_for('estoque.gestao_solicitacoes'))
        
    todas_solicitacoes = solic_repo.get_todas_ordenadas()
    return render_template('estoque/gestao_pedidos_uniforme.html', solicitacoes=todas_solicitacoes)


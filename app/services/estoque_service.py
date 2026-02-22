import pandas as pd
import io
import logging
from app.models import ItemEstoque, HistoricoEntrada, HistoricoSaida, SolicitacaoUniforme, User
from app.repositories.estoque_repository import (ItemEstoqueRepository, HistoricoEntradaRepository, 
                                                 HistoricoSaidaRepository, SolicitacaoUniformeRepository)
from app.utils import get_brasil_time, enviar_notificacao

logger = logging.getLogger(__name__)

class EstoqueService:
    def __init__(self):
        self.item_repo = ItemEstoqueRepository()
        self.entrada_repo = HistoricoEntradaRepository()
        self.saida_repo = HistoricoSaidaRepository()
        self.solic_repo = SolicitacaoUniformeRepository()

    def registrar_entrada(self, form_data):
        nome = form_data.get('nome_outros') if form_data.get('nome_select') == 'Outros' else form_data.get('nome_select')
        tamanho = form_data.get('tamanho')
        genero = form_data.get('genero')
        qtd = int(form_data.get('quantidade') or 0)
        
        item = self.item_repo.get_by_detalhes(nome, tamanho, genero)
        if not item:
            item = ItemEstoque(
                nome=nome, tamanho=tamanho, genero=genero, quantidade=0, 
                estoque_minimo=int(form_data.get('estoque_minimo') or 5),
                estoque_ideal=int(form_data.get('estoque_ideal') or 20)
            )
            self.item_repo.add(item)
        
        item.quantidade += qtd
        hist = HistoricoEntrada(item_nome=f"{nome} ({tamanho})", quantidade=qtd, data_hora=get_brasil_time())
        self.entrada_repo.add(hist)
        
        self.item_repo.commit()
        return qtd

    def registrar_saida(self, form_data):
        item_id = form_data.get('item_id')
        qtd = int(form_data.get('quantidade') or 0)
        colaborador = form_data.get('colaborador')
        coordenador = form_data.get('coordenador')
        
        item = self.item_repo.get_by_id(item_id)
        if not item or item.quantidade < qtd:
            raise ValueError('Estoque insuficiente para esta operação.')
            
        item.quantidade -= qtd
        hist = HistoricoSaida(
            coordenador=coordenador, colaborador=colaborador, item_nome=item.nome, 
            tamanho=item.tamanho, genero=item.genero, quantidade=qtd, data_entrega=get_brasil_time().date()
        )
        self.saida_repo.add(hist)
        self.saida_repo.commit()

    def processar_planilha_excel(self, file_bytes):
        df = pd.read_excel(io.BytesIO(file_bytes))
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
            
            quantidade = int(float(row.get('quantidade', 0))) if row.get('quantidade') else 0
            minimo = int(float(row.get('minimo', 5))) if row.get('minimo') else 5
            ideal = int(float(row.get('ideal', 20))) if row.get('ideal') else 20

            item_existente = self.item_repo.get_by_detalhes(descricao, tamanho, genero)
            
            if item_existente:
                item_existente.quantidade = quantidade
                item_existente.estoque_minimo = minimo
                item_existente.estoque_ideal = ideal
                sucesso_atualizados += 1
            else:
                novo_item = ItemEstoque(nome=descricao, tamanho=tamanho, genero=genero, quantidade=quantidade, estoque_minimo=minimo, estoque_ideal=ideal)
                self.item_repo.add(novo_item)
                sucesso_novos += 1

        self.item_repo.commit()
        return sucesso_novos, sucesso_atualizados, falhas

    def solicitar_uniforme_colaborador(self, user, form_data):
        item_id = form_data.get('item_id')
        quantidade = int(form_data.get('quantidade') or 1)
        
        item = self.item_repo.get_by_id(item_id)
        if not item or item.quantidade < quantidade:
            raise ValueError('O item selecionado não possui stock suficiente no momento.')
        
        nova_solic = SolicitacaoUniforme(
            user_id=user.id, item_id=item.id, item_nome=item.nome, tamanho=item.tamanho,
            genero=item.genero, quantidade=quantidade, status='Pendente'
        )
        self.solic_repo.add(nova_solic)
        self.solic_repo.commit()
        
        master = User.query.filter_by(username='50097952800').first()
        if master: enviar_notificacao(master.id, f"{user.real_name} solicitou {quantidade}x {item.nome}.", "/estoque/solicitacoes")

    def avaliar_solicitacao(self, coordenador, solic_id, acao):
        solicitacao = self.solic_repo.get_by_id(solic_id)
        if not solicitacao: raise ValueError("Solicitação não encontrada.")
            
        if acao == 'aprovar':
            item = self.item_repo.get_by_id(solicitacao.item_id)
            if not item or item.quantidade < solicitacao.quantidade:
                raise ValueError(f'O stock atual é insuficiente para aprovar as {solicitacao.quantidade} unidades de {solicitacao.item_nome}.')
            
            solicitacao.status = 'Aprovado'
            solicitacao.data_resposta = get_brasil_time()
            item.quantidade -= solicitacao.quantidade
            
            hist = HistoricoSaida(
                coordenador=coordenador.real_name, colaborador=solicitacao.user.real_name, 
                item_nome=item.nome, tamanho=item.tamanho, genero=item.genero, 
                quantidade=solicitacao.quantidade, data_entrega=get_brasil_time().date()
            )
            self.saida_repo.add(hist)
            enviar_notificacao(solicitacao.user_id, f"Seu pedido de EPI ({solicitacao.item_nome}) foi APROVADO.", "/estoque/solicitar")
            
        elif acao == 'recusar':
            solicitacao.status = 'Recusado'
            solicitacao.data_resposta = get_brasil_time()
            enviar_notificacao(solicitacao.user_id, f"Seu pedido de EPI ({solicitacao.item_nome}) foi RECUSADO.", "/estoque/solicitar")
            
        self.solic_repo.commit()


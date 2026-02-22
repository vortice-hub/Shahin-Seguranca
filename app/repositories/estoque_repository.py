from app.models import ItemEstoque, HistoricoEntrada, HistoricoSaida, SolicitacaoUniforme
from app.repositories.base_repository import BaseRepository
from app.extensions import db

class ItemEstoqueRepository(BaseRepository):
    def __init__(self):
        super().__init__(ItemEstoque)
        
    def get_all_ordered(self):
        return self.get_query().order_by(ItemEstoque.nome).all()

    def get_disponiveis(self):
        return self.get_query().filter(ItemEstoque.quantidade > 0).all()

    def get_by_detalhes(self, nome, tamanho, genero):
        return self.get_query().filter_by(nome=nome, tamanho=tamanho, genero=genero).first()

    def get_tamanhos_por_nome(self, nome):
        return self.get_query().filter(ItemEstoque.nome == nome, ItemEstoque.quantidade > 0).all()

    def get_nomes_disponiveis(self):
        # Utiliza o get_query() para garantir que a busca é apenas na empresa atual
        itens = self.get_query().filter(ItemEstoque.quantidade > 0).with_entities(ItemEstoque.nome).distinct().all()
        return [n[0] for n in itens]

class HistoricoEntradaRepository(BaseRepository):
    def __init__(self):
        super().__init__(HistoricoEntrada)
        
    def get_recentes(self, limit=100):
        return self.get_query().order_by(HistoricoEntrada.data_hora.desc()).limit(limit).all()

class HistoricoSaidaRepository(BaseRepository):
    def __init__(self):
        super().__init__(HistoricoSaida)
        
    def get_recentes(self, limit=100):
        return self.get_query().order_by(HistoricoSaida.data_entrega.desc()).limit(limit).all()

class SolicitacaoUniformeRepository(BaseRepository):
    def __init__(self):
        super().__init__(SolicitacaoUniforme)
        
    def get_by_user(self, user_id, limit=20):
        return self.get_query().filter_by(user_id=user_id).order_by(SolicitacaoUniforme.data_solicitacao.desc()).limit(limit).all()
        
    def get_todas_ordenadas(self, limit=100):
        return self.get_query().order_by(
            db.case({ 'Pendente': 1, 'Aprovado': 2, 'Recusado': 3 }, value=SolicitacaoUniforme.status),
            SolicitacaoUniforme.data_solicitacao.desc()
        ).limit(limit).all()


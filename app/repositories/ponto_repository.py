from app.models import PontoRegistro, PontoResumo, PontoAjuste, SolicitacaoAusencia, User
from app.repositories.base_repository import BaseRepository
from sqlalchemy import func

class PontoRegistroRepository(BaseRepository):
    def __init__(self):
        super().__init__(PontoRegistro)

    def get_by_user_and_date(self, user_id, date_obj):
        return self.get_query().filter_by(user_id=user_id, data_registro=date_obj).order_by(PontoRegistro.hora_registro).all()

    def get_last_by_user_and_date(self, user_id, date_obj):
        return self.get_query().filter_by(user_id=user_id, data_registro=date_obj).order_by(PontoRegistro.hora_registro.desc()).first()
    
    def get_last_by_user(self, user_id):
         return self.get_query().filter_by(user_id=user_id).order_by(PontoRegistro.id.desc()).first()

class PontoResumoRepository(BaseRepository):
    def __init__(self):
        super().__init__(PontoResumo)

    def get_by_user_and_date(self, user_id, date_obj):
        return self.get_query().filter_by(user_id=user_id, data_referencia=date_obj).first()

    def get_by_user_and_month(self, user_id, ano, mes):
        return self.get_query().filter(
            PontoResumo.user_id == user_id, 
            func.extract('year', PontoResumo.data_referencia) == ano, 
            func.extract('month', PontoResumo.data_referencia) == mes
        ).order_by(PontoResumo.data_referencia).all()

    def get_faltas_ultimos_dias(self, user_id, data_inicio):
        return self.get_query().filter(
            PontoResumo.user_id == user_id, 
            PontoResumo.data_referencia >= data_inicio, 
            PontoResumo.status_dia == 'Falta'
        ).count()

class PontoAjusteRepository(BaseRepository):
    def __init__(self):
        super().__init__(PontoAjuste)

    def get_pendentes(self):
         return self.get_query().filter_by(status='Pendente').order_by(PontoAjuste.created_at.desc()).all()
    
    def get_by_user(self, user_id, limit=20):
        return self.get_query().filter_by(user_id=user_id).order_by(PontoAjuste.created_at.desc()).limit(limit).all()

class SolicitacaoAusenciaRepository(BaseRepository):
    def __init__(self):
        super().__init__(SolicitacaoAusencia)

    def get_aprovada_por_data(self, user_id, data_ref):
        return self.get_query().filter(
            SolicitacaoAusencia.user_id == user_id, 
            SolicitacaoAusencia.status == 'Aprovado', 
            SolicitacaoAusencia.data_inicio <= data_ref, 
            SolicitacaoAusencia.data_fim >= data_ref
        ).first()

    def get_by_user(self, user_id):
        return self.get_query().filter_by(user_id=user_id).order_by(SolicitacaoAusencia.data_solicitacao.desc()).all()

    def get_by_user_and_type(self, user_id, tipo):
         return self.get_query().filter(
            SolicitacaoAusencia.user_id == user_id, 
            SolicitacaoAusencia.tipo_ausencia == tipo, 
            SolicitacaoAusencia.status.in_(['Aprovado', 'Pendente'])
        ).all()

    def get_todas(self):
        return self.get_query().order_by(SolicitacaoAusencia.data_solicitacao.desc()).all()


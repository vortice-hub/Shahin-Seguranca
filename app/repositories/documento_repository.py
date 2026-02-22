from app.models import Holerite, Recibo, AssinaturaDigital, Atestado
from app.repositories.base_repository import BaseRepository
from app.extensions import db

class HoleriteRepository(BaseRepository):
    def __init__(self):
        super().__init__(Holerite)
        
    def get_pendentes_revisao(self):
        return self.get_query().filter_by(status='Revisao').all()

    def get_by_user(self, user_id):
        return self.get_query().filter_by(user_id=user_id).order_by(Holerite.enviado_em.desc()).all()

class ReciboRepository(BaseRepository):
    def __init__(self):
        super().__init__(Recibo)
        
    def get_by_user(self, user_id):
        return self.get_query().filter_by(user_id=user_id).order_by(Recibo.created_at.desc()).all()

class AtestadoRepository(BaseRepository):
    def __init__(self):
        super().__init__(Atestado)
        
    def get_by_user(self, user_id):
        return self.get_query().filter_by(user_id=user_id).order_by(Atestado.data_envio.desc()).all()

class AssinaturaDigitalRepository(BaseRepository):
    def __init__(self):
        super().__init__(AssinaturaDigital)

    def get_by_user(self, user_id):
        return self.get_query().filter_by(user_id=user_id).order_by(AssinaturaDigital.data_assinatura.desc()).all()


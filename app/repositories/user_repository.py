from app.models import User, PreCadastro
from app.repositories.base_repository import BaseRepository

class UserRepository(BaseRepository):
    def __init__(self):
        super().__init__(User)

    def get_by_cpf(self, cpf):
        return self.get_query().filter_by(cpf=cpf).first()

    def get_active_users_paginated(self, page, per_page=15):
        return self.get_query().filter(
            User.username != '12345678900', 
            User.username != 'terminal'
        ).order_by(User.real_name).paginate(page=page, per_page=per_page, error_out=False)

    def get_gestores(self, exclude_id=None):
        q = self.get_query().filter(User.username != '12345678900', User.username != 'terminal')
        if exclude_id:
            q = q.filter(User.id != exclude_id)
        return q.order_by(User.real_name).all()

    def get_subordinados(self, gestor_id):
        return self.get_query().filter_by(gestor_id=gestor_id).all()


class PreCadastroRepository(BaseRepository):
    def __init__(self):
        super().__init__(PreCadastro)
        
    def get_by_cpf(self, cpf):
        return self.get_query().filter_by(cpf=cpf).first()
        
    def get_all_ordered(self):
        return self.get_query().order_by(PreCadastro.nome_previsto).all()


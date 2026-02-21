from flask import g
from app.extensions import db

class BaseRepository:
    """
    Guardião Multi-Tenant.
    Garante que todas as operações no banco sejam isoladas pela empresa atual.
    """
    def __init__(self, model):
        self.model = model

    def get_query(self):
        """Retorna uma query já filtrada pela empresa logada (se a tabela for Multi-Tenant)."""
        if hasattr(self.model, 'empresa_id') and hasattr(g, 'empresa_id'):
            return self.model.query.filter_by(empresa_id=g.empresa_id)
        return self.model.query

    def get_by_id(self, id):
        return self.get_query().filter_by(id=id).first()

    def get_all(self):
        return self.get_query().all()

    def add(self, entity):
        # Injeta automaticamente a empresa ao criar um registo novo
        if hasattr(entity, 'empresa_id') and hasattr(g, 'empresa_id'):
            entity.empresa_id = g.empresa_id
        db.session.add(entity)

    def delete(self, entity):
        db.session.delete(entity)

    def commit(self):
        db.session.commit()

    def rollback(self):
        db.session.rollback()


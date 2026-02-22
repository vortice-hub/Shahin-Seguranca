from app.models import Empresa
from app.extensions import db

class EmpresaRepository:
    def get_all(self):
        return Empresa.query.order_by(Empresa.created_at.desc()).all()

    def get_by_id(self, id):
        return Empresa.query.get(id)

    def get_by_slug(self, slug):
        return Empresa.query.filter_by(slug=slug).first()

    def add(self, empresa):
        db.session.add(empresa)

    def commit(self):
        db.session.commit()


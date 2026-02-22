from app.models import Empresa, Role, Permission, User
from app.repositories.empresa_repository import EmpresaRepository
from app.extensions import db
import re

class EmpresaService:
    def __init__(self):
        self.empresa_repo = EmpresaRepository()

    def criar_nova_conta_cliente(self, dados_empresa, dados_master):
        """
        Lógica complexa de Onboarding SaaS:
        1. Cria a Empresa
        2. Cria o Cargo 'Master' para essa empresa
        3. Vincula todas as permissões existentes a esse cargo
        4. Cria o utilizador dono (Master)
        """
        nome_empresa = dados_empresa.get('nome')
        slug = re.sub(r'[^a-z0-9]', '', nome_empresa.lower())
        
        if self.empresa_repo.get_by_slug(slug):
            raise ValueError("Uma empresa com este nome (ou slug similar) já existe.")

        # 1. Criar Empresa
        nova_empresa = Empresa(
            nome=nome_empresa,
            slug=slug,
            plano=dados_empresa.get('plano', 'Standard'),
            ativa=True,
            features_json={"ponto": True, "documentos": True, "estoque": True}
        )
        self.empresa_repo.add(nova_empresa)
        db.session.flush() # Gera o ID da empresa antes do commit final

        # 2. Criar Cargo Master da Nova Empresa
        cargo_master = Role(
            nome="Diretoria / Master",
            descricao="Acesso total às ferramentas da empresa",
            empresa_id=nova_empresa.id
        )
        # 3. Dar todas as permissões do sistema para este novo cargo
        todas_perms = Permission.query.all()
        cargo_master.permissions.extend(todas_perms)
        db.session.add(cargo_master)
        db.session.flush()

        # 4. Criar o Primeiro Utilizador (O dono do cliente)
        novo_user = User(
            username=dados_master.get('cpf').replace('.', '').replace('-', ''),
            real_name=dados_master.get('nome_completo'),
            cpf=dados_master.get('cpf'),
            role="Master",
            cargo_id=cargo_master.id,
            empresa_id=nova_empresa.id,
            is_first_access=True
        )
        novo_user.set_password(dados_master.get('senha_provisoria', '123456'))
        db.session.add(novo_user)

        self.empresa_repo.commit()
        return nova_empresa, novo_user


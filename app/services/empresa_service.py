from app.models import Empresa, Role, Permission, User
from app.repositories.empresa_repository import EmpresaRepository
from app.extensions import db
import re

class EmpresaService:
    def __init__(self):
        self.empresa_repo = EmpresaRepository()

    def criar_nova_conta_cliente(self, dados_empresa, dados_master):
        """
        Lógica de Onboarding SaaS:
        1. Cria a Empresa
        2. Cria o Cargo 'Master' para essa empresa
        3. Vincula todas as permissões existentes a esse cargo
        4. Cria o utilizador dono (Master)
        """
        nome_empresa = dados_empresa.get('nome')
        slug = re.sub(r'[^a-z0-9]', '', nome_empresa.lower())
        
        if self.empresa_repo.get_by_slug(slug):
            raise ValueError("Uma empresa com este nome (ou slug similar) já existe.")

        # 1. Criar Empresa com cores padrão iniciais
        nova_empresa = Empresa(
            nome=nome_empresa,
            slug=slug,
            plano=dados_empresa.get('plano', 'Standard'),
            ativa=True,
            features_json={"ponto": True, "documentos": True, "estoque": True},
            config_json={"cor_primaria": "#2563eb", "cor_hover": "#1d4ed8"}
        )
        self.empresa_repo.add(nova_empresa)
        db.session.flush() 

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

    # 🎨 NOVO: ATUALIZAR IDENTIDADE VISUAL (WHITE-LABEL)
    def atualizar_branding(self, empresa_id, config_visual):
        """Atualiza as cores e a logo no config_json da empresa."""
        empresa = self.empresa_repo.get_by_id(empresa_id)
        if not empresa:
            raise ValueError("Empresa não encontrada.")
            
        # Recupera o JSON atual ou cria um novo se estiver vazio
        config = empresa.config_json or {}
        
        # Atualiza os campos específicos de branding
        config['cor_primaria'] = config_visual.get('cor_primaria', '#2563eb')
        config['cor_hover'] = config_visual.get('cor_hover', '#1d4ed8')
        config['logo_url'] = config_visual.get('logo_url', '')
        
        # Grava de volta no banco de dados
        empresa.config_json = config
        db.session.commit()
        return empresa


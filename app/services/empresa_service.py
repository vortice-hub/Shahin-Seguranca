import os
import re
from google.cloud import storage
from sqlalchemy.orm.attributes import flag_modified
from app.models import Empresa, Role, Permission, User
from app.repositories.empresa_repository import EmpresaRepository
from app.extensions import db

class EmpresaService:
    def __init__(self):
        self.empresa_repo = EmpresaRepository()
        self.bucket_name = os.environ.get('VORTICE_BUCKET_NAME', 'vortice-assets')

    def _upload_logo_to_gcs(self, empresa_slug, file_obj):
        """Faz o upload do ficheiro para o Google Cloud Storage e retorna o link público."""
        try:
            client = storage.Client()
            bucket = client.bucket(self.bucket_name)
            
            ext = file_obj.filename.rsplit('.', 1)[1].lower()
            blob_name = f"logos/logo_{empresa_slug}.{ext}"
            blob = bucket.blob(blob_name)
            
            blob.upload_from_file(file_obj, content_type=file_obj.content_type)
            
            # REMOVIDO: blob.make_public()
            # Como o Bucket tem "Uniform Access" ativado, a permissão pública 
            # deve ser dada ao Bucket inteiro via IAM no painel do GCP.
            
            return blob.public_url
        except Exception as e:
            print(f"Erro no upload GCS: {e}")
            return None

    def criar_nova_conta_cliente(self, dados_empresa, dados_master, file_logo=None):
        """Lógica de Onboarding SaaS com upload de logo inicial."""
        nome_empresa = dados_empresa.get('nome')
        slug = re.sub(r'[^a-z0-9]', '', nome_empresa.lower())
        
        if self.empresa_repo.get_by_slug(slug):
            raise ValueError("Uma empresa com este nome (ou slug similar) já existe.")

        # Processa a logo no momento da criação se fornecida
        logo_url = ""
        if file_logo and file_logo.filename != '':
            logo_url = self._upload_logo_to_gcs(slug, file_logo)

        nova_empresa = Empresa(
            nome=nome_empresa,
            slug=slug,
            plano=dados_empresa.get('plano', 'Standard'),
            ativa=True,
            features_json={"ponto": True, "documentos": True, "estoque": True},
            config_json={
                "cor_primaria": "#2563eb", 
                "cor_hover": "#1d4ed8", 
                "logo_url": logo_url
            }
        )
        self.empresa_repo.add(nova_empresa)
        db.session.flush() 

        cargo_master = Role(
            nome="Diretoria / Master",
            descricao="Acesso total às ferramentas da empresa",
            empresa_id=nova_empresa.id
        )
        
        todas_perms = Permission.query.all()
        cargo_master.permissions.extend(todas_perms)
        db.session.add(cargo_master)
        db.session.flush()

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

    def atualizar_branding(self, empresa_id, config_visual, file_logo=None):
        """Atualiza o branding existente."""
        empresa = self.empresa_repo.get_by_id(empresa_id)
        if not empresa:
            raise ValueError("Empresa não encontrada.")
            
        config = dict(empresa.config_json) if empresa.config_json else {}
        
        if file_logo and file_logo.filename != '':
            url_gcs = self._upload_logo_to_gcs(empresa.slug, file_logo)
            if url_gcs:
                config['logo_url'] = url_gcs
        else:
            config['logo_url'] = config_visual.get('logo_url', config.get('logo_url', ''))
        
        config['cor_primaria'] = config_visual.get('cor_primaria', '#2563eb')
        config['cor_hover'] = config_visual.get('cor_hover', '#1d4ed8')
        
        empresa.config_json = config
        flag_modified(empresa, "config_json")
        
        db.session.commit()
        return empresa

    def excluir_empresa_completo(self, empresa_id):
        """Remove a empresa e todos os dados vinculados (Cascade)."""
        empresa = self.empresa_repo.get_by_id(empresa_id)
        if not empresa:
            raise ValueError("Empresa não encontrada para exclusão.")
        
        # O banco de dados cuidará de apagar usuários e registros vinculados se as FKs estiverem com CASCADE
        db.session.delete(empresa)
        db.session.commit()
        return True


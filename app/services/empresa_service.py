import os
import re
import io
from PIL import Image
from google.cloud import storage
from sqlalchemy.orm.attributes import flag_modified
from app.extensions import db

# CORREÇÃO: Importamos TODOS os modelos para fazer a limpeza cirúrgica sem erros de chave estrangeira
from app.models import (Empresa, Role, Permission, User, PontoRegistro, PontoResumo, 
                        PontoAjuste, Notificacao, SolicitacaoAusencia, SolicitacaoUniforme, 
                        ItemEstoque, Holerite, Recibo, AssinaturaDigital, PreCadastro, 
                        Atestado, PushSubscription, PeriodoAquisitivo)
from app.repositories.empresa_repository import EmpresaRepository


class EmpresaService:
    def __init__(self):
        self.empresa_repo = EmpresaRepository()
        self.bucket_name = os.environ.get('VORTICE_BUCKET', 'vortice-assets')

    def _upload_logo_to_gcs(self, empresa_slug, file_obj):
        """Redimensiona e faz o upload para o GCS."""
        try:
            client = storage.Client()
            bucket = client.bucket(self.bucket_name)
            
            ext = file_obj.filename.rsplit('.', 1)[-1].lower()
            if ext not in ['jpg', 'jpeg', 'png', 'webp']:
                ext = 'png'

            img = Image.open(file_obj.stream)
            if img.mode in ("RGBA", "P") and ext in ["jpg", "jpeg"]:
                img = img.convert("RGB")
                
            img.thumbnail((256, 256), Image.Resampling.LANCZOS)
            
            img_byte_arr = io.BytesIO()
            img_format = 'PNG' if ext == 'png' else ('WEBP' if ext == 'webp' else 'JPEG')
            img.save(img_byte_arr, format=img_format, optimize=True, quality=85)
            img_byte_arr.seek(0)

            blob_name = f"{empresa_slug}/logo/logo_{empresa_slug}.{ext}"
            blob = bucket.blob(blob_name)
            blob.upload_from_file(img_byte_arr, content_type=f'image/{ext}')
            
            return f"/cdn/logos/{empresa_slug}"
        except Exception as e:
            print(f"ERRO GRAVE NO UPLOAD/PILLOW: {e}")
            return None

    def criar_nova_conta_cliente(self, dados_empresa, dados_master, file_logo=None):
        """Lógica de Onboarding SaaS."""
        nome_empresa = dados_empresa.get('nome')
        slug = re.sub(r'[^a-z0-9]', '', nome_empresa.lower())
        
        if self.empresa_repo.get_by_slug(slug):
            raise ValueError("Uma empresa com este nome (ou slug similar) já existe.")

        logo_url = ""
        if file_logo and file_logo.filename != '':
            logo_url = self._upload_logo_to_gcs(slug, file_logo) or ""

        nova_empresa = Empresa(
            nome=nome_empresa,
            slug=slug,
            plano=dados_empresa.get('plano', 'Standard'),
            ativa=True,
            features_json={"ponto": True, "documentos": True, "estoque": True},
            config_json={"cor_primaria": "#2563eb", "cor_hover": "#1d4ed8", "logo_url": logo_url}
        )
        self.empresa_repo.add(nova_empresa)
        db.session.flush() 

        cargo_master = Role(nome="Diretoria / Master", descricao="Acesso total", empresa_id=nova_empresa.id)
        cargo_master.permissions.extend(Permission.query.all())
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
        empresa = self.empresa_repo.get_by_id(empresa_id)
        if not empresa: raise ValueError("Empresa não encontrada.")
            
        config = dict(empresa.config_json) if empresa.config_json else {}
        
        if file_logo and file_logo.filename != '':
            url_gcs = self._upload_logo_to_gcs(empresa.slug, file_logo)
            if url_gcs: config['logo_url'] = url_gcs
        else:
            config['logo_url'] = config_visual.get('logo_url', config.get('logo_url', ''))
        
        config['cor_primaria'] = config_visual.get('cor_primaria', '#2563eb')
        config['cor_hover'] = config_visual.get('cor_hover', '#1d4ed8')
        
        empresa.config_json = config
        flag_modified(empresa, "config_json")
        db.session.commit()
        return empresa

    def excluir_empresa_completo(self, empresa_id):
        """Remove a empresa e todos os dados vinculados de forma cirúrgica (Cascata manual)."""
        empresa = self.empresa_repo.get_by_id(empresa_id)
        if not empresa:
            raise ValueError("Empresa não encontrada para exclusão.")
        
        try:
            # Sub-query com os IDs dos utilizadores desta empresa
            user_ids_subquery = db.session.query(User.id).filter_by(empresa_id=empresa_id).subquery()
            
            # 1. Limpa todas as dependências geradas pelos utilizadores da empresa
            SolicitacaoUniforme.query.filter(SolicitacaoUniforme.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            Holerite.query.filter(Holerite.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            Recibo.query.filter(Recibo.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            AssinaturaDigital.query.filter(AssinaturaDigital.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            Atestado.query.filter(Atestado.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            PushSubscription.query.filter(PushSubscription.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            PeriodoAquisitivo.query.filter(PeriodoAquisitivo.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            PontoRegistro.query.filter(PontoRegistro.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            PontoResumo.query.filter(PontoResumo.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            PontoAjuste.query.filter(PontoAjuste.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            SolicitacaoAusencia.query.filter(SolicitacaoAusencia.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            Notificacao.query.filter(Notificacao.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            
            # 2. Limpa tabelas vinculadas diretamente à empresa
            ItemEstoque.query.filter_by(empresa_id=empresa_id).delete(synchronize_session=False)
            PreCadastro.query.filter_by(empresa_id=empresa_id).delete(synchronize_session=False)
            Role.query.filter_by(empresa_id=empresa_id).delete(synchronize_session=False)
            
            # 3. Finalmente remove os Utilizadores e a Empresa
            User.query.filter_by(empresa_id=empresa_id).delete(synchronize_session=False)
            db.session.delete(empresa)
            
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Erro na exclusão manual: {e}")
            raise ValueError(f"Não foi possível excluir a empresa devido a restrições no banco de dados. Contate o suporte.")


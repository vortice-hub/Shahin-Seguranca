import os
from google.cloud import storage
import uuid
import io

def get_bucket_name():
    """Busca o nome do bucket nas variáveis de ambiente do Cloud Run."""
    # O fallback 'shahin-docs-us' está aqui apenas por precaução caso a variável falhe
    return os.environ.get('VORTICE_BUCKET', 'shahin-docs-us')

def salvar_no_storage(pdf_bytes, pasta_ref, empresa_slug):
    """Salva o PDF no bucket isolado por empresa e retorna o caminho relativo."""
    try:
        client = storage.Client()
        bucket = client.bucket(get_bucket_name())
        # O arquivo será salvo com a estrutura: slug_da_empresa/documentos/pasta_ref/uuid.pdf
        nome_blob = f"{empresa_slug}/documentos/{pasta_ref}/{uuid.uuid4()}.pdf"
        blob = bucket.blob(nome_blob)
        blob.upload_from_string(pdf_bytes, content_type='application/pdf')
        return nome_blob
    except Exception as e:
        print(f"Erro no Cloud Storage Upload: {e}")
        return None

def salvar_imagem_storage(img_bytes, pasta_ref, empresa_slug, nome_arquivo):
    """Salva imagens (como biometria facial) no bucket isolado por empresa."""
    try:
        client = storage.Client()
        bucket = client.bucket(get_bucket_name())
        # O arquivo será salvo com a estrutura: slug_da_empresa/pasta_ref/nome_arquivo
        nome_blob = f"{empresa_slug}/{pasta_ref}/{nome_arquivo}"
        blob = bucket.blob(nome_blob)
        blob.upload_from_string(img_bytes, content_type='image/jpeg')
        return nome_blob
    except Exception as e:
        print(f"Erro no Cloud Storage Upload (Imagem): {e}")
        return None

def baixar_bytes_storage(caminho_blob):
    """
    Baixa o arquivo do Storage para a memória do servidor.
    Isso evita problemas de Link Assinado/Chave Privada no Cloud Run.
    """
    try:
        client = storage.Client()
        bucket = client.bucket(get_bucket_name())
        blob = bucket.blob(caminho_blob)
        
        if not blob.exists():
            return None
            
        return blob.download_as_bytes()
    except Exception as e:
        print(f"Erro ao baixar do Storage: {e}")
        return None

# Função legada mantida para compatibilidade, mas não será usada preferencialmente
def gerar_url_assinada(caminho_blob):
    return None


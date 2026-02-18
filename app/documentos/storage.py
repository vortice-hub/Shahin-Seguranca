from google.cloud import storage
import uuid
import io

# NOVO BUCKET GRATUITO NOS EUA
BUCKET_NAME = "shahin-docs-us"

def salvar_no_storage(pdf_bytes, pasta_ref):
    """Salva o PDF no bucket e retorna o caminho relativo."""
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        # O arquivo será salvo com a estrutura: pasta_ref/uuid.pdf
        nome_blob = f"{pasta_ref}/{uuid.uuid4()}.pdf"
        blob = bucket.blob(nome_blob)
        blob.upload_from_string(pdf_bytes, content_type='application/pdf')
        return nome_blob
    except Exception as e:
        print(f"Erro no Cloud Storage Upload: {e}")
        return None

def baixar_bytes_storage(caminho_blob):
    """
    Baixa o arquivo do Storage para a memória do servidor.
    Isso evita problemas de Link Assinado/Chave Privada no Cloud Run.
    """
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
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


from google.cloud import storage
from datetime import datetime, timedelta
import uuid

# Nome do seu Bucket criado no console do GCP
BUCKET_NAME = "shahin-documentos"

def salvar_no_storage(pdf_bytes, mes_ref):
    """Envia o PDF para o bucket e retorna o NOME DO BLOB (caminho)."""
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        
        # Gera um caminho único: holerites/2026-02/uuid.pdf
        nome_blob = f"holerites/{mes_ref}/{uuid.uuid4()}.pdf"
        blob = bucket.blob(nome_blob)
        
        blob.upload_from_string(pdf_bytes, content_type='application/pdf')
        return nome_blob # Retorna o caminho para salvar no banco
    except Exception as e:
        print(f"Erro no Cloud Storage: {e}")
        return None

def gerar_url_assinada(caminho_blob):
    """Gera um link privado que expira em 15 minutos."""
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(caminho_blob)

        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=15), 
            method="GET",
        )
        return url
    except Exception as e:
        print(f"Erro ao gerar link assinado: {e}")
        return None
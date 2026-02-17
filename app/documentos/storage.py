from google.cloud import storage
from datetime import timedelta
import uuid
import google.auth

BUCKET_NAME = "shahin-documentos"

def salvar_no_storage(pdf_bytes, mes_ref):
    """Envia o PDF para o bucket e retorna o caminho."""
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        nome_blob = f"holerites/{mes_ref}/{uuid.uuid4()}.pdf"
        blob = bucket.blob(nome_blob)
        blob.upload_from_string(pdf_bytes, content_type='application/pdf')
        return nome_blob
    except Exception as e:
        print(f"Erro no Cloud Storage: {e}")
        return None

def gerar_url_assinada(caminho_blob):
    """Gera link privado compatível com o Google Cloud Run (IAM Signing)."""
    try:
        # Obtém as credenciais da conta de serviço do Cloud Run
        credentials, project_id = google.auth.default()
        client = storage.Client(credentials=credentials)
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(caminho_blob)

        # Assina a URL usando o IAM Service Account Token Creator
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=15),
            method="GET",
            service_account_email=credentials.service_account_email
        )
        return url
    except Exception as e:
        print(f"Erro ao gerar link assinado: {e}")
        return None


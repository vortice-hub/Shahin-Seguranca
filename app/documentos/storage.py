from google.cloud import storage
from datetime import timedelta
import uuid
import google.auth

BUCKET_NAME = "shahin-documentos"

def salvar_no_storage(pdf_bytes, mes_ref):
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
    """Gera link assinado compatível com o ambiente Cloud Run."""
    try:
        credentials, project_id = google.auth.default()
        client = storage.Client(credentials=credentials)
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(caminho_blob)

        # Tenta gerar o link usando a identidade do Service Account
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


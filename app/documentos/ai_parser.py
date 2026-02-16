import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
import logging

logger = logging.getLogger(__name__)

PROJECT_ID = "nimble-gearing-487415-u6"
LOCATION = "us-central1"

def inicializar_vertex():
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
    except Exception as e:
        logger.error(f"Falha ao iniciar Vertex AI: {e}")

def analisar_pagina_pdf_ia(pdf_bytes):
    """
    Envia os bytes de UMA página PDF para a IA analisar visualmente.
    """
    inicializar_vertex()
    model = GenerativeModel("gemini-1.5-flash-001")
    
    # Criamos o componente de dados para a IA (PDF nativo)
    pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
    
    prompt = """
    Analise esta página de documento de RH e extraia os dados para identificação.
    
    Regras:
    1. 'eh_holerite': Marque como true se for um Recibo de Pagamento, Holerite ou Folha Mensal.
    2. 'nome': Extraia o nome completo do funcionário.
    3. 'cpf': Extraia apenas os números do CPF.
    4. 'mes_referencia': Formate como AAAA-MM (Ex: Janeiro de 2026 vira 2026-01).
    
    Retorne APENAS o JSON puro, sem markdown:
    {
        "eh_holerite": true,
        "nome": "NOME COMPLETO",
        "cpf": "00000000000",
        "mes_referencia": "2026-02"
    }
    """
    
    try:
        response = model.generate_content([pdf_part, prompt])
        # Limpeza de possíveis marcações de código da IA
        res_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(res_text)
    except Exception as e:
        logger.error(f"Erro na análise visual da IA: {e}")
        return {"eh_holerite": False, "erro": str(e)}
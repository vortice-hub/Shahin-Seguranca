import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json

def extrair_dados_holerite(pdf_bytes):
    """Usa IA para identificar Nome e Mês de Referência no PDF."""
    # Inicializa com seu ID de projeto
    vertexai.init(project="nimble-gearing-487415-u6", location="us-central1")
    model = GenerativeModel("gemini-1.5-flash-001")
    
    # Prepara o arquivo para análise multimodal
    pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
    
    prompt = """
    Aja como um especialista em RH. Analise este holerite e extraia:
    1. O NOME COMPLETO do funcionário.
    2. O MÊS DE REFERÊNCIA no formato AAAA-MM (Ex: 2026-02).
    
    Retorne estritamente um JSON puro:
    {
        "nome": "NOME ENCONTRADO",
        "mes_referencia": "AAAA-MM"
    }
    """
    try:
        response = model.generate_content([pdf_part, prompt])
        res_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(res_text)
    except Exception as e:
        print(f"Falha na IA: {e}")
        return None
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json

def extrair_dados_holerite(pdf_bytes):
    """Usa IA para identificar Nome e Mês. Adicionado logs de depuração."""
    vertexai.init(project="nimble-gearing-487415-u6", location="us-central1")
    model = GenerativeModel("gemini-1.5-flash-001")
    
    pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
    
    prompt = """
    Analise este holerite e extraia o NOME COMPLETO e o MÊS DE REFERÊNCIA (AAAA-MM).
    Retorne APENAS um JSON: {"nome": "NOME", "mes_referencia": "2026-02"}
    """
    try:
        response = model.generate_content([pdf_part, prompt])
        res_text = response.text.replace('```json', '').replace('```', '').strip()
        dados = json.loads(res_text)
        # LOG DE DEPURAÇÃO: Importante para ver no console do GCP
        print(f"IA EXTRAÇÃO SUCESSO: {dados}")
        return dados
    except Exception as e:
        print(f"IA ERRO CRÍTICO: {e}")
        return None


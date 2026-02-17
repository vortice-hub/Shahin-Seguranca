import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json

def extrair_dados_holerite(pdf_bytes):
    """
    Usa IA para identificar Nome e Mês. 
    Atualizado para usar modelo estável 'gemini-1.5-flash'.
    """
    # Inicializa Vertex AI na região correta
    vertexai.init(project="nimble-gearing-487415-u6", location="us-central1")
    
    # Tenta usar o modelo Flash (mais rápido), com fallback se não encontrar
    try:
        model = GenerativeModel("gemini-1.5-flash")
    except:
        model = GenerativeModel("gemini-1.0-pro")
    
    pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
    
    prompt = """
    Analise este holerite.
    Extraia o NOME COMPLETO do funcionário.
    Extraia o MÊS DE REFERÊNCIA (formato AAAA-MM).
    Retorne APENAS um JSON válido neste formato: {"nome": "NOME", "mes_referencia": "AAAA-MM"}
    """
    try:
        # Gera conteúdo
        response = model.generate_content([pdf_part, prompt])
        
        # Limpeza robusta da resposta (Markdown removal)
        res_text = response.text.replace('```json', '').replace('```', '').strip()
        
        dados = json.loads(res_text)
        print(f"IA SUCESSO: {dados}") # Log para debug
        return dados
    except Exception as e:
        print(f"IA FALHA CRÍTICA: {e}")
        return None


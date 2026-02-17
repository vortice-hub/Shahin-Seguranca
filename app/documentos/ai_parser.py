import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json

def extrair_dados_holerite(pdf_bytes):
    """
    Usa IA para identificar Nome e Mês.
    Estratégia: Modelo estável 'gemini-1.0-pro' para garantir disponibilidade.
    """
    # Inicializa Vertex AI
    vertexai.init(project="nimble-gearing-487415-u6", location="us-central1")
    
    # MUDANÇA CRÍTICA: 'gemini-1.0-pro' é o modelo estável global (GA).
    # O modelo 'flash' pode estar em preview ou indisponível nesta região.
    try:
        model = GenerativeModel("gemini-1.0-pro")
    except:
        # Fallback de emergência
        model = GenerativeModel("gemini-pro")
    
    pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
    
    prompt = """
    Aja como um especialista em RH.
    Analise este documento (Holerite) e extraia:
    1. O NOME DO FUNCIONÁRIO (Ignore o nome da empresa/empregador).
    2. O MÊS DE REFERÊNCIA (Data do pagamento ou competência).
    
    Retorne estritamente um JSON neste formato:
    {"nome": "NOME ENCONTRADO", "mes_referencia": "AAAA-MM"}
    """
    try:
        # Configuração de geração conservadora para evitar alucinações
        response = model.generate_content(
            [pdf_part, prompt],
            generation_config={"temperature": 0.2, "max_output_tokens": 1024}
        )
        
        res_text = response.text.replace('```json', '').replace('```', '').strip()
        dados = json.loads(res_text)
        print(f"IA LEITURA SUCESSO: {dados}")
        return dados
    except Exception as e:
        print(f"IA ERRO DE MODELO: {e}")
        return None


import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json

def extrair_dados_holerite(pdf_bytes):
    """
    Usa IA para identificar Nome e Mês.
    Estratégia: Prompt focado em ignorar cabeçalhos de empresa.
    """
    vertexai.init(project="nimble-gearing-487415-u6", location="us-central1")
    
    # Tenta carregar o modelo Flash, com fallback para Pro
    try:
        model = GenerativeModel("gemini-1.5-flash")
    except:
        model = GenerativeModel("gemini-1.0-pro")
    
    pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
    
    prompt = """
    Você é um especialista em RH analisando um holerite brasileiro.
    Tarefa: Extraia o NOME DO FUNCIONÁRIO e o MÊS DE REFERÊNCIA.
    
    Regras Críticas:
    1. IGNORE o nome da empresa (ex: Shahin, La Shahin, Empregador).
    2. Procure por rótulos como "Nome do Funcionário", "Colaborador" ou logo abaixo do nome da empresa.
    3. Retorne a data no formato AAAA-MM.
    
    Retorne APENAS um JSON: {"nome": "NOME ENCONTRADO", "mes_referencia": "AAAA-MM"}
    """
    try:
        response = model.generate_content([pdf_part, prompt])
        res_text = response.text.replace('```json', '').replace('```', '').strip()
        dados = json.loads(res_text)
        print(f"IA LEITURA: {dados}") # Log para vermos o que ele leu
        return dados
    except Exception as e:
        print(f"IA ERRO: {e}")
        return None


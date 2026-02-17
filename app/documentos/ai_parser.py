import vertexai
from vertexai.generative_models import GenerativeModel, Part
from vertexai.language_models import TextGenerationModel
import json

def extrair_dados_holerite(pdf_bytes):
    """
    Usa IA para identificar Nome e Mês.
    Estratégia: Tentativa em CASCATA de múltiplos modelos para contornar erros 404/403.
    """
    # Inicializa Vertex AI na região correta
    vertexai.init(project="nimble-gearing-487415-u6", location="us-central1")
    
    modelos_gemini = ["gemini-1.5-flash", "gemini-1.0-pro", "gemini-pro"]
    
    prompt_texto = """
    Aja como um especialista em RH.
    Analise o texto deste holerite e extraia:
    1. O NOME DO FUNCIONÁRIO (Ignore o nome da empresa).
    2. O MÊS DE REFERÊNCIA (AAAA-MM).
    
    Retorne estritamente um JSON neste formato, sem markdown:
    {"nome": "NOME ENCONTRADO", "mes_referencia": "AAAA-MM"}
    """

    # TENTATIVA 1, 2 e 3: Família Gemini (Multimodal)
    for modelo_nome in modelos_gemini:
        try:
            print(f"IA: Tentando modelo {modelo_nome}...")
            model = GenerativeModel(modelo_nome)
            pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
            
            response = model.generate_content(
                [pdf_part, prompt_texto],
                generation_config={"temperature": 0.0, "max_output_tokens": 1024}
            )
            
            res_text = response.text.replace('```json', '').replace('```', '').strip()
            dados = json.loads(res_text)
            print(f"IA SUCESSO ({modelo_nome}): {dados}")
            return dados
        except Exception as e:
            print(f"IA FALHA ({modelo_nome}): {e}")
            continue # Tenta o próximo

    # TENTATIVA 4: Fallback para PaLM 2 (Text-Bison) - Requer extração de texto prévia
    # Nota: O PaLM 2 não lê PDF nativamente como o Gemini, então se chegarmos aqui,
    # retornamos None para evitar erros de processamento de imagem, mas logamos o aviso.
    print("IA CRÍTICO: Todos os modelos Gemini falharam. Verifique a API Vertex AI no Console.")
    return None


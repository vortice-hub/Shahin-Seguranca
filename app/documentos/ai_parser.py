import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
import logging

# Configuração de Log
logger = logging.getLogger(__name__)

# Configuração do Modelo (Idealmente usar variáveis de ambiente para o Project ID)
# O Cloud Run injeta a autenticação automaticamente
PROJECT_ID = "nimble-gearing-487415-u6"  # Seu ID do projeto GCP
LOCATION = "us-central1" # A IA roda melhor/mais barato nesta região

def inicializar_vertex():
    """Inicializa a conexão com a Vertex AI."""
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
    except Exception as e:
        logger.error(f"Falha ao iniciar Vertex AI: {e}")

def analisar_texto_holerite(texto_pagina):
    """
    Envia o texto cru de uma página para o Gemini Flash e retorna um JSON estruturado.
    """
    inicializar_vertex()
    
    model = GenerativeModel("gemini-1.5-flash-001")
    
    # O Prompt é a "instrução" para o cérebro da IA
    prompt = f"""
    Você é um assistente de RH especializado em ler holerites e folhas de pagamento.
    Analise o texto abaixo extraído de uma página de documento.
    
    Tarefas:
    1. Identifique se é um Holerite/Folha de Pagamento.
    2. Extraia o Nome do Funcionário.
    3. Extraia o CPF (se houver).
    4. Extraia o Mês/Ano de referência.
    5. Identifique se esta página é continuação de uma anterior (ex: "Página 2/2").
    
    Texto do documento:
    ---
    {texto_pagina}
    ---
    
    Retorne APENAS um JSON no seguinte formato, sem markdown (```json):
    {{
        "eh_holerite": true/false,
        "nome": "Nome Encontrado ou null",
        "cpf": "000.000.000-00 ou null",
        "mes_referencia": "AAAA-MM ou null",
        "valor_liquido": 0.00,
        "eh_continuacao": true/false
    }}
    """
    
    try:
        # Configuração para garantir que a resposta seja determinística (sem criatividade)
        generation_config = {
            "max_output_tokens": 256,
            "temperature": 0.0,
            "top_p": 0.95,
        }
        
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )
        
        # Limpeza básica caso a IA mande blocos de código
        texto_limpo = response.text.replace('```json', '').replace('```', '').strip()
        
        dados = json.loads(texto_limpo)
        return dados
        
    except Exception as e:
        logger.error(f"Erro na análise de IA: {e}")
        # Retorna um objeto vazio/seguro em caso de erro
        return {
            "eh_holerite": False,
            "nome": None,
            "cpf": None,
            "mes_referencia": None,
            "erro": str(e)
        }
import io
import re
import json
from pypdf import PdfReader
from thefuzz import process, fuzz
import vertexai
from vertexai.language_models import TextGenerationModel

def extrair_dados_holerite(pdf_bytes, lista_nomes_banco=None):
    """
    Abordagem Híbrida:
    1. Tenta extrair texto e achar o nome localmente (Sem custo/Sem erro de API).
    2. Se falhar, usa IA legado (PaLM 2) que é mais estável na região.
    """
    
    # --- ETAPA 1: EXTRAÇÃO LOCAL (A BALA DE PRATA) ---
    texto_pdf = ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if len(reader.pages) > 0:
            texto_pdf = reader.pages[0].extract_text()
    except Exception as e:
        print(f"ERRO LEITURA LOCAL: {e}")

    # Busca Data por Regex (Procura padrões como 02/2026 ou 2026/02)
    mes_ref = "2026-02" # Fallback
    match_data = re.search(r'(\d{2}/\d{4})', texto_pdf)
    if match_data:
        m, y = match_data.group(1).split('/')
        mes_ref = f"{y}-{m}"

    # Busca Nome Localmente (Se tivermos a lista do banco)
    if lista_nomes_banco and texto_pdf:
        # Limpa o texto do PDF para facilitar
        texto_upper = texto_pdf.upper()
        
        # Scorer 'partial_ratio' verifica se o nome do funcionário aparece DENTRO do texto do PDF
        match = process.extractOne(texto_upper, lista_nomes_banco, scorer=fuzz.partial_ratio)
        
        # Se a certeza for alta (>90), confiamos e retornamos na hora
        if match and match[1] >= 90:
            print(f"MATCH LOCAL SUCESSO: '{match[0]}' encontrado no texto (Score: {match[1]})")
            return {"nome": match[0], "mes_referencia": mes_ref, "origem": "local"}

    # --- ETAPA 2: FALLBACK PARA IA (PaLM 2) ---
    # Só executamos se o método local falhar.
    try:
        vertexai.init(project="nimble-gearing-487415-u6", location="us-central1")
        # Usamos text-bison@001 que costuma estar disponível onde o Gemini falha
        model = TextGenerationModel.from_pretrained("text-bison@001")
        
        prompt = f"""
        Extraia do texto abaixo o NOME COMPLETO do funcionário e a DATA (AAAA-MM).
        Texto: {texto_pdf[:3000]}
        
        Responda apenas JSON: {{"nome": "NOME", "mes_referencia": "AAAA-MM"}}
        """
        
        response = model.predict(prompt, temperature=0.1)
        txt = response.text.replace('```json', '').replace('```', '').strip()
        
        # Tenta extrair o JSON da resposta
        if '{' in txt and '}' in txt:
            json_str = txt[txt.find('{'):txt.rfind('}')+1]
            dados = json.loads(json_str)
            dados["origem"] = "ia"
            print(f"IA SUCESSO: {dados}")
            return dados
            
    except Exception as e:
        print(f"IA FALHA CRÍTICA: {e}")

    # Se tudo falhar, retorna vazio para cair na revisão
    return {"nome": "", "mes_referencia": mes_ref, "origem": "falha"}


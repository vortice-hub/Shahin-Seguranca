import io
import re
import json
import unicodedata
from pypdf import PdfReader
from thefuzz import process, fuzz

def normalizar_texto_pdf(texto):
    """Limpa o texto do PDF para facilitar a busca."""
    if not texto: return ""
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto.upper().replace('\n', ' ').strip()

def extrair_dados_holerite(pdf_bytes, lista_nomes_banco=None):
    """
    Abordagem 100% Local com RIGOR MÁXIMO (95%).
    """
    dados_retorno = {"nome": "", "mes_referencia": "2026-02", "origem": "falha"}
    
    texto_raw = ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if len(reader.pages) > 0:
            texto_raw = reader.pages[0].extract_text()
    except Exception as e:
        print(f"ERRO DE LEITURA PDF: {e}")
        return dados_retorno

    if not texto_raw:
        return dados_retorno

    texto_limpo = normalizar_texto_pdf(texto_raw)

    # Busca de Data (Regex)
    padrao_data = r'(\d{2})[/-](\d{4})'
    match_data = re.search(padrao_data, texto_raw)
    if match_data:
        mes = match_data.group(1)
        ano = match_data.group(2)
        if 1 <= int(mes) <= 12:
            dados_retorno["mes_referencia"] = f"{ano}-{mes}"

    # Busca de Nome (Rigorosa)
    if lista_nomes_banco:
        # partial_token_set_ratio é bom, mas vamos exigir score alto
        melhor_match = process.extractOne(texto_limpo, lista_nomes_banco, scorer=fuzz.partial_token_set_ratio)
        
        if melhor_match:
            nome_encontrado = melhor_match[0]
            score = melhor_match[1]
            
            # MUDANÇA CRÍTICA: Subiu de 85 para 95 para evitar falso positivo
            if score >= 95:
                print(f"MATCH LOCAL SEGURO: '{nome_encontrado}' (Score: {score})")
                dados_retorno["nome"] = nome_encontrado
                dados_retorno["origem"] = "python_local"
            else:
                print(f"MATCH RECUSADO (BAIXO SCORE): '{nome_encontrado}' (Score: {score}) - Vai para revisão.")

    return dados_retorno


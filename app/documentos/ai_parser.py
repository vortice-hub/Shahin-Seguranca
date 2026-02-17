import io
import re
import json
import unicodedata
from pypdf import PdfReader
from thefuzz import process, fuzz

def normalizar_texto_pdf(texto):
    """Limpa o texto do PDF para facilitar a busca."""
    if not texto: return ""
    # Remove acentos
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    # Tudo maiúsculo e remove quebras de linha excessivas
    return texto.upper().replace('\n', ' ').strip()

def extrair_dados_holerite(pdf_bytes, lista_nomes_banco=None):
    """
    Abordagem 100% Local (Python Puro).
    Não usa IA. Usa Regex e Fuzzy Matching.
    """
    dados_retorno = {"nome": "", "mes_referencia": "2026-02", "origem": "falha"}
    
    # 1. Extração do Texto Bruto
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

    # 2. Busca de Data (Regex)
    # Procura padrões: 02/2026, 02-2026, FEV/2026
    padrao_data = r'(\d{2})[/-](\d{4})'
    match_data = re.search(padrao_data, texto_raw)
    
    if match_data:
        mes = match_data.group(1)
        ano = match_data.group(2)
        # Validação básica de mês
        if 1 <= int(mes) <= 12:
            dados_retorno["mes_referencia"] = f"{ano}-{mes}"

    # 3. Busca de Nome (Varredura na Lista)
    if lista_nomes_banco:
        # A estratégia aqui é: Verificar qual nome da nossa lista de funcionários
        # aparece com maior "força" dentro do texto do PDF.
        
        # 'partial_ratio': Verifica se o nome do funcionário é uma substring do texto do PDF
        # Ex: PDF "Nome: JOAO DA SILVA - Mot..." contém "JOAO SILVA" (se normalizado)
        melhor_match = process.extractOne(texto_limpo, lista_nomes_banco, scorer=fuzz.partial_token_set_ratio)
        
        if melhor_match:
            nome_encontrado = melhor_match[0]
            score = melhor_match[1]
            
            # Se a certeza for alta (>85%), assumimos que é esse o dono
            if score >= 85:
                print(f"MATCH LOCAL: '{nome_encontrado}' (Score: {score})")
                dados_retorno["nome"] = nome_encontrado
                dados_retorno["origem"] = "python_local"
            else:
                print(f"MATCH BAIXO: '{nome_encontrado}' (Score: {score}) - Enviando para revisão.")

    return dados_retorno


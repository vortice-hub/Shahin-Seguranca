import io
import re
import unicodedata
from pypdf import PdfReader

def limpar_texto_pdf_para_busca(texto):
    """
    Aplica a mesma limpeza usada no banco de dados para garantir
    que o texto do PDF e o nome do funcionário falem a exata mesma língua.
    """
    if not texto: return ""
    # Remove acentos
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = texto.upper().replace('\n', ' ').strip()
    
    # Remove preposições (para focar apenas nos nomes fortes)
    stopwords = [" DE ", " DA ", " DO ", " DOS ", " DAS ", " E "]
    for word in stopwords:
        texto = texto.replace(word, " ")
    
    # Remove múltiplos espaços
    return " ".join(texto.split())

def extrair_dados_holerite(pdf_bytes, lista_nomes_banco=None):
    """
    Abordagem de MATCH EXATO E COMPLETO.
    Sem margem para "adivinhação" ou envios errados.
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

    # 1. Busca de Data
    padrao_data = r'(\d{2})[/-](\d{4})'
    match_data = re.search(padrao_data, texto_raw)
    if match_data:
        mes = match_data.group(1)
        ano = match_data.group(2)
        if 1 <= int(mes) <= 12:
            dados_retorno["mes_referencia"] = f"{ano}-{mes}"

    # 2. Busca de Nome (RIGOROSA E EXATA)
    if lista_nomes_banco:
        # Limpa o texto inteiro da página do PDF
        texto_pdf_limpo = limpar_texto_pdf_para_busca(texto_raw)
        
        # ORDENA OS NOMES POR TAMANHO (Do maior para o menor)
        # Motivo: Se tivermos "João Marcos Silva" e "João Marcos", 
        # o sistema testa o nome mais longo primeiro. Isso impede 
        # que nomes curtos roubem o holerite de nomes compostos.
        nomes_ordenados = sorted(lista_nomes_banco, key=len, reverse=True)
        
        for nome_banco in nomes_ordenados:
            # Adiciona espaços ao redor (f" {nome} ") para garantir a busca da palavra exata.
            # Impede que o sistema ache "ANA" no meio da palavra "JULIANA".
            if f" {nome_banco} " in f" {texto_pdf_limpo} ":
                print(f"MATCH EXATO COMPLETO: '{nome_banco}' encontrado no PDF.")
                dados_retorno["nome"] = nome_banco
                dados_retorno["origem"] = "python_exato"
                break  # Para a busca no primeiro match perfeito

    return dados_retorno


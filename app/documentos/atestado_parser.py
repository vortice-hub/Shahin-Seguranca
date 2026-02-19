from google.cloud import vision
import re
import unicodedata

def limpar_texto(texto):
    """Remove acentos e padroniza o texto para facilitar a busca do nome e regex."""
    if not texto: return ""
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    # Substitui quebras de linha por espaço e remove espaços duplos
    texto = texto.upper().replace('\n', ' ')
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def converter_numero_extenso(texto):
    """Mapeia palavras comuns de atestados para números inteiros."""
    mapa = {
        "UM": 1, "DOIS": 2, "TRES": 3, "QUATRO": 4, "CINCO": 5,
        "SEIS": 6, "SETE": 7, "OITO": 8, "NOVE": 9, "DEZ": 10,
        "ONZE": 11, "DOZE": 12, "TREZE": 13, "QUATORZE": 14, "CATORZE": 14, "QUINZE": 15
    }
    return mapa.get(texto.upper(), None)

def analisar_atestado_vision(imagem_bytes, nome_funcionario):
    """Usa o Google Cloud Vision para ler o atestado e extrair os dados de forma flexível."""
    dados = {
        "nome_encontrado": False,
        "data_inicio": None,
        "dias_afastamento": None,
        "texto_bruto": ""
    }
    
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=imagem_bytes)
        response = client.text_detection(image=image)
        
        if response.error.message:
            return dados

        textos = response.text_annotations
        if not textos:
            return dados
        
        texto_completo = textos[0].description
        dados["texto_bruto"] = texto_completo
        
        texto_limpo = limpar_texto(texto_completo)
        nome_limpo = limpar_texto(nome_funcionario)

        # --- DEBUG: IMPRIME NO CONSOLE O QUE A IA ESTÁ LENDO ---
        print("=== INICIO DA LEITURA DO ATESTADO ===")
        print(f"Texto Limpo: {texto_limpo}")
        print("=====================================")

        # 1. Verifica se o nome do funcionário está no atestado (lógica flexível)
        partes_nome = nome_limpo.split()
        if len(partes_nome) >= 2:
            if partes_nome[0] in texto_limpo and partes_nome[-1] in texto_limpo:
                dados["nome_encontrado"] = True
        elif nome_limpo in texto_limpo:
             dados["nome_encontrado"] = True

        # 2. Busca a quantidade de dias usando RegEx Avançado e Semântica
        
        # Estratégia 1: Procura Número Literal perto da palavra DIA/DIAS. 
        # O [A-Z\s] garante que ele ignora palavras entre parênteses como "2 (DOIS) DIAS"
        match_num = re.search(r'(\d{1,2})\s*(?:\([A-Z\s]+\))?\s*(?:DIAS|DIA)', texto_limpo)
        
        if match_num:
            dados["dias_afastamento"] = int(match_num.group(1))
        else:
            # Estratégia 2: Palavras-chave de afastamento seguidas de número (ex: AFASTAMENTO POR 5 DIAS, REPOUSO DE 02)
            match_contexto = re.search(r'(?:AFASTAMENTO|REPOUSO|ATESTO|CONCEDO|NECESSITA DE)\D*?(\d{1,2})\s*(?:\([A-Z\s]+\))?\s*(?:DIAS|DIA)?', texto_limpo)
            if match_contexto:
                dados["dias_afastamento"] = int(match_contexto.group(1))
            else:
                # Estratégia 3: Procura Número por Extenso perto da palavra DIA/DIAS
                palavras_numero = r'(UM|DOIS|TRES|QUATRO|CINCO|SEIS|SETE|OITO|NOVE|DEZ|ONZE|DOZE|TREZE|QUATORZE|CATORZE|QUINZE)'
                match_extenso = re.search(f'{palavras_numero}\\s*(?:DIAS|DIA)', texto_limpo)
                if match_extenso:
                    dados["dias_afastamento"] = converter_numero_extenso(match_extenso.group(1))
                else:
                    # Estratégia 4 (Desesperada): Procura a palavra "DIA" e pega o primeiro número que aparecer até 20 caracteres antes dela.
                    match_desespero = re.search(r'(\d{1,2}).{1,20}(?:DIAS|DIA)', texto_limpo)
                    if match_desespero:
                         dados["dias_afastamento"] = int(match_desespero.group(1))

        # 3. Busca a data de emissão (assumindo como data de início)
        match_data = re.search(r'(\d{2})[/\-](\d{2})[/\-](\d{4})', texto_limpo)
        if match_data:
            dia, mes, ano = match_data.group(1), match_data.group(2), match_data.group(3)
            dados["data_inicio"] = f"{ano}-{mes}-{dia}"

        return dados

    except Exception as e:
        print(f"Falha ao processar OCR do atestado: {e}")
        return dados


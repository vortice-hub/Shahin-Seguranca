from google.cloud import vision
import re
import unicodedata
import traceback

def limpar_texto(texto):
    if not texto: return ""
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = texto.upper().replace('\n', ' ')
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def converter_numero_extenso(texto):
    mapa = {
        "UM": 1, "DOIS": 2, "TRES": 3, "QUATRO": 4, "CINCO": 5,
        "SEIS": 6, "SETE": 7, "OITO": 8, "NOVE": 9, "DEZ": 10,
        "ONZE": 11, "DOZE": 12, "TREZE": 13, "QUATORZE": 14, "CATORZE": 14, "QUINZE": 15
    }
    return mapa.get(texto.upper(), None)

def analisar_atestado_vision(imagem_bytes, nome_funcionario):
    # Iniciamos com uma mensagem de erro padrão caso nada seja lido
    dados = {
        "nome_encontrado": False,
        "data_inicio": None,
        "dias_afastamento": None,
        "texto_bruto": "NENHUM TEXTO FOI DETECTADO PELO ROBÔ. VERIFIQUE A QUALIDADE DA FOTO."
    }
    
    try:
        if not imagem_bytes or len(imagem_bytes) == 0:
            dados["texto_bruto"] = "ERRO: O arquivo chegou vazio ao processador de IA."
            return dados

        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=imagem_bytes)
        
        # Usamos TEXT_DETECTION para fotos e DOCUMENT_TEXT_DETECTION para PDFs/scans
        response = client.text_detection(image=image)
        
        if response.error.message:
            dados["texto_bruto"] = f"ERRO NA API GOOGLE: {response.error.message}"
            return dados

        textos = response.text_annotations
        if not textos:
            dados["texto_bruto"] = "O GOOGLE VISION NÃO ENCONTROU NENHUMA LETRA NESTA IMAGEM."
            return dados
        
        # Pega o bloco completo de texto
        texto_completo = textos[0].description
        dados["texto_bruto"] = texto_completo # Aqui o texto deve aparecer na caixa verde
        
        texto_limpo = limpar_texto(texto_completo)
        nome_limpo = limpar_texto(nome_funcionario)

        # 1. Busca Nome
        partes_nome = nome_limpo.split()
        if len(partes_nome) >= 2:
            if partes_nome[0] in texto_limpo and partes_nome[-1] in texto_limpo:
                dados["nome_encontrado"] = True

        # 2. Busca Dias (Regras Sniper)
        match_num = re.search(r'(\d{1,2})\s*(?:\([A-Z\s]+\))?\s*(?:DIAS|DIA)', texto_limpo)
        if match_num:
            dados["dias_afastamento"] = int(match_num.group(1))
        else:
            match_contexto = re.search(r'(?:AFASTAMENTO|REPOUSO|CONCEDO|NECESSITA DE)\D*?(\d{1,2})', texto_limpo)
            if match_contexto:
                dados["dias_afastamento"] = int(match_contexto.group(1))
            else:
                palavras_numero = r'(UM|DOIS|TRES|QUATRO|CINCO|SEIS|SETE|OITO|NOVE|DEZ|ONZE|DOZE|TREZE|QUATORZE|CATORZE|QUINZE)'
                match_extenso = re.search(f'{palavras_numero}\\s*(?:DIAS|DIA)', texto_limpo)
                if match_extenso:
                    dados["dias_afastamento"] = converter_numero_extenso(match_extenso.group(1))

        # 3. Busca Data
        match_data = re.search(r'(\d{2})[/\-](\d{2})[/\-](\d{4})', texto_limpo)
        if match_data:
            dia, mes, ano = match_data.group(1), match_data.group(2), match_data.group(3)
            dados["data_inicio"] = f"{ano}-{mes}-{dia}"

        return dados

    except Exception as e:
        # Se der erro no código, ele vai escrever o erro na tela para nós
        dados["texto_bruto"] = f"ERRO CRÍTICO NO CÓDIGO: {str(e)}\n{traceback.format_exc()}"
        return dados


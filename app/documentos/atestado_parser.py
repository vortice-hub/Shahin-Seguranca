from google.cloud import vision
import re
import unicodedata
import traceback

def limpar_texto(texto):
    """Padroniza o texto para análise de dados."""
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
    dados = {
        "nome_encontrado": False,
        "data_inicio": None,
        "dias_afastamento": None,
        "texto_bruto": "NENHUM TEXTO DETECTADO."
    }
    
    try:
        client = vision.ImageAnnotatorClient()
        
        # Identifica se é PDF (assinatura de arquivo %PDF)
        is_pdf = imagem_bytes.startswith(b'%PDF')
        
        if is_pdf:
            # Lógica para Processar PDF
            input_config = vision.InputConfig(content=imagem_bytes, mime_type='application/pdf')
            feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
            # Solicitamos a análise da primeira página do PDF
            request = vision.AnnotateFileRequest(input_config=input_config, features=[feature], pages=[1])
            
            response = client.batch_annotate_files(requests=[request])
            # O PDF retorna uma estrutura de resposta diferente da imagem
            if response.responses[0].responses:
                texto_completo = response.responses[0].responses[0].full_text_annotation.text
            else:
                dados["texto_bruto"] = "PDF LIDO, MAS NENHUM TEXTO ENCONTRADO DENTRO DELE."
                return dados
        else:
            # Lógica para Processar Imagem (JPG, PNG)
            image = vision.Image(content=imagem_bytes)
            response = client.text_detection(image=image)
            
            if response.error.message:
                dados["texto_bruto"] = f"ERRO NA API GOOGLE: {response.error.message}"
                return dados
                
            if not response.text_annotations:
                dados["texto_bruto"] = "NENHUM TEXTO ENCONTRADO NA IMAGEM."
                return dados
            
            texto_completo = response.text_annotations[0].description

        # Processamento Comum (Independente do formato)
        dados["texto_bruto"] = texto_completo
        texto_limpo = limpar_texto(texto_completo)
        nome_limpo = limpar_texto(nome_funcionario)

        # 1. Validação de Nome
        partes_nome = nome_limpo.split()
        if len(partes_nome) >= 2:
            if partes_nome[0] in texto_limpo and partes_nome[-1] in texto_limpo:
                dados["nome_encontrado"] = True

        # 2. Extração de Dias (Regras de Negócio)
        # Tenta: "X dias", "X (extenso) dias", "AFASTAMENTO DE X", "REPOUSO DE X"
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

        # 3. Extração de Data
        match_data = re.search(r'(\d{2})[/\-](\d{2})[/\-](\d{4})', texto_limpo)
        if match_data:
            dia, mes, ano = match_data.group(1), match_data.group(2), match_data.group(3)
            dados["data_inicio"] = f"{ano}-{mes}-{dia}"

        return dados

    except Exception as e:
        dados["texto_bruto"] = f"ERRO NO PROCESSAMENTO: {str(e)}\n{traceback.format_exc()}"
        return dados


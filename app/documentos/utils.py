from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
import io
from app.utils import data_por_extenso

def gerar_pdf_recibo(recibo, user):
    """
    Gera um PDF binário baseado no modelo 'ALCIMONE NASCIMENTO.docx'.
    """
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Configurações de Fonte
    p.setFont("Helvetica-Bold", 14)
    
    # 1. Título
    p.drawString(2.5*cm, height - 3*cm, "RECIBO DE PAGAMENTO DE BENEFÍCIOS")
    
    p.setFont("Helvetica", 11)
    p.drawString(2.5*cm, height - 4*cm, "Recibo;")
    
    # Data no Topo
    data_fmt = recibo.data_pagamento.strftime('%d/%m/%Y')
    p.drawString(2.5*cm, height - 4.6*cm, f"Data:  {data_fmt}")
    
    # 2. Texto Legal
    p.setFont("Helvetica", 11)
    
    # Dados da Empresa (Puxados do Usuário ou Padrão)
    empresa = user.razao_social_empregadora or "LA SHAHIN SERVIÇOS DE SEGURANÇA LTDA"
    cnpj = user.cnpj_empregador or "50.537.235/0001-95"
    
    # Formatação de Moeda
    valor_fmt = f"{recibo.valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    texto_corpo = p.beginText(2.5*cm, height - 6*cm)
    texto_corpo.setFont("Helvetica", 11)
    texto_corpo.setLeading(18) # Espaçamento entre linhas
    
    texto_corpo.textLines(f"Recebi de {empresa},")
    texto_corpo.textLines(f"inscrita no CNPJ nº {cnpj} a quantia de R$ {valor_fmt}")
    texto_corpo.textLines("referente ao pagamento do(s) benefício(s) abaixo assinalado(s):")
    p.drawText(texto_corpo)
    
    # 3. Checkboxes de Benefícios
    y_checkbox = height - 9*cm
    
    def draw_check(x, y, label, checked):
        mark = "(X)" if checked else "(  )"
        p.setFont("Helvetica-Bold", 11)
        p.drawString(x, y, mark)
        p.setFont("Helvetica", 11)
        p.drawString(x + 1*cm, y, label)

    draw_check(2.5*cm, y_checkbox, "Vale Alimentação (VA)", recibo.tipo_vale_alimentacao)
    draw_check(10.5*cm, y_checkbox, "Vale Transporte (VT)", recibo.tipo_vale_transporte)
    
    draw_check(2.5*cm, y_checkbox - 1*cm, "Assiduidade", recibo.tipo_assiduidade)
    draw_check(10.5*cm, y_checkbox - 1*cm, "Cesta Básica", recibo.tipo_cesta_basica)

    # 4. Dados do Funcionário
    y_dados = height - 12*cm
    p.setFont("Helvetica-Bold", 12)
    p.drawString(2.5*cm, y_dados, "Dados do Funcionário")
    
    y_dados -= 1*cm
    p.setFont("Helvetica", 11)
    p.drawString(2.5*cm, y_dados, f"Nome: {user.real_name}")
    
    # Formata CPF ###.###.###-##
    cpf_fmt = user.cpf if user.cpf else "00000000000"
    if len(cpf_fmt) == 11:
        cpf_fmt = f"{cpf_fmt[:3]}.{cpf_fmt[3:6]}.{cpf_fmt[6:9]}-{cpf_fmt[9:]}"
    
    p.drawString(12*cm, y_dados, f"CPF: {cpf_fmt}")
    
    # 5. Forma de Pagamento
    y_pgto = y_dados - 1.5*cm
    p.drawString(2.5*cm, y_pgto, "Forma de pagamento:")
    
    draw_check(7*cm, y_pgto, "Dinheiro", recibo.forma_pagamento == 'Dinheiro')
    draw_check(10.5*cm, y_pgto, "Pix", recibo.forma_pagamento == 'Pix')
    draw_check(13*cm, y_pgto, "Transferência", recibo.forma_pagamento == 'Transferência')

    # 6. Declaração Final
    p.drawString(2.5*cm, y_pgto - 1.5*cm, "Declaro que recebi o valor acima descrito, referente ao(s) benefício(s) assinalado(s).")
    
    # 7. Assinaturas
    y_ass = y_pgto - 4*cm
    
    # Linha Empregado
    p.line(2.5*cm, y_ass, 9*cm, y_ass)
    p.setFont("Helvetica", 10)
    p.drawString(3*cm, y_ass - 0.5*cm, "Assinatura do Empregado")
    
    # Linha Empregador
    p.line(11*cm, y_ass, 17.5*cm, y_ass)
    p.drawString(11.5*cm, y_ass - 0.5*cm, "Assinatura do Empregador")
    
    # 8. Data Extenso Rodapé
    data_extenso = data_por_extenso(recibo.data_pagamento)
    p.setFont("Helvetica-Bold", 11)
    p.drawCentredString(width/2, y_ass - 2.5*cm, f"{data_extenso}.")

    p.showPage()
    p.save()
    
    buffer.seek(0)
    return buffer.read()




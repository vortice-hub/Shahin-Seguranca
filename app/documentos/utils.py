from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
import io
import calendar
from datetime import date, timedelta, datetime
from app.utils import data_por_extenso, time_to_minutes, format_minutes_to_hm

def gerar_pdf_recibo(recibo, user):
    """Gera o PDF do Recibo Financeiro."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    p.setFont("Helvetica-Bold", 14)
    p.drawString(2.5*cm, height - 3*cm, "RECIBO DE PAGAMENTO DE BENEFÍCIOS")
    p.setFont("Helvetica", 11)
    p.drawString(2.5*cm, height - 4*cm, "Recibo;")
    data_fmt = recibo.data_pagamento.strftime('%d/%m/%Y')
    p.drawString(2.5*cm, height - 4.6*cm, f"Data:  {data_fmt}")
    p.setFont("Helvetica", 11)
    
    empresa = user.razao_social_empregadora or "LA SHAHIN SERVIÇOS DE SEGURANÇA LTDA"
    cnpj = user.cnpj_empregador or "50.537.235/0001-95"
    valor_fmt = f"{recibo.valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    texto_corpo = p.beginText(2.5*cm, height - 6*cm)
    texto_corpo.setFont("Helvetica", 11)
    texto_corpo.setLeading(18)
    texto_corpo.textLines(f"Recebi de {empresa},")
    texto_corpo.textLines(f"inscrita no CNPJ nº {cnpj} a quantia de R$ {valor_fmt}")
    texto_corpo.textLines("referente ao pagamento do(s) benefício(s) abaixo assinalado(s):")
    p.drawText(texto_corpo)
    
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

    y_dados = height - 12*cm
    p.setFont("Helvetica-Bold", 12)
    p.drawString(2.5*cm, y_dados, "Dados do Funcionário")
    y_dados -= 1*cm
    p.setFont("Helvetica", 11)
    p.drawString(2.5*cm, y_dados, f"Nome: {user.real_name}")
    cpf_fmt = user.cpf if user.cpf else "00000000000"
    if len(cpf_fmt) == 11: cpf_fmt = f"{cpf_fmt[:3]}.{cpf_fmt[3:6]}.{cpf_fmt[6:9]}-{cpf_fmt[9:]}"
    p.drawString(12*cm, y_dados, f"CPF: {cpf_fmt}")
    
    y_pgto = y_dados - 1.5*cm
    p.drawString(2.5*cm, y_pgto, "Forma de pagamento:")
    draw_check(7*cm, y_pgto, "Dinheiro", recibo.forma_pagamento == 'Dinheiro')
    draw_check(10.5*cm, y_pgto, "Pix", recibo.forma_pagamento == 'Pix')
    draw_check(13*cm, y_pgto, "Transferência", recibo.forma_pagamento == 'Transferência')

    p.drawString(2.5*cm, y_pgto - 1.5*cm, "Declaro que recebi o valor acima descrito, referente ao(s) benefício(s) assinalado(s).")
    
    y_ass = y_pgto - 4*cm
    p.line(2.5*cm, y_ass, 9*cm, y_ass)
    p.setFont("Helvetica", 10)
    p.drawString(3*cm, y_ass - 0.5*cm, "Assinatura do Empregado")
    p.line(11*cm, y_ass, 17.5*cm, y_ass)
    p.drawString(11.5*cm, y_ass - 0.5*cm, "Assinatura do Empregador")
    
    data_extenso = data_por_extenso(recibo.data_pagamento)
    p.setFont("Helvetica-Bold", 11)
    p.drawCentredString(width/2, y_ass - 2.5*cm, f"{data_extenso}.")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.read()

def gerar_pdf_espelho_mensal(user, mes_ano_str):
    """Gera PDF com a tabela de pontos do mês e integra atestados médicos e férias."""
    from app.models import PontoRegistro, PontoResumo
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    try:
        ano, mes = map(int, mes_ano_str.split('-'))
    except:
        now = datetime.now()
        ano, mes = now.year, now.month

    p.setFont("Helvetica-Bold", 16)
    p.drawString(2*cm, height - 2*cm, "ESPELHO DE PONTO ELETRÔNICO")
    
    p.setFont("Helvetica", 10)
    p.drawString(2*cm, height - 3*cm, f"Colaborador: {user.real_name}")
    p.drawString(2*cm, height - 3.5*cm, f"Cargo: {user.role}")
    p.drawString(12*cm, height - 3*cm, f"Período: {mes}/{ano}")
    
    empresa = user.razao_social_empregadora or "SHAHIN GESTÃO"
    cnpj = user.cnpj_empregador or ""
    p.drawString(2*cm, height - 4*cm, f"Empresa: {empresa} - CNPJ: {cnpj}")
    
    dados = [['Data', 'Dia', 'Entradas / Saídas', 'Jornada', 'Saldo', 'Status']]
    last_day = calendar.monthrange(ano, mes)[1]
    total_saldo_min = 0
    dias_semana = {0:'Seg', 1:'Ter', 2:'Qua', 3:'Qui', 4:'Sex', 5:'Sáb', 6:'Dom'}
    
    for dia in range(1, last_day + 1):
        dt_atual = date(ano, mes, dia)
        
        # Busca batidas no registro
        pontos = PontoRegistro.query.filter_by(user_id=user.id, data_registro=dt_atual).order_by(PontoRegistro.hora_registro).all()
        horarios_str = "  ".join([pt.hora_registro.strftime('%H:%M') for pt in pontos])
        
        # Busca o status consolidado do dia (Para ver se teve Atestado Aprovado, Férias, etc.)
        resumo_dia = PontoResumo.query.filter_by(user_id=user.id, data_referencia=dt_atual).first()
        
        meta = user.carga_horaria or 528
        if user.escala == '5x2' and dt_atual.weekday() >= 5: meta = 0
        elif user.escala == '12x36' and user.data_inicio_escala:
            if (dt_atual - user.data_inicio_escala).days % 2 != 0: meta = 0
            else: meta = 720
            
        trabalhado = 0
        for i in range(0, len(pontos), 2):
            if i+1 < len(pontos):
                trabalhado += (time_to_minutes(pontos[i+1].hora_registro) - time_to_minutes(pontos[i].hora_registro))
        
        saldo = trabalhado - meta
        
        # LÓGICA DE AFASTAMENTO - Substitui tudo se o funcionário estiver afastado (Férias, Licença, Atestado)
        status_abonados = ['Atestado', 'Férias', 'Licença', 'Folga Prêmio', 'Ferias', 'Licenca', 'Folga Premio']
        
        if resumo_dia and resumo_dia.status_dia in status_abonados:
            horarios_str = str(resumo_dia.status_dia).upper() # Escreve no PDF: "FÉRIAS", "ATESTADO"...
            trabalhado = 0
            saldo = 0  # Zera as horas devidas
            status = "Abono"
        else:
            status = "OK"
            if not pontos: status = "Folga" if meta == 0 else "Falta"
            elif len(pontos) % 2 != 0: status = "Inc."
            elif saldo > 10: status = "+ Extra"
            elif saldo < -10: status = "Débito" if meta > 0 else "Extra"

        total_saldo_min += saldo
        dados.append([dt_atual.strftime('%d/%m'), dias_semana[dt_atual.weekday()], horarios_str, format_minutes_to_hm(trabalhado).replace('-', ''), format_minutes_to_hm(saldo), status])
    
    dados.append(['', '', 'TOTAL MENSAL', '', format_minutes_to_hm(total_saldo_min), ''])

    t = Table(dados, colWidths=[2*cm, 1.5*cm, 6*cm, 2*cm, 2*cm, 2.5*cm])
    t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.navy), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,0), 9), ('BOTTOMPADDING', (0,0), (-1,0), 8), ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey), ('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('FONTSIZE', (0,1), (-1,-1), 8)]))
    w, h = t.wrapOn(p, width, height)
    t.drawOn(p, 2*cm, height - 6*cm - h)
    
    y_ass = 3*cm
    p.line(2*cm, y_ass, 9*cm, y_ass)
    p.setFont("Helvetica", 8)
    p.drawString(3*cm, y_ass - 0.5*cm, "Assinatura do Colaborador")
    p.line(12*cm, y_ass, 19*cm, y_ass)
    p.drawString(13*cm, y_ass - 0.5*cm, "Gestor Responsável")
    p.drawString(2*cm, 1.5*cm, f"Documento gerado eletronicamente em {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.read()

def gerar_certificado_entrega(assinatura, user):
    """Gera um PDF de auditoria (Certificado de Entrega Digital)."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Cabeçalho Oficial
    p.setFillColor(colors.navy)
    p.rect(0, height - 3*cm, width, 3*cm, fill=True, stroke=False)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(width/2, height - 2*cm, "CERTIFICADO DE ENTREGA DIGITAL")
    
    # Corpo
    p.setFillColor(colors.black)
    p.setFont("Helvetica", 12)
    
    texto = p.beginText(2.5*cm, height - 5*cm)
    texto.setLeading(20)
    texto.textLines(f"Certificamos, para os devidos fins de direito e prova, que o colaborador:")
    texto.textLines(f"Nome: {user.real_name}")
    texto.textLines(f"CPF: {user.cpf}")
    texto.textLines(f"")
    texto.textLines(f"Realizou o ACESSO e CONFIRMAÇÃO DE RECEBIMENTO do documento digital")
    texto.textLines(f"identificado abaixo, através da plataforma SHAHIN GESTÃO.")
    p.drawText(texto)
    
    # Caixa de Dados Forenses
    p.setStrokeColor(colors.grey)
    p.rect(2.5*cm, height - 16*cm, 16*cm, 7*cm)
    
    p.setFont("Helvetica-Bold", 12)
    p.drawString(3*cm, height - 10*cm, "DADOS DA TRANSAÇÃO DIGITAL")
    
    p.setFont("Helvetica", 10)
    y_forense = height - 11*cm
    p.drawString(3*cm, y_forense, f"Documento: {assinatura.tipo_documento} (ID: {assinatura.documento_id})")
    p.drawString(3*cm, y_forense - 1*cm, f"Data/Hora do Acesso: {assinatura.data_assinatura.strftime('%d/%m/%Y %H:%M:%S')} (UTC-3)")
    p.drawString(3*cm, y_forense - 2*cm, f"Endereço IP de Origem: {assinatura.ip_address}")
    p.drawString(3*cm, y_forense - 3*cm, f"Dispositivo/Navegador: {assinatura.user_agent[:60]}...")
    
    p.setFont("Helvetica-Bold", 10)
    p.drawString(3*cm, y_forense - 4.5*cm, "Hash de Integridade (SHA-256):")
    p.setFont("Courier", 8)
    p.drawString(3*cm, y_forense - 5*cm, f"{assinatura.hash_arquivo}")
    
    # Rodapé Legal
    p.setFont("Helvetica-Oblique", 9)
    p.drawCentredString(width/2, 3*cm, "Este registro eletrônico possui validade jurídica conforme MP 2.200-2/2001.")
    p.drawCentredString(width/2, 2.5*cm, "A integridade do arquivo pode ser verificada através do Hash acima.")
    
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.read()


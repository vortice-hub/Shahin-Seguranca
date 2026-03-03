import io
import pandas as pd
from datetime import datetime, timedelta
from pypdf import PdfReader, PdfWriter

from app.extensions import db
from app.models import Holerite, Recibo, AssinaturaDigital, Atestado, PontoResumo, User
from app.repositories.documento_repository import (HoleriteRepository, ReciboRepository, 
                                                   AtestadoRepository, AssinaturaDigitalRepository)
from app.repositories.user_repository import UserRepository
from app.repositories.ponto_repository import PontoResumoRepository
from app.utils import get_brasil_time, limpar_nome, format_minutes_to_hm, enviar_notificacao, calcular_hash_arquivo
from app.documentos.storage import salvar_no_storage
from app.documentos.ai_parser import extrair_dados_holerite
from app.documentos.atestado_parser import analisar_atestado_vision

class DocumentoService:
    def __init__(self):
        self.holerite_repo = HoleriteRepository()
        self.recibo_repo = ReciboRepository()
        self.atestado_repo = AtestadoRepository()
        self.assinatura_repo = AssinaturaDigitalRepository()
        self.user_repo = UserRepository()
        self.resumo_repo = PontoResumoRepository()

    def processar_holerites_lote(self, file_bytes, empresa_slug):
        """Lê o PDF mestre e fatia em holerites individuais."""
        reader = PdfReader(io.BytesIO(file_bytes))
        sucesso, revisao = 0, 0
        
        usuarios_db = self.user_repo.get_all()
        # Ignora o utilizador terminal logo no mapeamento para envio
        usuarios_map = {limpar_nome(u.real_name): u.id for u in usuarios_db if u.role != 'Terminal'}
        lista_nomes_banco = list(usuarios_map.keys())

        for page in reader.pages:
            writer = PdfWriter(); writer.add_page(page); buffer = io.BytesIO(); writer.write(buffer)
            pdf_bytes_page = buffer.getvalue()
            
            dados = extrair_dados_holerite(pdf_bytes_page, lista_nomes_banco)
            nome_identificado = dados.get('nome', '')
            mes_ref = dados.get('mes_referencia', '2026-02')

            caminho_blob = salvar_no_storage(pdf_bytes_page, f"holerites/{mes_ref}", empresa_slug)
            if not caminho_blob: continue

            user_id = usuarios_map.get(nome_identificado)

            novo_h = Holerite(
                user_id=user_id, mes_referencia=mes_ref, url_arquivo=caminho_blob,
                status='Enviado' if user_id else 'Revisao', enviado_em=get_brasil_time()
            )
            self.holerite_repo.add(novo_h)
            
            if user_id: 
                sucesso += 1
                enviar_notificacao(user_id, f"Novo Holerite disponível para assinatura ({mes_ref}).", "/documentos/meus-documentos")
            else: 
                revisao += 1

        self.holerite_repo.commit()
        return sucesso, revisao

    def registrar_assinatura(self, user_id, doc_id, tipo_doc, arquivo_bytes, ip_address, user_agent):
        """Gera o registo legal de leitura (Assinatura Eletrónica)."""
        assinatura = AssinaturaDigital(
            user_id=user_id,
            documento_id=doc_id,
            tipo_documento=tipo_doc,
            hash_arquivo=calcular_hash_arquivo(arquivo_bytes),
            data_assinatura=get_brasil_time(),
            ip_address=ip_address,
            user_agent=user_agent
        )
        self.assinatura_repo.add(assinatura)
        self.assinatura_repo.commit()

    def avaliar_atestado(self, atestado, acao, form_data):
        """Avalia o atestado e automaticamente abona os dias no Ponto."""
        if acao == 'aprovar':
            data_inicio_str = form_data.get('data_inicio')
            qtd_dias_str = form_data.get('quantidade_dias')
            if not data_inicio_str or not qtd_dias_str: raise ValueError("Dados incompletos.")

            atestado.data_inicio_afastamento = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
            atestado.quantidade_dias = int(qtd_dias_str)
            atestado.status = 'Aprovado'
            
            # Abona o ponto
            for i in range(atestado.quantidade_dias):
                dia_atual = atestado.data_inicio_afastamento + timedelta(days=i)
                ponto = self.resumo_repo.get_by_user_and_date(atestado.user_id, dia_atual)
                if ponto:
                    ponto.status_dia = 'Atestado'
                    ponto.minutos_esperados = 0
                    ponto.minutos_saldo = ponto.minutos_trabalhados
                else:
                    novo_ponto = PontoResumo(user_id=atestado.user_id, data_referencia=dia_atual, minutos_trabalhados=0, minutos_esperados=0, minutos_saldo=0, status_dia='Atestado')
                    self.resumo_repo.add(novo_ponto)
                    
            enviar_notificacao(atestado.user_id, "O seu Atestado foi recebido e APROVADO com sucesso.", "/documentos/atestados/meus")
            
        elif acao == 'recusar':
            atestado.status = 'Recusado'
            atestado.motivo_recusa = form_data.get('motivo_recusa', 'Recusado pelo RH')
            enviar_notificacao(atestado.user_id, "O seu Atestado foi RECUSADO. Verifique o motivo.", "/documentos/atestados/meus")
            
        self.atestado_repo.commit()

    def gerar_relatorio_excel(self, data_inicio_str, data_fim_str):
        """Processa a matemática complexa do Fechamento de Folha."""
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        
        usuarios = self.user_repo.get_all()
        dados_relatorio = []
        
        for u in usuarios:
            # PONTO 23: IGNORAR O FUNCIONÁRIO TERMINAL E MASTER DE FORMA EFICIENTE
            if u.role == 'Terminal' or u.username == '50097952800' or u.username == '12345678900': 
                continue
            
            pontos = PontoResumo.query.filter(
                PontoResumo.user_id == u.id,
                PontoResumo.data_referencia >= data_inicio,
                PontoResumo.data_referencia <= data_fim
            ).all()
            
            total_esperado = sum(p.minutos_esperados for p in pontos)
            total_trabalhado = sum(p.minutos_trabalhados for p in pontos)
            saldo = total_trabalhado - total_esperado
            
            faltas = sum(1 for p in pontos if p.status_dia == 'Falta')
            atestados = sum(1 for p in pontos if p.status_dia == 'Atestado')
            
            sinal = "+" if saldo >= 0 else "-"
            saldo_str = f"{sinal}{format_minutes_to_hm(abs(saldo))}"
            
            dados_relatorio.append({
                'Nome do Funcionário': u.real_name,
                'CPF': u.cpf,
                'Departamento': u.departamento or 'Não Definido',
                'Cargo': u.role,
                'Total Horas Esperadas': format_minutes_to_hm(total_esperado),
                'Total Horas Realizadas': format_minutes_to_hm(total_trabalhado),
                'Saldo Extra / Débito': saldo_str,
                'Total Faltas (Dias)': faltas,
                'Atestados (Dias)': atestados
            })
            
        if not dados_relatorio: return None
            
        df = pd.DataFrame(dados_relatorio)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Fechamento Folha')
            worksheet = writer.sheets['Fechamento Folha']
            
            for i, col in enumerate(df.columns):
                larguras = [len(str(v)) for v in df[col].values] + [len(str(col))]
                max_len = max(larguras) + 2
                worksheet.column_dimensions[chr(65 + i)].width = min(max_len, 50)

        output.seek(0)
        return output


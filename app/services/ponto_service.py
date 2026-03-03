import io
import calendar
from datetime import datetime, time, timedelta
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

from app.extensions import db
from app.repositories.ponto_repository import (PontoRegistroRepository, PontoResumoRepository, 
                                               PontoAjusteRepository, SolicitacaoAusenciaRepository)
from app.repositories.user_repository import UserRepository
from app.models import PontoRegistro, PontoResumo, PontoAjuste, SolicitacaoAusencia, Holerite, Empresa, User
from app.utils import time_to_minutes, get_brasil_time, format_minutes_to_hm, enviar_notificacao
from app.documentos.storage import salvar_no_storage

class PontoService:
    def __init__(self):
        self.reg_repo = PontoRegistroRepository()
        self.resumo_repo = PontoResumoRepository()
        self.ajuste_repo = PontoAjusteRepository()
        self.ausencia_repo = SolicitacaoAusenciaRepository()
        self.user_repo = UserRepository()

    def calcular_dia(self, user_id, data_ref):
        """Lógica central de cálculo de ponto isolada no Service."""
        user = self.user_repo.get_by_id(user_id)
        if not user: return

        registros = self.reg_repo.get_by_user_and_date(user_id, data_ref)
        meta = user.carga_horaria if user.carga_horaria else 528
        
        # --- CÉREBRO DE ESCALAS ---
        if user.escala == '5x2' and data_ref.weekday() >= 5: 
            meta = 0
        elif user.escala == '12x36' and user.data_inicio_escala:
            dias_diff = (data_ref - user.data_inicio_escala).days
            if dias_diff % 2 != 0: meta = 0
            else: meta = 720
        elif user.escala == '6x1' and user.data_inicio_escala:
            # Matemática 6x1: Um ciclo tem 7 dias. A folga é o 7º dia (índice 6).
            dias_diff = (data_ref - user.data_inicio_escala).days
            if dias_diff % 7 == 6: meta = 0
        elif user.escala == 'Personalizado':
            # Se for personalizado, assume a carga configurada ou permite ajuste flexível
            pass
                
        trab = 0
        for i in range(0, len(registros), 2):
            if i + 1 < len(registros):
                entrada = time_to_minutes(registros[i].hora_registro)
                saida = time_to_minutes(registros[i+1].hora_registro)
                trab += (saida - entrada)
                
        saldo = trab - meta
        
        status = "OK"
        if not registros:
            status = "Falta" if meta > 0 else "Folga"
        elif len(registros) % 2 != 0:
            status = "Incompleto"
        elif saldo > 10:
            status = "Hora Extra"
        elif saldo < -10:
            status = "Débito" if meta > 0 else "Extra" 
            
        resumo = self.resumo_repo.get_by_user_and_date(user_id, data_ref)
        if not resumo:
            resumo = PontoResumo(user_id=user_id, data_referencia=data_ref)
            self.resumo_repo.add(resumo)
        
        resumo.minutos_trabalhados = trab
        resumo.minutos_esperados = meta
        resumo.minutos_saldo = saldo
        resumo.status_dia = status
        
        try:
             self.resumo_repo.commit()
        except:
             self.resumo_repo.rollback()

    def verificar_bloqueio_ponto(self, user, data_obj):
        ausencia = self.ausencia_repo.get_aprovada_por_data(user.id, data_obj)
        if ausencia: 
            return True, f"Afastamento programado: {ausencia.tipo_ausencia}"
        elif user.escala == '5x2' and data_obj.weekday() >= 5: 
            return True, "Fim de semana (Escala 5x2)."
        elif user.escala == '12x36' and user.data_inicio_escala:
            if (data_obj - user.data_inicio_escala).days % 2 != 0: 
                return True, "Dia de folga (Escala 12x36)."
        elif user.escala == '6x1' and user.data_inicio_escala:
            if (data_obj - user.data_inicio_escala).days % 7 == 6:
                return True, "Dia de folga (Escala 6x1)."
        return False, ""

    def determinar_proxima_batida(self, user_id, data_obj):
        pontos = self.reg_repo.get_by_user_and_date(user_id, data_obj)
        if len(pontos) == 0: return "Entrada"
        elif len(pontos) == 1: return "Ida Almoço"
        elif len(pontos) == 2: return "Volta Almoço"
        elif len(pontos) == 3: return "Saída"
        else: return "Extra"

    def processar_solicitacao_ferias(self, user, form_data, saldo):
        tipo = form_data.get('tipo_ausencia')
        dt_inicio = datetime.strptime(form_data.get('data_inicio'), '%Y-%m-%d').date()
        dt_fim = datetime.strptime(form_data.get('data_fim'), '%Y-%m-%d').date()
        obs = form_data.get('observacao', '')
        vender_ferias = form_data.get('vender_ferias') == 'sim'
        
        if dt_inicio > dt_fim:
            raise ValueError("A data de início não pode ser maior que a data de fim.")
            
        qtd_dias = (dt_fim - dt_inicio).days + 1
        dias_abono = 0

        if tipo == 'Férias':
            if not user.data_admissao:
                raise ValueError("Data de admissão ausente. O RH deve configurar seu perfil antes de solicitar férias.")

            if vender_ferias:
                dias_abono = qtd_dias // 2 
                dias_direito = 30
                if dias_abono > (dias_direito / 3):
                    raise ValueError(f"A CLT permite vender no máximo 1/3 das férias (Max: {int(dias_direito/3)} dias).")
                total_descontado = qtd_dias + dias_abono
                if total_descontado > saldo:
                    raise ValueError(f"Saldo insuficiente. Você tem {saldo} dias disponíveis, mas o pedido totaliza {total_descontado} dias.")
            else:
                if qtd_dias > saldo:
                    raise ValueError(f"Saldo insuficiente. Você possui apenas {saldo} dias.")

            if qtd_dias < 5:
                raise ValueError("Pela CLT, o período fracionado de férias não pode ser inferior a 5 dias.")

            if user.escala == '5x2' and dt_inicio.weekday() in [3, 4]:
                raise ValueError("Ilegal: O início das férias não pode ocorrer nos 2 dias que antecedem o repouso semanal (Sáb/Dom).")

        nova_solicitacao = SolicitacaoAusencia(
            user_id=user.id, tipo_ausencia=tipo, data_inicio=dt_inicio, data_fim=dt_fim, 
            quantidade_dias=qtd_dias, abono_pecuniario=vender_ferias, dias_abono=dias_abono, observacao=obs
        )
        self.ausencia_repo.add(nova_solicitacao)
        self.ausencia_repo.commit()
        return tipo

    def gerar_espelhos_lote(self, empresa_id, mes_ref):
        """Ponto 20: Gera os PDFs de Espelho de Ponto em lote e distribui para assinatura."""
        try:
            ano, mes = map(int, mes_ref.split('-'))
            _, ultimo_dia = calendar.monthrange(ano, mes)
            data_inicio = datetime(ano, mes, 1).date()
            data_fim = datetime(ano, mes, ultimo_dia).date()
        except Exception:
            return False, "Mês de referência inválido."

        empresa = Empresa.query.get(empresa_id)
        if not empresa: 
            return False, "Empresa não encontrada."

        usuarios = User.query.filter_by(empresa_id=empresa_id).filter(User.role != 'Terminal', User.username != '50097952800').all()
        
        count = 0
        for u in usuarios:
            pontos = PontoResumo.query.filter(
                PontoResumo.user_id == u.id, 
                PontoResumo.data_referencia >= data_inicio, 
                PontoResumo.data_referencia <= data_fim
            ).order_by(PontoResumo.data_referencia).all()
            
            if not pontos:
                continue

            # Inicia o gerador de PDF
            buffer = io.BytesIO()
            p = canvas.Canvas(buffer, pagesize=A4)
            
            # Cabeçalho
            p.setFont("Helvetica-Bold", 14)
            p.drawString(50, 800, f"ESPELHO DE PONTO - REFERÊNCIA: {mes_ref}")
            p.setFont("Helvetica", 10)
            p.drawString(50, 780, f"EMPRESA: {empresa.nome}")
            p.drawString(50, 765, f"COLABORADOR: {u.real_name}")
            p.drawString(50, 750, f"CPF: {u.cpf}   |   CARGO: {u.role}")
            
            # Tabela (Cabeçalho)
            y = 710
            p.setFont("Helvetica-Bold", 9)
            p.drawString(50, y, "DATA")
            p.drawString(120, y, "STATUS")
            p.drawString(240, y, "TRABALHADO")
            p.drawString(340, y, "ESPERADO")
            p.drawString(440, y, "SALDO (Extra/Falta)")
            p.line(50, y - 5, 500, y - 5)
            y -= 20
            
            total_trab = 0
            total_esp = 0
            
            p.setFont("Helvetica", 9)
            for pt in pontos:
                if y < 50:
                    p.showPage()
                    p.setFont("Helvetica", 9)
                    y = 800
                    
                p.drawString(50, y, pt.data_referencia.strftime('%d/%m/%Y'))
                p.drawString(120, y, pt.status_dia or "OK")
                p.drawString(240, y, format_minutes_to_hm(pt.minutos_trabalhados))
                p.drawString(340, y, format_minutes_to_hm(pt.minutos_esperados))
                
                saldo_str = format_minutes_to_hm(abs(pt.minutos_saldo))
                sinal = "+" if pt.minutos_saldo >= 0 else "-"
                p.drawString(440, y, f"{sinal} {saldo_str}")
                
                total_trab += pt.minutos_trabalhados
                total_esp += pt.minutos_esperados
                y -= 15
            
            # Totais
            y -= 10
            p.line(50, y + 10, 500, y + 10)
            saldo_final = total_trab - total_esp
            sinal_final = "+" if saldo_final >= 0 else "-"
            
            p.setFont("Helvetica-Bold", 10)
            p.drawString(50, y, "TOTAIS DO MÊS:")
            p.drawString(240, y, format_minutes_to_hm(total_trab))
            p.drawString(340, y, format_minutes_to_hm(total_esp))
            p.drawString(440, y, f"{sinal_final} {format_minutes_to_hm(abs(saldo_final))}")
            
            # Rodapé para Assinatura Eletrónica
            y -= 50
            p.setFont("Helvetica-Oblique", 8)
            p.drawString(50, y, "Documento gerado e assinado digitalmente pelo sistema Vortice SaaS.")
            
            p.showPage()
            p.save()
            
            pdf_bytes = buffer.getvalue()
            
            # Salvar no Storage
            caminho_blob = salvar_no_storage(pdf_bytes, f"espelhos/{mes_ref}", empresa.slug)
            
            if caminho_blob:
                holerite_existente = Holerite.query.filter_by(user_id=u.id, mes_referencia=mes_ref, empresa_id=empresa_id).filter(Holerite.url_arquivo.like('%espelhos%')).first()
                if not holerite_existente:
                    novo_h = Holerite(
                        user_id=u.id, mes_referencia=mes_ref, url_arquivo=caminho_blob,
                        status='Enviado', enviado_em=get_brasil_time(), empresa_id=empresa_id
                    )
                    db.session.add(novo_h)
                else:
                    holerite_existente.url_arquivo = caminho_blob
                    holerite_existente.status = 'Enviado'
                    holerite_existente.enviado_em = get_brasil_time()
                    holerite_existente.visualizado = False 
                
                enviar_notificacao(u.id, f"Novo Espelho de Ponto disponível para assinatura ({mes_ref}).", "/documentos/meus-documentos")
                count += 1

        db.session.commit()
        return True, f"{count} espelhos gerados e disponibilizados com sucesso."


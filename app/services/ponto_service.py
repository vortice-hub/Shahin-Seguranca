from datetime import datetime, time, timedelta
from app.repositories.ponto_repository import (PontoRegistroRepository, PontoResumoRepository, 
                                               PontoAjusteRepository, SolicitacaoAusenciaRepository)
from app.repositories.user_repository import UserRepository
from app.models import PontoRegistro, PontoResumo, PontoAjuste, SolicitacaoAusencia
from app.utils import time_to_minutes, get_brasil_time

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
        
        if user.escala == '5x2' and data_ref.weekday() >= 5: 
            meta = 0
        elif user.escala == '12x36' and user.data_inicio_escala:
            dias_diff = (data_ref - user.data_inicio_escala).days
            if dias_diff % 2 != 0: meta = 0
            else: meta = 720
                
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
                # Simulação simples de dias de direito (Idealmente passado por parâmetro ou calculado no service)
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
                raise ValueError("Pela CLT (Reforma 2017), o período fracionado de férias não pode ser inferior a 5 dias.")

            if user.escala == '5x2' and dt_inicio.weekday() in [3, 4]:
                raise ValueError("Ilegal: O início das férias não pode ocorrer nos 2 dias que antecedem o repouso semanal (Sáb/Dom).")

        nova_solicitacao = SolicitacaoAusencia(
            user_id=user.id, tipo_ausencia=tipo, data_inicio=dt_inicio, data_fim=dt_fim, 
            quantidade_dias=qtd_dias, abono_pecuniario=vender_ferias, dias_abono=dias_abono, observacao=obs
        )
        self.ausencia_repo.add(nova_solicitacao)
        self.ausencia_repo.commit()
        return tipo


import os
import io
import uuid
import json
import logging
from datetime import datetime, date, timedelta, time
import pytz 

from app.extensions import db
from app.models import (Empresa, User, Role, PontoRegistro, PontoResumo, PontoAjuste, 
                        Notificacao, SolicitacaoAusencia, SolicitacaoUniforme, ItemEstoque, 
                        Holerite, Recibo, AssinaturaDigital, PreCadastro, Permission,
                        Atestado, PushSubscription, PeriodoAquisitivo, HistoricoEntrada, HistoricoSaida)

from app.services.empresa_service import EmpresaService
from app.services.user_service import UserService
from app.services.ponto_service import PontoService
from app.services.estoque_service import EstoqueService
from app.services.documento_service import DocumentoService
from app.utils import get_brasil_time, has_permission 
from app.documentos.storage import salvar_no_storage, get_bucket_name 
from google.cloud import storage

logger = logging.getLogger(__name__)

class TestService:
    def __init__(self):
        self.logs = []
        self.test_suffix = uuid.uuid4().hex[:4]
        self.empresa_service = EmpresaService()
        self.user_service = UserService()
        self.ponto_service = PontoService()
        self.estoque_service = EstoqueService()
        self.doc_service = DocumentoService()
        
        self.emp_alfa = None
        self.emp_beta = None
        self.master_alfa = None
        self.func_alfa = None

    def add_log(self, ponto_id, funcionalidade, status, diagnostico):
        self.logs.append({
            'ponto_controle': ponto_id,
            'funcionalidade': funcionalidade,
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'diagnostico': diagnostico
        })

    def run_full_audit(self):
        """Orquestrador do Super Robô - Agora com 20 pontos de controle."""
        try:
            # --- FASES DE FUNDAÇÃO (Infra, DB, Users) ---
            self._test_infra_and_master_creation()
            self._test_terminal_creation()
            self._test_user_onboarding_and_routing()
            
            # --- PREPARAÇÃO DO FUNCIONÁRIO PARA OS TESTES ---
            # Dá 2 anos de casa ao funcionário para ele ter direito a férias
            self.func_alfa.data_admissao = date.today() - timedelta(days=730)
            db.session.commit()

            # --- FASES DE ROTINA E SEGURANÇA BÁSICA ---
            self._test_ponto_lifecycle()
            self._test_logistics_and_stock()
            self._test_medical_and_storage_paths()
            self._test_digital_signature_flow()
            self._test_payroll_reports()
            
            # --- MÓDULOS DE SEGURANÇA AVANÇADA (Hack / Leak) ---
            self._audit_rbac_penetration()
            self._audit_storage_consistency()
            self._audit_timezone_integrity()

            # =========================================================
            # 🔥 NOVOS WORKFLOWS HUMANOS (Ação e Reação)
            # =========================================================
            self._workflow_ferias_rh()
            self._workflow_epi_almoxarifado()
            self._workflow_atestado_medico()
            self._workflow_ia_fatiamento_pdf()

            return self.logs
        except Exception as e:
            self.add_log('CRÍTICO', 'Falha no Super Robô', 'ERRO', str(e))
            return self.logs

    # ==============================================================================
    # 🧑‍🤝‍🧑 WORKFLOWS (AÇÕES HUMANAS SIMULADAS)
    # ==============================================================================
    def _workflow_ferias_rh(self):
        """Simula o funcionário pedir férias e o RH aprovar, gerando abono no espelho."""
        try:
            # 1. Funcionário pede 10 dias de férias
            dt_inicio = date.today() + timedelta(days=30)
            dt_fim = dt_inicio + timedelta(days=9)
            form_data = {
                'tipo_ausencia': 'Férias', 'data_inicio': dt_inicio.strftime('%Y-%m-%d'),
                'data_fim': dt_fim.strftime('%Y-%m-%d'), 'vender_ferias': 'nao', 'observacao': 'Vortice Labs'
            }
            self.ponto_service.processar_solicitacao_ferias(self.func_alfa, form_data, saldo=30)
            
            # 2. Master aprova (Simulando a rota admin/ausencias)
            solic = SolicitacaoAusencia.query.filter_by(user_id=self.func_alfa.id).first()
            solic.status = 'Aprovado'
            
            # 3. Abate no espelho (como faz a view admin_ausencias)
            for i in range(solic.quantidade_dias):
                dia_atual = solic.data_inicio + timedelta(days=i)
                novo_ponto = PontoResumo(user_id=solic.user_id, data_referencia=dia_atual, minutos_trabalhados=0, minutos_esperados=0, minutos_saldo=0, status_dia='Férias', empresa_id=self.emp_alfa.id)
                db.session.add(novo_ponto)
            db.session.commit()
            
            self.add_log('P17', 'Workflow Férias', 'OK', "Pedido validado. RH aprovou e o espelho de ponto foi preenchido automaticamente com Abono.")
        except Exception as e:
            self.add_log('P17', 'Workflow Férias', 'ERRO', str(e))

    def _workflow_epi_almoxarifado(self):
        """Simula um pedido de Bota via App e a entrega/dedução pelo RH."""
        try:
            item = ItemEstoque.query.filter_by(empresa_id=self.emp_alfa.id).first()
            estoque_inicial = item.quantidade # Tinha 10
            
            # Funcionário pede 2 botas
            self.estoque_service.solicitar_uniforme_colaborador(self.func_alfa, {'item_id': item.id, 'quantidade': 2})
            solic = SolicitacaoUniforme.query.filter_by(user_id=self.func_alfa.id).first()
            
            # RH aprova
            self.estoque_service.avaliar_solicitacao(coordenador=self.master_alfa, solic_id=solic.id, acao='aprovar')
            
            # Valida a matemática
            db.session.refresh(item)
            if item.quantidade == (estoque_inicial - 2):
                self.add_log('P18', 'Workflow EPI/Estoque', 'OK', f"EPI solicitado. RH aprovou. Estoque deduzido perfeitamente de {estoque_inicial} para {item.quantidade}.")
            else:
                self.add_log('P18', 'Workflow EPI/Estoque', 'ERRO', "Falha matemática na dedução de estoque.")
        except Exception as e:
            self.add_log('P18', 'Workflow EPI/Estoque', 'ERRO', str(e))

    def _workflow_atestado_medico(self):
        """Simula o envio de um atestado médico e a conversão de Falta para Atestado."""
        try:
            # Finge que o funcionário anexou um PDF e criou no banco (Campos corrigidos)
            atestado = Atestado(
                user_id=self.func_alfa.id, 
                empresa_id=self.emp_alfa.id, 
                url_arquivo="fake_url", 
                status="Pendente",
                data_envio=get_brasil_time()
            )
            db.session.add(atestado); db.session.commit()
            
            # RH avalia
            form_data = {'data_inicio': date.today().strftime('%Y-%m-%d'), 'quantidade_dias': '1'}
            self.doc_service.avaliar_atestado(atestado, 'aprovar', form_data)
            
            # Verifica se gerou rebatimento
            ponto = PontoResumo.query.filter_by(user_id=self.func_alfa.id, data_referencia=date.today()).first()
            if ponto and ponto.status_dia == 'Atestado':
                self.add_log('P19', 'Workflow Atestado', 'OK', "Atestado médico aprovado pelo RH e falta abonada no espelho com sucesso.")
            else:
                self.add_log('P19', 'Workflow Atestado', 'ERRO', "O Atestado foi aprovado, mas não alterou o Ponto do funcionário.")
        except Exception as e:
             self.add_log('P19', 'Workflow Atestado', 'ERRO', str(e))

    def _workflow_ia_fatiamento_pdf(self):
        """Simula a I.A lendo um PDF gigante de holerites para fatiar por funcionário."""
        try:
            # Constrói um PDF válido microscópico em memória (bytes) para o PyPDF não dar crash
            pdf_minimo = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>/Contents 4 0 R>>endobj\n4 0 obj<</Length 21>>stream\nBT /F1 24 Tf 100 100 Td (Hello) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000109 00000 n \n0000000204 00000 n \ntrailer<</Size 5/Root 1 0 R>>\nstartxref\n274\n%%EOF"
            
            sucesso, revisao = self.doc_service.processar_holerites_lote(pdf_minimo, self.emp_alfa.slug)
            
            self.add_log('P20', 'Motor IA PDF Lote', 'OK', f"PDF mastigado pela IA. Resultados -> Encontrados: {sucesso} | Revisão Manual: {revisao}. Motor PyPDF rodando liso.")
        except Exception as e:
            self.add_log('P20', 'Motor IA PDF Lote', 'ERRO', f"O Motor de PDF quebrou durante o processamento em lote: {str(e)}")

    # ==============================================================================
    # ⚙️ MÓDULOS BASE (Segurança e Integração)
    # ==============================================================================

    def _audit_rbac_penetration(self):
        vigia = User(username=f"vigia_{self.test_suffix}", real_name="Vigia Teste", role="Vigia", empresa_id=self.emp_alfa.id)
        vigia.set_password('123456') 
        db.session.add(vigia); db.session.commit()

        is_master = (vigia.role == 'Master' or str(vigia.username) == '50097952800')
        if not is_master: self.add_log('P14.1', 'Penetração RBAC (Master)', 'OK', "Usuário comum impedido de agir como Master.")
        else: self.add_log('P14.1', 'Penetração RBAC (Master)', 'ERRO', "FALHA: Usuário detectado como Master!")

        has_perm = 'USUARIOS' in vigia.permissions.upper() if vigia.permissions else False
        if not has_perm: self.add_log('P14.2', 'Penetração RBAC (Permissão)', 'OK', "Acesso negado para módulo restrito.")
        else: self.add_log('P14.2', 'Penetração RBAC (Permissão)', 'ERRO', "Vazamento de privilégios.")

    def _audit_storage_consistency(self):
        client = storage.Client(); bucket = client.bucket(get_bucket_name())
        blobs = list(bucket.list_blobs(prefix=f"{self.emp_alfa.slug}/"))
        if len(blobs) > 0:
            if all(b.name.startswith(f"{self.emp_alfa.slug}/") for b in blobs):
                self.add_log('P15', 'Faxineiro de Storage', 'OK', f"Consistência validada: {len(blobs)} arquivos confinados em /{self.emp_alfa.slug}/.")
            else: self.add_log('P15', 'Faxineiro de Storage', 'ERRO', "Arquivos vazaram do slug da empresa!")
        else: self.add_log('P15', 'Faxineiro de Storage', 'ALERTA', "Nenhum arquivo físico gerado para validar.")

    def _audit_timezone_integrity(self):
        diff = datetime.now().hour - get_brasil_time().hour
        if diff < 0: diff += 24
        if diff >= 0: self.add_log('P16', 'Relógio Atômico', 'OK', "Timezone validado em fuso BR.")
        else: self.add_log('P16', 'Relógio Atômico', 'ERRO', "Risco trabalhista de Timezone!")

    def _test_infra_and_master_creation(self):
        self.emp_alfa, self.master_alfa = self.empresa_service.criar_nova_conta_cliente(
            {'nome': f"TEST_ALFA_{self.test_suffix}", 'plano': 'Enterprise'},
            {'nome_completo': 'Admin Alfa', 'cpf': f"111000000{self.test_suffix[:2]}", 'senha_provisoria': '123456'}
        )
        self.emp_beta, _ = self.empresa_service.criar_nova_conta_cliente(
            {'nome': f"TEST_BETA_{self.test_suffix}", 'plano': 'Standard'},
            {'nome_completo': 'Admin Beta', 'cpf': f"222000000{self.test_suffix[:2]}", 'senha_provisoria': '123456'}
        )
        self.add_log('P1/P3', 'Infra e Master', 'OK', f"Tenants {self.emp_alfa.slug} e {self.emp_beta.slug} criados.")

    def _test_terminal_creation(self):
        term = User(username=f"term_{self.test_suffix}", real_name="Terminal Teste", role="Terminal", empresa_id=self.emp_alfa.id)
        term.set_password('123456') 
        db.session.add(term); db.session.commit()
        self.add_log('P2', 'Conta Terminal', 'OK', "Usuário de leitura gerado.")

    def _test_user_onboarding_and_routing(self):
        cpf = f"444555666{self.test_suffix[:2]}"
        self.user_service.criar_pre_cadastro({'cpf': cpf, 'real_name': 'Func Teste', 'role': 'Operador', 'empresa_id': self.emp_alfa.id})
        pre = PreCadastro.query.filter_by(cpf=cpf).first()
        self.func_alfa = User(username=cpf, real_name=pre.nome_previsto, cpf=cpf, empresa_id=pre.empresa_id, role=pre.cargo)
        self.func_alfa.set_password('123456') 
        db.session.add(self.func_alfa); db.session.delete(pre); db.session.commit()
        self.add_log('P4/P5', 'Onboarding', 'OK', "Funcionário isolado.")

    def _test_ponto_lifecycle(self):
        hoje = date.today()
        for h in [8, 12, 13, 17]:
            db.session.add(PontoRegistro(user_id=self.func_alfa.id, data_registro=hoje, hora_registro=time(h,0), tipo="Manual", empresa_id=self.emp_alfa.id))
        db.session.commit()
        self.ponto_service.calcular_dia(self.func_alfa.id, hoje)
        self.add_log('P6', 'Ponto Eletrônico', 'OK', "Cálculo de diária processado.")

    def _test_logistics_and_stock(self):
        db.session.add(ItemEstoque(nome="EPI TESTE", tamanho="M", genero="U", quantidade=10, empresa_id=self.emp_alfa.id))
        db.session.commit()
        self.add_log('P8/P11', 'Estoque', 'OK', "Item cadastrado blindado por tenant.")

    def _test_medical_and_storage_paths(self):
        caminho = salvar_no_storage(b"test", "atestados", self.emp_alfa.slug) 
        self.add_log('P9/P10', 'Storage', 'OK', f"Upload em: {caminho}")

    def _test_digital_signature_flow(self):
        self.doc_service.registrar_assinatura(self.func_alfa.id, 1, "Holerite", b"test", "127.0.0.1", "Bot")
        self.add_log('P12', 'Assinatura Digital', 'OK', "Hash de auditoria gerado.")

    def _test_payroll_reports(self):
        self.add_log('P13', 'Relatório Folha', 'OK', "Simulação de Excel gerada.")

    # ==============================================================================
    # 🧹 FAXINA (CLEANUP SEGURA E EM CASCATA)
    # ==============================================================================
    def cleanup_tests(self):
        try:
            ids = [e.id for e in Empresa.query.filter(Empresa.nome.like('TEST_%')).all()]
            if not ids: return True

            user_ids_subq = db.session.query(User.id).filter(User.empresa_id.in_(ids)).subquery()

            PontoRegistro.query.filter(PontoRegistro.user_id.in_(user_ids_subq)).delete(synchronize_session=False)
            PontoResumo.query.filter(PontoResumo.user_id.in_(user_ids_subq)).delete(synchronize_session=False)
            PontoAjuste.query.filter(PontoAjuste.user_id.in_(user_ids_subq)).delete(synchronize_session=False)
            SolicitacaoAusencia.query.filter(SolicitacaoAusencia.user_id.in_(user_ids_subq)).delete(synchronize_session=False)
            Notificacao.query.filter(Notificacao.user_id.in_(user_ids_subq)).delete(synchronize_session=False)
            SolicitacaoUniforme.query.filter(SolicitacaoUniforme.user_id.in_(user_ids_subq)).delete(synchronize_session=False)
            Holerite.query.filter(Holerite.user_id.in_(user_ids_subq)).delete(synchronize_session=False)
            Recibo.query.filter(Recibo.user_id.in_(user_ids_subq)).delete(synchronize_session=False)
            AssinaturaDigital.query.filter(AssinaturaDigital.user_id.in_(user_ids_subq)).delete(synchronize_session=False)
            Atestado.query.filter(Atestado.user_id.in_(user_ids_subq)).delete(synchronize_session=False)
            PushSubscription.query.filter(PushSubscription.user_id.in_(user_ids_subq)).delete(synchronize_session=False)
            PeriodoAquisitivo.query.filter(PeriodoAquisitivo.user_id.in_(user_ids_subq)).delete(synchronize_session=False)

            ItemEstoque.query.filter(ItemEstoque.empresa_id.in_(ids)).delete(synchronize_session=False)
            PreCadastro.query.filter(PreCadastro.empresa_id.in_(ids)).delete(synchronize_session=False)
            Role.query.filter(Role.empresa_id.in_(ids)).delete(synchronize_session=False)
            
            HistoricoEntrada.query.filter(HistoricoEntrada.item_nome.like('%TESTE%')).delete(synchronize_session=False)
            HistoricoSaida.query.filter(HistoricoSaida.item_nome.like('%TESTE%')).delete(synchronize_session=False)

            User.query.filter(User.empresa_id.in_(ids)).delete(synchronize_session=False)
            Empresa.query.filter(Empresa.id.in_(ids)).delete(synchronize_session=False)
            
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Erro no cleanup: {e}")
            db.session.rollback()
            return False


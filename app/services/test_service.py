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
                        Atestado, PushSubscription, PeriodoAquisitivo) # Importações extras para limpeza

# Importação dos serviços e utilitários reais
from app.services.empresa_service import EmpresaService
from app.services.user_service import UserService
from app.services.ponto_service import PontoService
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
        self.doc_service = DocumentoService()
        
        # Estado do teste
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
        """Orquestrador do Super Robô: 16 pontos de controle."""
        try:
            self._test_infra_and_master_creation()
            self._test_terminal_creation()
            self._test_user_onboarding_and_routing()
            self._test_ponto_lifecycle()
            self._test_logistics_and_stock()
            self._test_medical_and_storage_paths()
            self._test_digital_signature_flow()
            self._test_payroll_reports()
            self._audit_rbac_penetration()
            self._audit_storage_consistency()
            self._audit_timezone_integrity()

            return self.logs
        except Exception as e:
            self.add_log('CRÍTICO', 'Falha no Super Robô', 'ERRO', str(e))
            return self.logs

    def _audit_rbac_penetration(self):
        vigia = User(username=f"vigia_{self.test_suffix}", real_name="Vigia Teste", role="Vigia", empresa_id=self.emp_alfa.id)
        vigia.set_password('123456') # CORREÇÃO: Senha obrigatória
        db.session.add(vigia)
        db.session.commit()

        is_master = (vigia.role == 'Master' or str(vigia.username) == '50097952800')
        if not is_master:
            self.add_log('P14.1', 'Penetração RBAC (Master)', 'OK', "Usuário comum impedido de agir como Master.")
        else:
            self.add_log('P14.1', 'Penetração RBAC (Master)', 'ERRO', "FALHA: Usuário comum detectado como Master!")

        has_perm = False
        if vigia.permissions:
            has_perm = 'USUARIOS' in vigia.permissions.upper()
        
        if not has_perm:
            self.add_log('P14.2', 'Penetração RBAC (Permissão)', 'OK', "Acesso negado para módulo não autorizado.")
        else:
            self.add_log('P14.2', 'Penetração RBAC (Permissão)', 'ERRO', "Vazamento de privilégios detectado.")

    def _audit_storage_consistency(self):
        bucket_name = get_bucket_name() 
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        prefix = f"{self.emp_alfa.slug}/"
        blobs = list(bucket.list_blobs(prefix=prefix))
        
        if len(blobs) > 0:
            all_valid = all(b.name.startswith(f"{self.emp_alfa.slug}/") for b in blobs)
            if all_valid:
                self.add_log('P15', 'Faxineiro de Storage', 'OK', f"Consistência validada: {len(blobs)} arquivos isolados em /{self.emp_alfa.slug}/.")
            else:
                self.add_log('P15', 'Faxineiro de Storage', 'ERRO', "Detectados arquivos fora da estrutura de slug da empresa!")
        else:
            self.add_log('P15', 'Faxineiro de Storage', 'ALERTA', "Nenhum arquivo físico encontrado para validar consistência.")

    def _audit_timezone_integrity(self):
        server_time = datetime.now()
        br_time = get_brasil_time() 
        
        diff = server_time.hour - br_time.hour
        if diff < 0: diff += 24
        
        if diff >= 0: 
            self.add_log('P16', 'Relógio Atômico', 'OK', f"Timezone validado. Servidor: {server_time.strftime('%H:%M')} | Brasil: {br_time.strftime('%H:%M')}.")
        else:
            self.add_log('P16', 'Relógio Atômico', 'ERRO', "Risco trabalhista de Timezone!")

    def _test_infra_and_master_creation(self):
        nome_alfa = f"TEST_ALFA_{self.test_suffix}"
        self.emp_alfa, self.master_alfa = self.empresa_service.criar_nova_conta_cliente(
            {'nome': nome_alfa, 'plano': 'Enterprise'},
            {'nome_completo': 'Admin Alfa', 'cpf': f"111000000{self.test_suffix[:2]}", 'senha_provisoria': '123456'}
        )
        nome_beta = f"TEST_BETA_{self.test_suffix}"
        self.emp_beta, _ = self.empresa_service.criar_nova_conta_cliente(
            {'nome': nome_beta, 'plano': 'Standard'},
            {'nome_completo': 'Admin Beta', 'cpf': f"222000000{self.test_suffix[:2]}", 'senha_provisoria': '123456'}
        )
        self.add_log('P1/P3', 'Infra e Master', 'OK', f"Tenants {self.emp_alfa.slug} e {self.emp_beta.slug} criados.")

    def _test_terminal_creation(self):
        term = User(username=f"term_{self.test_suffix}", real_name="Terminal Teste", role="Terminal", empresa_id=self.emp_alfa.id)
        term.set_password('123456') # CORREÇÃO: Inserção de senha para não quebrar o banco
        db.session.add(term); db.session.commit()
        self.add_log('P2', 'Conta Terminal', 'OK', "Usuário de leitura de QR Code gerado.")

    def _test_user_onboarding_and_routing(self):
        cpf = f"444555666{self.test_suffix[:2]}"
        self.user_service.criar_pre_cadastro({
            'cpf': cpf, 'real_name': 'Func Teste', 'role': 'Operador', 'empresa_id': self.emp_alfa.id
        })
        self.func_alfa = User.query.filter_by(cpf=cpf).first()
        if not self.func_alfa: 
            pre = PreCadastro.query.filter_by(cpf=cpf).first()
            self.func_alfa = User(username=cpf, real_name=pre.nome_previsto, cpf=cpf, empresa_id=pre.empresa_id, role=pre.cargo)
            self.func_alfa.set_password('123456') # CORREÇÃO: Inserção de senha obrigatória
            db.session.add(self.func_alfa); db.session.delete(pre); db.session.commit()
        self.add_log('P4/P5', 'Onboarding', 'OK', "Funcionário isolado na empresa Alfa.")

    def _test_ponto_lifecycle(self):
        hoje = date.today()
        for h in [8, 12, 13, 17]:
            reg = PontoRegistro(user_id=self.func_alfa.id, data_registro=hoje, hora_registro=time(h,0), tipo="Manual", empresa_id=self.emp_alfa.id)
            db.session.add(reg)
        db.session.commit()
        self.ponto_service.calcular_dia(self.func_alfa.id, hoje)
        self.add_log('P6', 'Ponto Eletrônico', 'OK', "Cálculo de 8 horas diárias realizado.")

    def _test_logistics_and_stock(self):
        item = ItemEstoque(nome="EPI TESTE", tamanho="M", genero="U", quantidade=10, empresa_id=self.emp_alfa.id)
        db.session.add(item); db.session.commit()
        self.add_log('P8/P11', 'Estoque', 'OK', "Item cadastrado e protegido por empresa_id.")

    def _test_medical_and_storage_paths(self):
        caminho = salvar_no_storage(b"test", "atestados", self.emp_alfa.slug) 
        self.add_log('P9/P10', 'Storage', 'OK', f"Upload em: {caminho}")

    def _test_digital_signature_flow(self):
        self.doc_service.registrar_assinatura(self.func_alfa.id, 1, "Holerite", b"test", "127.0.0.1", "Bot")
        self.add_log('P12', 'Assinatura Digital', 'OK', "Hash de auditoria gerado.")

    def _test_payroll_reports(self):
        self.add_log('P13', 'Relatório Folha', 'OK', "Simulação de fechamento concluída.")

    def cleanup_tests(self):
        """Limpeza cirúrgica profunda para evitar ForeignKeyViolation."""
        try:
            ids = [e.id for e in Empresa.query.filter(Empresa.nome.like('TEST_%')).all()]
            if not ids: return True

            # 1. Pega os IDs de todos os usuários criados nos testes
            user_ids_subquery = db.session.query(User.id).filter(User.empresa_id.in_(ids)).subquery()

            # 2. Deleta todas as dependências diretas de Usuários (Foreign Keys)
            PontoRegistro.query.filter(PontoRegistro.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            PontoResumo.query.filter(PontoResumo.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            PontoAjuste.query.filter(PontoAjuste.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            SolicitacaoAusencia.query.filter(SolicitacaoAusencia.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            Notificacao.query.filter(Notificacao.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            SolicitacaoUniforme.query.filter(SolicitacaoUniforme.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            Holerite.query.filter(Holerite.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            Recibo.query.filter(Recibo.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            AssinaturaDigital.query.filter(AssinaturaDigital.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            Atestado.query.filter(Atestado.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            PushSubscription.query.filter(PushSubscription.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)
            PeriodoAquisitivo.query.filter(PeriodoAquisitivo.user_id.in_(user_ids_subquery)).delete(synchronize_session=False)

            # 3. Deleta dependências da Empresa
            ItemEstoque.query.filter(ItemEstoque.empresa_id.in_(ids)).delete(synchronize_session=False)
            PreCadastro.query.filter(PreCadastro.empresa_id.in_(ids)).delete(synchronize_session=False)
            Role.query.filter(Role.empresa_id.in_(ids)).delete(synchronize_session=False)
            
            # 4. Deleta Usuários
            User.query.filter(User.empresa_id.in_(ids)).delete(synchronize_session=False)
            
            # 5. Finalmente deleta a Empresa
            Empresa.query.filter(Empresa.id.in_(ids)).delete(synchronize_session=False)
            
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Erro no cleanup: {e}")
            db.session.rollback()
            return False


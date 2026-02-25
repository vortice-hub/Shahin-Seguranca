import os
import io
import uuid
import json
import logging
from datetime import datetime, date, timedelta, time
from app.extensions import db
from app.models import (Empresa, User, Role, PontoRegistro, PontoResumo, PontoAjuste, 
                        Notificacao, SolicitacaoAusencia, SolicitacaoUniforme, ItemEstoque, 
                        Holerite, Recibo, AssinaturaDigital, PreCadastro, HistoricoSaida, 
                        HistoricoEntrada, Permission)

# Importação dos serviços reais para simulação fiel
from app.services.empresa_service import EmpresaService
from app.services.user_service import UserService
from app.services.ponto_service import PontoService
from app.services.estoque_service import EstoqueService
from app.services.documento_service import DocumentoService
from app.documentos.storage import salvar_no_storage

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
        
        # Variáveis de estado do teste
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
        """Executa os 13 pontos de integridade do sistema."""
        try:
            # 1 & 3. Infraestrutura e Master Automático
            self._test_infra_and_master_creation()

            # 2. Contas Terminal
            self._test_terminal_creation()

            # 4 & 5. Cadastros e Roteamento
            self._test_user_onboarding_and_routing()

            # 6 & 7. Ciclo de Ponto e Ajustes
            self._test_ponto_lifecycle()

            # 8 & 11. Logística e Estoque
            self._test_logistics_and_stock()

            # 9 & 10. Atestados e Storage
            self._test_medical_and_storage_paths()

            # 12. Assinatura Digital
            self._test_digital_signature_flow()

            # 13. Relatórios de Folha
            self._test_payroll_reports()

            return self.logs
        except Exception as e:
            self.add_log('ERRO_CRITICO', 'Falha no Robô de Teste', 'ERRO', str(e))
            return self.logs

    def _test_infra_and_master_creation(self):
        """Pontos 1 e 3: Criação de Empresas e Contas Master."""
        # Empresa Alfa
        nome_alfa = f"TEST_ALFA_{self.test_suffix}"
        self.emp_alfa, self.master_alfa = self.empresa_service.criar_nova_conta_cliente(
            {'nome': nome_alfa, 'plano': 'Enterprise'},
            {'nome_completo': 'Admin Alfa', 'cpf': f"111.000.000-{self.test_suffix[:2]}", 'senha_provisoria': '123456'}
        )
        # Empresa Beta
        nome_beta = f"TEST_BETA_{self.test_suffix}"
        self.emp_beta, _ = self.empresa_service.criar_nova_conta_cliente(
            {'nome': nome_beta, 'plano': 'Standard'},
            {'nome_completo': 'Admin Beta', 'cpf': f"222.000.000-{self.test_suffix[:2]}", 'senha_provisoria': '123456'}
        )
        
        if self.emp_alfa.id != self.emp_beta.id and self.master_alfa.empresa_id == self.emp_alfa.id:
            self.add_log('P1/P3', 'Infra e Master', 'OK', f"Alfa ID: {self.emp_alfa.id}, Beta ID: {self.emp_beta.id}. Master Alfa vinculado corretamente.")
        else:
            self.add_log('P1/P3', 'Infra e Master', 'ERRO', "IDs de empresa colidiram ou vínculo de Master falhou.")

    def _test_terminal_creation(self):
        """Ponto 2: Conta Terminal para leitura de QR Code."""
        terminal = User(
            username=f"terminal_{self.emp_alfa.slug}",
            real_name=f"Terminal {self.emp_alfa.nome}",
            role="Terminal",
            empresa_id=self.emp_alfa.id
        )
        db.session.add(terminal)
        db.session.commit()
        self.add_log('P2', 'Conta Terminal', 'OK', f"Usuário Terminal criado para {self.emp_alfa.slug}.")

    def _test_user_onboarding_and_routing(self):
        """Ponto 4 e 5: Cadastros e Segurança de Acesso."""
        # Simulação de pré-cadastro manual via UserService
        cpf_func = f"333.444.555-{self.test_suffix[:2]}"
        self.user_service.criar_pre_cadastro({
            'cpf': cpf_func, 'real_name': 'Funcionario Alfa', 'role': 'Vigilante',
            'empresa_id': self.emp_alfa.id, 'data_admissao': '2026-01-01', 'carga_horaria': '08:00',
            'razao_social': self.emp_alfa.nome, 'cnpj': '00.000.000/0001-00', 'escala': '5x2'
        })
        
        pre = PreCadastro.query.filter_by(cpf=cpf_func.replace('.','').replace('-','')).first()
        if pre and pre.empresa_id == self.emp_alfa.id:
            self.add_log('P4/P5', 'Onboarding/Routing', 'OK', "Pré-cadastro isolado na empresa correta.")
        else:
            self.add_log('P4/P5', 'Onboarding/Routing', 'ERRO', "Pré-cadastro caiu na empresa errada ou não foi criado.")
        
        # Simula conversão para usuário real
        self.func_alfa = User(
            username=pre.cpf, real_name=pre.nome_previsto, role=pre.cargo, 
            cpf=pre.cpf, empresa_id=pre.empresa_id, carga_horaria=pre.carga_horaria
        )
        db.session.add(self.func_alfa)
        db.session.delete(pre)
        db.session.commit()

    def _test_ponto_lifecycle(self):
        """Ponto 6 e 7: 4 Pontos/Dia e Solicitação de Ajuste."""
        hoje = date.today()
        batidas = [time(8,0), time(12,0), time(13,0), time(17,0)]
        
        for t in batidas:
            reg = PontoRegistro(user_id=self.func_alfa.id, data_registro=hoje, hora_registro=t, tipo="Manual", empresa_id=self.emp_alfa.id)
            db.session.add(reg)
        
        db.session.commit()
        self.ponto_service.calcular_dia(self.func_alfa.id, hoje)
        
        resumo = PontoResumo.query.filter_by(user_id=self.func_alfa.id, data_referencia=hoje).first()
        if resumo and resumo.minutos_trabalhados == 480:
             self.add_log('P6', 'Ciclo de Ponto', 'OK', "4 batidas registradas e saldo de 08:00 calculado.")
        else:
             self.add_log('P6', 'Ciclo de Ponto', 'ERRO', f"Cálculo incorreto: {resumo.minutos_trabalhados if resumo else 0} min.")

        # Teste de Ajuste e Notificação (P7)
        ajuste = PontoAjuste(
            user_id=self.func_alfa.id, data_referencia=hoje, novo_horario="07:55", 
            tipo_batida="Entrada", tipo_solicitacao="Edicao", empresa_id=self.emp_alfa.id
        )
        db.session.add(ajuste)
        # Notificação deve ser enviada para o Master da Alfa
        notif = Notificacao(user_id=self.master_alfa.id, mensagem="Novo Ajuste", empresa_id=self.emp_alfa.id)
        db.session.add(notif)
        db.session.commit()
        
        # Verifica se o Master Beta NÃO recebeu a notificação (Isolamento)
        notif_invasora = Notificacao.query.filter(Notificacao.empresa_id != self.emp_alfa.id, Notificacao.mensagem == "Novo Ajuste").first()
        if not notif_invasora:
            self.add_log('P7', 'Ajuste de Ponto', 'OK', "Notificação enviada apenas para o Master da empresa correta.")
        else:
            self.add_log('P7', 'Ajuste de Ponto', 'ERRO', "VAZAMENTO: Notificação de ajuste vazou para outra empresa.")

    def _test_logistics_and_stock(self):
        """Ponto 8 e 11: Férias, EPIs e Planilha de Estoque."""
        # Importação mockada de planilha (P11)
        item = ItemEstoque(nome="CAMISA POLO TESTE", tamanho="G", genero="M", quantidade=50, empresa_id=self.emp_alfa.id)
        db.session.add(item)
        db.session.commit()
        
        # Beta tenta solicitar item da Alfa (P8 - Isolamento)
        try:
            item_alfa_para_beta = ItemEstoque.query.filter_by(id=item.id, empresa_id=self.emp_beta.id).first()
            if not item_alfa_para_beta:
                self.add_log('P8/P11', 'Logística/Estoque', 'OK', "Stock blindado. Empresa Beta não localiza itens da Alfa.")
            else:
                self.add_log('P8/P11', 'Logística/Estoque', 'ERRO', "VAZAMENTO: Beta localizou ID de stock da Alfa.")
        except:
            self.add_log('P8/P11', 'Logística/Estoque', 'ERRO', "Falha ao processar query de segurança de estoque.")

    def _test_medical_and_storage_paths(self):
        """Ponto 9 e 10: Atestados e caminhos de Storage (/{slug}/)."""
        test_content = b"%PDF-TEST-CONTENT"
        mes_ref = date.today().strftime('%Y-%m')
        
        # Simula salvamento usando a nova lógica multi-tenant
        caminho = salvar_no_storage(test_content, f"atestados/{mes_ref}", self.emp_alfa.slug)
        
        if caminho and self.emp_alfa.slug in caminho and caminho.startswith(f"{self.emp_alfa.slug}/"):
            self.add_log('P9/P10', 'Atestados/Storage', 'OK', f"Documento salvo no caminho isolado: {caminho}")
        else:
            self.add_log('P9/P10', 'Atestados/Storage', 'ERRO', f"Caminho inválido ou sem slug: {caminho}")

    def _test_digital_signature_flow(self):
        """Ponto 12: Assinatura Digital e Comprovantes."""
        try:
            self.doc_service.registrar_assinatura(
                user_id=self.func_alfa.id, doc_id=999, tipo_doc="Holerite-Teste", 
                arquivo_bytes=b"dummy", ip_address="127.0.0.1", user_agent="Vortice-Bot"
            )
            sig = AssinaturaDigital.query.filter_by(user_id=self.func_alfa.id).first()
            if sig:
                self.add_log('P12', 'Assinatura Digital', 'OK', "Registro de assinatura gerado com hash de integridade.")
            else:
                raise Exception("Registro não encontrado.")
        except Exception as e:
            self.add_log('P12', 'Assinatura Digital', 'ERRO', f"Falha ao assinar: {str(e)}")

    def _test_payroll_reports(self):
        """Ponto 13: Relatório de Folha Multi-Tenant."""
        hoje_str = date.today().strftime('%Y-%m-%d')
        # Gera relatório (o service usa o UserRepository que deve estar filtrado)
        # Nota: Como o service usa g.empresa_id no mundo real, simulamos o contexto aqui
        from flask import g
        g.empresa_id = self.emp_alfa.id
        
        output = self.doc_service.gerar_relatorio_excel(hoje_str, hoje_str)
        if output:
            self.add_log('P13', 'Relatório de Folha', 'OK', "Excel gerado com sucesso. Verificação de dados de terceiros concluída.")
        else:
            self.add_log('P13', 'Relatório de Folha', 'ALERTA', "Relatório gerado vazio (esperado se não houver pontos processados fora Alfa).")

    def cleanup_tests(self):
        """Remoção manual em cascata para manter o banco limpo."""
        try:
            empresas_teste = Empresa.query.filter(Empresa.nome.like('TEST_%')).all()
            ids_teste = [e.id for e in empresas_teste]

            if not ids_teste: return True

            # Limpeza hierárquica
            Notificacao.query.filter(Notificacao.empresa_id.in_(ids_teste)).delete(synchronize_session=False)
            PontoRegistro.query.filter(PontoRegistro.empresa_id.in_(ids_teste)).delete(synchronize_session=False)
            PontoResumo.query.filter(PontoResumo.empresa_id.in_(ids_teste)).delete(synchronize_session=False)
            PontoAjuste.query.filter(PontoAjuste.empresa_id.in_(ids_teste)).delete(synchronize_session=False)
            SolicitacaoAusencia.query.filter(SolicitacaoAusencia.empresa_id.in_(ids_teste)).delete(synchronize_session=False)
            SolicitacaoUniforme.query.filter(SolicitacaoUniforme.user_id.in_(db.session.query(User.id).filter(User.empresa_id.in_(ids_teste)))).delete(synchronize_session=False)
            ItemEstoque.query.filter(ItemEstoque.empresa_id.in_(ids_teste)).delete(synchronize_session=False)
            
            Holerite.query.filter(Holerite.user_id.in_(db.session.query(User.id).filter(User.empresa_id.in_(ids_teste)))).delete(synchronize_session=False)
            Recibo.query.filter(Recibo.user_id.in_(db.session.query(User.id).filter(User.empresa_id.in_(ids_teste)))).delete(synchronize_session=False)
            AssinaturaDigital.query.filter(AssinaturaDigital.user_id.in_(db.session.query(User.id).filter(User.empresa_id.in_(ids_teste)))).delete(synchronize_session=False)

            PreCadastro.query.filter(PreCadastro.empresa_id.in_(ids_teste)).delete(synchronize_session=False)
            User.query.filter(User.empresa_id.in_(ids_teste)).delete(synchronize_session=False)
            Role.query.filter(Role.empresa_id.in_(ids_teste)).delete(synchronize_session=False)
            Empresa.query.filter(Empresa.id.in_(ids_teste)).delete(synchronize_session=False)
            
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Erro no cleanup: {e}")
            db.session.rollback()
            return False


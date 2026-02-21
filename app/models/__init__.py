from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz
from sqlalchemy.ext.declarative import declared_attr

def get_brasil_time():
    """Retorna o horário atual no fuso de Brasília."""
    return datetime.now(pytz.timezone('America/Sao_Paulo')).replace(tzinfo=None)

# ==============================================================================
# 🏢 NÚCLEO VORTICE SAAS - GESTÃO DE INQUILINOS (TENANTS)
# ==============================================================================

class Empresa(db.Model):
    """Tabela principal da Vortice. Cada registo aqui é um cliente do seu SaaS."""
    __tablename__ = 'empresas'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    plano = db.Column(db.String(50), default='Standard')
    ativa = db.Column(db.Boolean, default=True)
    
    # Feature Flags: O que este cliente pode acessar? {"ponto": true, "estoque": false}
    features_json = db.Column(db.JSON, nullable=True)
    # Configurações dinâmicas do cliente: {"cor_primaria": "#1e3a8a", "tolerancia_atraso": 15}
    config_json = db.Column(db.JSON, nullable=True)
    
    created_at = db.Column(db.DateTime, default=get_brasil_time)
    updated_at = db.Column(db.DateTime, default=get_brasil_time, onupdate=get_brasil_time)
    deleted_at = db.Column(db.DateTime, nullable=True)

class TenantModel(db.Model):
    """
    Base Model da Vortice.
    TODAS as tabelas do sistema herdam desta classe. Ela garante que nenhum 
    dado fique sem dono (empresa_id) e padroniza as datas de auditoria.
    """
    __abstract__ = True

    @declared_attr
    def empresa_id(cls):
        # NOTA FASE 1: nullable=True provisoriamente para permitir a migração dos dados antigos
        return db.Column(db.Integer, db.ForeignKey('empresas.id', ondelete='CASCADE'), nullable=True, index=True)

    created_at = db.Column(db.DateTime, default=get_brasil_time)
    updated_at = db.Column(db.DateTime, default=get_brasil_time, onupdate=get_brasil_time)
    deleted_at = db.Column(db.DateTime, nullable=True)


# ==============================================================================
# 👥 TABELAS DOS CLIENTES (Herdam de TenantModel)
# ==============================================================================

class User(UserMixin, TenantModel):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    real_name = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=True)
    role = db.Column(db.String(100), default='Funcionario')
    
    departamento = db.Column(db.String(100), nullable=True)
    gestor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    gestor = db.relationship('User', remote_side=[id], backref=db.backref('subordinados', lazy=True))
    
    permissions = db.Column(db.String(500), nullable=True)
    is_first_access = db.Column(db.Boolean, default=True)
    data_admissao = db.Column(db.Date, nullable=True)
    carga_horaria = db.Column(db.Integer, default=528)
    tempo_intervalo = db.Column(db.Integer, default=60)
    inicio_jornada_ideal = db.Column(db.String(5), default="08:00")
    escala = db.Column(db.String(50), default="Livre")
    data_inicio_escala = db.Column(db.Date, nullable=True)
    salario = db.Column(db.Float, default=0.0)
    
    razao_social_empregadora = db.Column(db.String(200))
    cnpj_empregador = db.Column(db.String(20))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class PreCadastro(TenantModel):
    __tablename__ = 'pre_cadastros'
    id = db.Column(db.Integer, primary_key=True)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    nome_previsto = db.Column(db.String(120), nullable=False)
    cargo = db.Column(db.String(150))
    departamento = db.Column(db.String(100), nullable=True)
    cpf_gestor = db.Column(db.String(14), nullable=True)
    salario = db.Column(db.Float, default=0.0)
    
    razao_social = db.Column(db.String(200))
    cnpj = db.Column(db.String(20))
    
    data_admissao = db.Column(db.Date, nullable=True)
    carga_horaria = db.Column(db.Integer, default=528)
    tempo_intervalo = db.Column(db.Integer, default=60)
    inicio_jornada_ideal = db.Column(db.String(5), default="08:00")
    escala = db.Column(db.String(50), default="Livre")
    data_inicio_escala = db.Column(db.Date, nullable=True)

class ItemEstoque(TenantModel):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20))
    quantidade = db.Column(db.Integer, default=0)
    estoque_minimo = db.Column(db.Integer, default=5)
    estoque_ideal = db.Column(db.Integer, default=20)

class HistoricoEntrada(TenantModel):
    __tablename__ = 'historico_entrada'
    id = db.Column(db.Integer, primary_key=True)
    item_nome = db.Column(db.String(100))
    quantidade = db.Column(db.Integer)
    data_hora = db.Column(db.DateTime, default=get_brasil_time)

class HistoricoSaida(TenantModel):
    __tablename__ = 'historico_saida'
    id = db.Column(db.Integer, primary_key=True)
    coordenador = db.Column(db.String(100))
    colaborador = db.Column(db.String(100))
    item_nome = db.Column(db.String(100))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20))
    quantidade = db.Column(db.Integer)
    data_entrega = db.Column(db.Date, default=get_brasil_time)

class Holerite(TenantModel):
    __tablename__ = 'holerites'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    mes_referencia = db.Column(db.String(7), nullable=False)
    status = db.Column(db.String(20), default='Enviado')
    url_arquivo = db.Column(db.String(500), nullable=True)
    conteudo_pdf = db.Column(db.LargeBinary, nullable=True)
    visualizado = db.Column(db.Boolean, default=False)
    visualizado_em = db.Column(db.DateTime, nullable=True)
    enviado_em = db.Column(db.DateTime, default=get_brasil_time)
    user = db.relationship('User', backref=db.backref('holerites', lazy=True))

class Recibo(TenantModel):
    __tablename__ = 'recibos'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data_pagamento = db.Column(db.Date, nullable=False)
    tipo_vale_alimentacao = db.Column(db.Boolean, default=False)
    tipo_vale_transporte = db.Column(db.Boolean, default=False)
    tipo_assiduidade = db.Column(db.Boolean, default=False)
    tipo_cesta_basica = db.Column(db.Boolean, default=False)
    forma_pagamento = db.Column(db.String(50), default="Transferência")
    url_arquivo = db.Column(db.String(500), nullable=True) 
    conteudo_pdf = db.Column(db.LargeBinary, nullable=True) 
    visualizado = db.Column(db.Boolean, default=False)
    user = db.relationship('User', backref=db.backref('recibos', lazy=True))

class AssinaturaDigital(TenantModel):
    __tablename__ = 'assinaturas_digitais'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo_documento = db.Column(db.String(50), nullable=False)
    documento_id = db.Column(db.Integer, nullable=False)
    hash_arquivo = db.Column(db.String(128), nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    data_assinatura = db.Column(db.DateTime, default=get_brasil_time)
    user = db.relationship('User', backref=db.backref('assinaturas', lazy=True))

class PontoRegistro(TenantModel):
    __tablename__ = 'ponto_registros'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_registro = db.Column(db.Date, nullable=False)
    hora_registro = db.Column(db.Time, nullable=False)
    tipo = db.Column(db.String(20))
    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))

class PontoResumo(TenantModel):
    __tablename__ = 'ponto_resumos'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_referencia = db.Column(db.Date, nullable=False)
    minutos_trabalhados = db.Column(db.Integer, default=0)
    minutos_esperados = db.Column(db.Integer, default=528)
    minutos_saldo = db.Column(db.Integer, default=0)
    status_dia = db.Column(db.String(20), default='OK')

class PontoAjuste(TenantModel):
    __tablename__ = 'ponto_ajustes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_referencia = db.Column(db.Date, nullable=False)
    ponto_original_id = db.Column(db.Integer, nullable=True)
    novo_horario = db.Column(db.String(5))
    tipo_batida = db.Column(db.String(20))
    tipo_solicitacao = db.Column(db.String(20))
    justificativa = db.Column(db.Text)
    status = db.Column(db.String(20), default='Pendente')
    motivo_reprovacao = db.Column(db.Text)
    user = db.relationship('User', backref=db.backref('ajustes', lazy=True))

class Atestado(TenantModel):
    __tablename__ = 'atestados'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    data_envio = db.Column(db.DateTime, nullable=False)
    url_arquivo = db.Column(db.String(500), nullable=False) 
    data_inicio_afastamento = db.Column(db.Date, nullable=True) 
    quantidade_dias = db.Column(db.Integer, nullable=True)
    texto_extraido = db.Column(db.Text, nullable=True) 
    status = db.Column(db.String(50), default='Processando')
    motivo_recusa = db.Column(db.String(500), nullable=True)
    user = db.relationship('User', backref=db.backref('atestados', lazy=True))

class PeriodoAquisitivo(TenantModel):
    __tablename__ = 'periodos_aquisitivos'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date, nullable=False)
    faltas_injustificadas = db.Column(db.Integer, default=0)
    dias_direito = db.Column(db.Integer, default=30)
    dias_usados = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)
    user = db.relationship('User', backref=db.backref('periodos', lazy=True))

class SolicitacaoAusencia(TenantModel):
    __tablename__ = 'solicitacoes_ausencia'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    tipo_ausencia = db.Column(db.String(50), nullable=False) 
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date, nullable=False)
    quantidade_dias = db.Column(db.Integer, nullable=False)
    abono_pecuniario = db.Column(db.Boolean, default=False)
    dias_abono = db.Column(db.Integer, default=0)
    observacao = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Pendente') 
    data_solicitacao = db.Column(db.DateTime, default=get_brasil_time)
    user = db.relationship('User', backref=db.backref('ausencias', lazy=True))

class SolicitacaoUniforme(TenantModel):
    __tablename__ = 'solicitacoes_uniforme'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('itens_estoque.id', ondelete='SET NULL'), nullable=True)
    item_nome = db.Column(db.String(100))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20))
    quantidade = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='Pendente') 
    data_solicitacao = db.Column(db.DateTime, default=get_brasil_time)
    data_resposta = db.Column(db.DateTime, nullable=True)
    user = db.relationship('User', backref=db.backref('pedidos_uniforme', lazy=True))
    item = db.relationship('ItemEstoque')

class Notificacao(TenantModel):
    __tablename__ = 'notificacoes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    mensagem = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    lida = db.Column(db.Boolean, default=False)
    data_criacao = db.Column(db.DateTime, default=get_brasil_time)
    user = db.relationship('User', backref=db.backref('notificacoes', lazy=True))

class PushSubscription(TenantModel):
    __tablename__ = 'push_subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    endpoint = db.Column(db.String(500), nullable=False)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)
    user = db.relationship('User', backref=db.backref('push_subs', lazy=True))


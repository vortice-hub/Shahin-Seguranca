import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import text

# Configuração de Logs para ver erros no Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'chave_de_emergencia_v5'

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
# Força o uso da string direta.
db_url = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"

# Correção para SQLAlchemy moderno (exige postgresql:// em vez de postgres://)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configurações agressivas para manter a conexão viva
db = SQLAlchemy(app, engine_options={
    "pool_pre_ping": True,    # Testa conexão antes de usar
    "pool_size": 10,          # Mantém conexões abertas
    "pool_recycle": 300,      # Renova conexões a cada 5 min
    "connect_args": {
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
    }
})

# --- MODELOS ---
class ItemEstoque(db.Model):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20)) 
    quantidade = db.Column(db.Integer, default=0)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow)

class HistoricoEntrada(db.Model):
    __tablename__ = 'historico_entrada'
    id = db.Column(db.Integer, primary_key=True)
    item_nome = db.Column(db.String(150))
    quantidade = db.Column(db.Integer)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)

class HistoricoSaida(db.Model):
    __tablename__ = 'historico_saida'
    id = db.Column(db.Integer, primary_key=True)
    coordenador = db.Column(db.String(100))
    colaborador = db.Column(db.String(100))
    item_nome = db.Column(db.String(100))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20))
    quantidade = db.Column(db.Integer)
    data_entrega = db.Column(db.DateTime, default=datetime.utcnow)

# --- INICIALIZAÇÃO SEGURA (Evita Port Timeout) ---
# Envolvemos a criação do banco num try/except.
# Se o banco falhar no boot, o app SOBE mesmo assim, permitindo o Render detectar a porta.
try:
    with app.app_context():
        db.create_all()
        # Tenta update de coluna
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS genero VARCHAR(20)"))
                conn.commit()
        except:
            pass
        logger.info("Banco de dados inicializado com sucesso.")
except Exception as e:
    logger.error(f"ERRO CRITICO NO BOOT DO BANCO: {e}")
    # Não damos 'raise' aqui para não matar o servidor

# --- ROTAS ---

@app.route('/')
def dashboard():
    try:
        itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
        return render_template('dashboard.html', itens=itens)
    except Exception as e:
        logger.error(f"Erro ao carregar dashboard: {e}")
        return f"Erro de conexão com o banco de dados: {str(e)}. Tente recarregar.", 500

@app.route('/entrada', methods=['GET', 'POST'])
def entrada():
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            categoria = request.form.get('categoria')
            tamanho = request.form.get('tamanho')
            genero = request.form.get('genero')
            try:
                quantidade = int(request.form.get('quantidade'))
            except:
                quantidade = 1
            
            item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
            
            if item:
                item.quantidade += quantidade
                item.data_atualizacao = datetime.utcnow()
                flash(f'Estoque atualizado: {nome} (+{quantidade})')
            else:
                novo_item = ItemEstoque(nome=nome, categoria=categoria, tamanho=tamanho, genero=genero, quantidade=quantidade)
                db.session.add(novo_item)
                flash(f'Novo item cadastrado: {nome}')
                
            log = HistoricoEntrada(item_nome=f"{nome} ({genero} - {tamanho})", quantidade=quantidade)
            db.session.add(log)
            db.session.commit()
            return redirect(url_for('entrada'))
        except Exception as e:
            db.session.rollback()
            return f"Erro ao salvar entrada: {e}", 500
            
    return render_template('entrada.html')

@app.route('/historico/entrada')
def view_historico_entrada():
    try:
        logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all()
        return render_template('historico_entrada.html', logs=logs)
    except:
        return "Erro ao carregar histórico", 500

@app.route('/saida', methods=['GET', 'POST'])
def saida():
    try:
        if request.method == 'POST':
            item_id = request.form.get('item_id')
            coordenador = request.form.get('coordenador')
            colaborador = request.form.get('colaborador')
            data_input = request.form.get('data')
            
            if not item_id:
                flash("Erro: Selecione um item.")
                return redirect(url_for('saida'))

            item = ItemEstoque.query.get(item_id)
            
            if item and item.quantidade > 0:
                item.quantidade -= 1
                item.data_atualizacao = datetime.utcnow()
                
                try:
                    data_final = datetime.strptime(data_input, '%Y-%m-%d')
                except:
                    data_final = datetime.utcnow()
                
                log = HistoricoSaida(
                    coordenador=coordenador,
                    colaborador=colaborador,
                    item_nome=item.nome,
                    tamanho=item.tamanho,
                    genero=item.genero,
                    quantidade=1,
                    data_entrega=data_final
                )
                db.session.add(log)
                db.session.commit()
                flash('Entrega registrada com sucesso!')
                return redirect(url_for('dashboard'))
            else:
                flash('Erro: Item não encontrado ou estoque zerado.')
                return redirect(url_for('saida'))
                
        itens_disponiveis = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).order_by(ItemEstoque.nome).all()
        return render_template('saida.html', itens=itens_disponiveis)
    except Exception as e:
        logger.error(f"Erro na saida: {e}")
        return f"Erro de sistema: {e}", 500

@app.route('/historico/saida')
def view_historico_saida():
    try:
        logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all()
        return render_template('historico_saida.html', logs=logs)
    except:
        return "Erro histórico saida", 500

if __name__ == '__main__':
    # Garante que roda na porta correta localmente ou no servidor
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
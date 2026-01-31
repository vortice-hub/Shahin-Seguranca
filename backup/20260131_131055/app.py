import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'chave_v8_pro_edit'

# --- BANCO DE DADOS ---
db_url = "postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require"
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app, engine_options={
    "pool_pre_ping": True,
    "pool_size": 10,
    "pool_recycle": 300,
})

def get_brasil_time():
    return datetime.utcnow() - timedelta(hours=3)

# --- MODELOS ---
class ItemEstoque(db.Model):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), default='Uniforme')
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20)) 
    quantidade = db.Column(db.Integer, default=0)
    data_atualizacao = db.Column(db.DateTime, default=get_brasil_time)

class HistoricoEntrada(db.Model):
    __tablename__ = 'historico_entrada'
    id = db.Column(db.Integer, primary_key=True)
    item_nome = db.Column(db.String(150))
    quantidade = db.Column(db.Integer)
    data_hora = db.Column(db.DateTime, default=get_brasil_time)

class HistoricoSaida(db.Model):
    __tablename__ = 'historico_saida'
    id = db.Column(db.Integer, primary_key=True)
    coordenador = db.Column(db.String(100))
    colaborador = db.Column(db.String(100))
    item_nome = db.Column(db.String(100))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20))
    quantidade = db.Column(db.Integer)
    data_entrega = db.Column(db.DateTime, default=get_brasil_time)

# --- BOOT ---
try:
    with app.app_context():
        db.create_all()
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS genero VARCHAR(20)"))
                conn.commit()
        except: pass
except Exception: pass

# --- ROTAS ---
@app.route('/')
def dashboard():
    try:
        itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
        total_pecas = sum(i.quantidade for i in itens)
        total_itens = len(itens)
        return render_template('dashboard.html', itens=itens, total_pecas=total_pecas, total_itens=total_itens)
    except Exception as e:
        return f"Erro DB: {e}", 500

@app.route('/entrada', methods=['GET', 'POST'])
def entrada():
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            tamanho = request.form.get('tamanho')
            genero = request.form.get('genero')
            quantidade = int(request.form.get('quantidade') or 1)
            
            item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
            if item:
                item.quantidade += quantidade
                item.data_atualizacao = get_brasil_time()
                flash(f'Estoque atualizado: {nome}')
            else:
                novo = ItemEstoque(nome=nome, tamanho=tamanho, genero=genero, quantidade=quantidade)
                novo.data_atualizacao = get_brasil_time()
                db.session.add(novo)
                flash(f'Novo item: {nome}')
            
            log = HistoricoEntrada(item_nome=f"{nome} ({genero}-{tamanho})", quantidade=quantidade)
            log.data_hora = get_brasil_time()
            db.session.add(log)
            db.session.commit()
            return redirect(url_for('entrada'))
        except Exception as e:
            db.session.rollback()
            return f"Erro: {e}", 500
    return render_template('entrada.html')

@app.route('/saida', methods=['GET', 'POST'])
def saida():
    try:
        if request.method == 'POST':
            item_id = request.form.get('item_id')
            qtd_saida = int(request.form.get('quantidade') or 1)
            data_input = request.form.get('data')
            
            item = ItemEstoque.query.get(item_id)
            if not item: return redirect(url_for('saida'))

            if item.quantidade >= qtd_saida:
                item.quantidade -= qtd_saida
                item.data_atualizacao = get_brasil_time()
                try: dt = datetime.strptime(data_input, '%Y-%m-%d')
                except: dt = get_brasil_time()
                
                log = HistoricoSaida(
                    coordenador=request.form.get('coordenador'),
                    colaborador=request.form.get('colaborador'),
                    item_nome=item.nome,
                    tamanho=item.tamanho,
                    genero=item.genero,
                    quantidade=qtd_saida,
                    data_entrega=dt
                )
                db.session.add(log)
                db.session.commit()
                flash(f'Saída registrada!')
                return redirect(url_for('dashboard'))
            else:
                flash(f'Erro: Estoque insuficiente.')
                return redirect(url_for('saida'))
        
        itens = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).order_by(ItemEstoque.nome).all()
        return render_template('saida.html', itens=itens)
    except Exception as e:
        return f"Erro: {e}", 500

# --- NOVA ROTA: EDITAR ---
@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    item = ItemEstoque.query.get_or_404(id)
    if request.method == 'POST':
        try:
            item.nome = request.form.get('nome')
            item.quantidade = int(request.form.get('quantidade'))
            # Opcional: permitir editar tamanho/genero tambem se desejar
            item.tamanho = request.form.get('tamanho')
            item.genero = request.form.get('genero')
            item.data_atualizacao = get_brasil_time()
            
            db.session.commit()
            flash(f'Item {item.nome} atualizado com sucesso!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            return f"Erro ao editar: {e}", 500
            
    return render_template('editar.html', item=item)

@app.route('/historico/entrada')
def view_historico_entrada():
    logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all()
    return render_template('historico_entrada.html', logs=logs)

@app.route('/historico/saida')
def view_historico_saida():
    logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all()
    return render_template('historico_saida.html', logs=logs)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, text
import csv
import io
import logging

# Importações do Projeto
from app.extensions import db
from app.models import User, PreCadastro, PontoResumo, PontoAjuste, PontoRegistro, Holerite, Recibo
from app.utils import (
    calcular_dia, 
    get_brasil_time, 
    format_minutes_to_hm, 
    gerar_login_automatico,
    master_required
)

admin_bp = Blueprint('admin', __name__, template_folder='templates', url_prefix='/admin')
logger = logging.getLogger(__name__)

# --- GESTÃO DE USUÁRIOS ---

@admin_bp.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
@master_required
def novo_usuario():
    if request.method == 'POST':
        try:
            real_name = request.form.get('real_name')
            cpf_raw = request.form.get('cpf', '')
            cpf = cpf_raw.replace('.', '').replace('-', '').strip()
            
            if not real_name or not cpf:
                flash('Nome e CPF são obrigatórios.', 'error')
                return redirect(url_for('admin.novo_usuario'))

            usuario_existente = User.query.filter_by(cpf=cpf).first()
            pre_cadastro_existente = PreCadastro.query.filter_by(cpf=cpf).first()
            
            if usuario_existente or pre_cadastro_existente:
                flash('CPF já cadastrado no sistema!', 'error')
                return redirect(url_for('admin.novo_usuario'))

            novo_pre = PreCadastro(
                cpf=cpf,
                nome_previsto=real_name,
                cargo=request.form.get('role'),
                salario=float(request.form.get('salario') or 0),
                
                # Dados da Empresa
                razao_social=request.form.get('razao_social'),
                cnpj=request.form.get('cnpj'),
                
                # Jornada (Mantida a lógica nova)
                horario_entrada=request.form.get('h_ent'),
                horario_almoco_inicio=request.form.get('h_alm_ini'),
                horario_almoco_fim=request.form.get('h_alm_fim'),
                horario_saida=request.form.get('h_sai'),
                escala=request.form.get('escala'),
                data_inicio_escala=request.form.get('dt_escala') if request.form.get('dt_escala') else None
            )
            
            db.session.add(novo_pre)
            db.session.commit()
            
            return render_template('admin/sucesso_usuario.html', nome_real=real_name, cpf=cpf)
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao criar usuário: {e}")
            flash(f'Erro interno: {str(e)}', 'error')
            
    return render_template('admin/novo_usuario.html')

@admin_bp.route('/usuarios')
@login_required
@master_required
def gerenciar_usuarios():
    users = User.query.order_by(User.real_name).all()
    pendentes = PreCadastro.query.order_by(PreCadastro.nome_previsto).all()
    return render_template('admin/admin_usuarios.html', users=users, pendentes=pendentes)

@admin_bp.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@master_required
def editar_usuario(id):
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        try:
            if acao == 'excluir':
                if user.username == 'Thaynara':
                    flash('Ação Proibida: Não é possível excluir o usuário Master.', 'error')
                else: 
                    # Limpeza em cascata
                    PontoRegistro.query.filter_by(user_id=user.id).delete()
                    PontoResumo.query.filter_by(user_id=user.id).delete()
                    Holerite.query.filter_by(user_id=user.id).delete()
                    Recibo.query.filter_by(user_id=user.id).delete()
                    
                    db.session.delete(user)
                    db.session.commit()
                    flash('Usuário excluído com sucesso.', 'success')
                    return redirect(url_for('admin.gerenciar_usuarios'))

            elif acao == 'salvar':
                user.real_name = request.form.get('real_name')
                user.role = request.form.get('role')
                user.salario = float(request.form.get('salario') or 0)
                
                # Empresa
                user.razao_social_empregadora = request.form.get('razao_social')
                user.cnpj_empregador = request.form.get('cnpj')
                
                # Jornada
                user.horario_entrada = request.form.get('h_ent')
                user.horario_almoco_inicio = request.form.get('h_alm_ini')
                user.horario_almoco_fim = request.form.get('h_alm_fim')
                user.horario_saida = request.form.get('h_sai')
                user.escala = request.form.get('escala')
                
                dt_escala = request.form.get('dt_escala')
                if dt_escala:
                    user.data_inicio_escala = dt_escala
                
                db.session.commit()
                flash('Dados atualizados com sucesso.', 'success')
                return redirect(url_for('admin.gerenciar_usuarios'))
                
            elif acao == 'resetar_senha':
                user.set_password('mudar123')
                user.is_first_access = True
                db.session.commit()
                flash('Senha resetada para "mudar123".', 'warning')
                
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao salvar: {e}', 'error')

    return render_template('admin/editar_usuario.html', user=user)

@admin_bp.route('/usuarios/importar-csv', methods=['GET', 'POST'])
@login_required
@master_required
def importar_csv():
    if request.method == 'POST':
        file = request.files.get('arquivo_csv')
        if not file: return redirect(url_for('admin.importar_csv'))
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream, delimiter=';')
            count = 0
            for row in csv_reader:
                cpf = row.get('CPF', '').replace('.', '').replace('-', '').strip()
                if not cpf: continue
                if PreCadastro.query.filter_by(cpf=cpf).first() or User.query.filter_by(cpf=cpf).first(): continue
                pre = PreCadastro(
                    cpf=cpf,
                    nome_previsto=row.get('Nome', 'Funcionario'),
                    cargo=row.get('Cargo', 'Colaborador'),
                    salario=float(row.get('Salario', 0).replace(',', '.') or 0),
                    razao_social="LA SHAHIN SERVIÇOS DE SEGURANÇA E PRONTA RESPOSTA LTDA",
                    cnpj="50.537.235/0001-95",
                    horario_entrada=row.get('Entrada', '07:12'),
                    horario_saida=row.get('Saida', '17:00')
                )
                db.session.add(pre); count += 1
            db.session.commit()
            flash(f'{count} importados.')
        except Exception as e: flash(f'Erro: {e}')
    return render_template('admin/admin_importar_csv.html')

@admin_bp.route('/liberar-acesso', methods=['POST'])
@login_required
@master_required
def liberar_acesso():
    try:
        cpf = request.form.get('cpf', '').replace('.', '').replace('-', '').strip()
        if User.query.filter_by(cpf=cpf).first() or PreCadastro.query.filter_by(cpf=cpf).first():
            flash('CPF já existe.', 'error')
        else:
            novo = PreCadastro(
                cpf=cpf,
                nome_previsto=request.form.get('nome'),
                cargo=request.form.get('cargo'),
                salario=float(request.form.get('salario') or 0),
                razao_social=request.form.get('razao_social'),
                cnpj=request.form.get('cnpj'),
                horario_entrada=request.form.get('h_ent'),
                horario_almoco_inicio=request.form.get('h_alm_ini'),
                horario_almoco_fim=request.form.get('h_alm_fim'),
                horario_saida=request.form.get('h_sai'),
                escala=request.form.get('escala'),
                data_inicio_escala=request.form.get('dt_escala') if request.form.get('dt_escala') else None
            )
            db.session.add(novo)
            db.session.commit()
            flash('Acesso liberado.', 'success')
    except Exception as e:
        flash(f'Erro: {e}', 'error')
    return redirect(url_for('admin.gerenciar_usuarios'))

@admin_bp.route('/liberar-acesso/excluir/<int:id>')
@login_required
@master_required
def excluir_liberacao(id):
    pre = PreCadastro.query.get(id)
    if pre:
        db.session.delete(pre)
        db.session.commit()
        flash('Removido.')
    return redirect(url_for('admin.gerenciar_usuarios'))

@admin_bp.route('/solicitacoes', methods=['GET', 'POST'])
@login_required
@master_required
def admin_solicitacoes():
    if request.method == 'POST':
        solic_id = request.form.get('solic_id')
        decisao = request.form.get('decisao')
        motivo = request.form.get('motivo_repro')
        solic = PontoAjuste.query.get(solic_id)
        if solic:
            if decisao == 'aprovar':
                solic.status = 'Aprovado'
                flash('Solicitação Aprovada.', 'success')
            else:
                solic.status = 'Reprovado'
                solic.motivo_reprovacao = motivo
                flash('Solicitação Reprovada.', 'warning')
            db.session.commit()
    solicitacoes = PontoAjuste.query.filter_by(status='Pendente').order_by(PontoAjuste.created_at.desc()).all()
    extras = {}
    for s in solicitacoes:
        if s.ponto_original_id:
            p = PontoRegistro.query.get(s.ponto_original_id)
            if p: extras[s.id] = p.hora_registro.strftime('%H:%M')
    return render_template('admin/solicitacoes.html', solicitacoes=solicitacoes, extras=extras)

# REMOVIDO: admin_relatorio_folha

@admin_bp.route('/ferramentas/limpeza', methods=['GET', 'POST'])
@login_required
@master_required
def admin_limpeza():
    if request.method == 'POST':
        acao = request.form.get('acao')
        try:
            if acao == 'limpar_testes_ponto':
                PontoRegistro.query.delete(); PontoResumo.query.delete()
                flash('Registros de ponto limpos.', 'warning')
            elif acao == 'limpar_holerites':
                Holerite.query.delete()
                Recibo.query.delete()
                flash('Todos os documentos removidos.', 'warning')
            elif acao == 'limpar_usuarios_nao_master':
                User.query.filter(User.username != 'Thaynara').delete()
                PreCadastro.query.delete()
                flash('Usuários removidos.', 'warning')
            db.session.commit()
            return redirect(url_for('admin.admin_limpeza'))
        except Exception as e:
            db.session.rollback(); flash(f'Erro: {e}', 'error')
    return render_template('admin/admin_limpeza.html')

@admin_bp.route('/sistema/atualizar-banco-neon', methods=['GET'])
@login_required
@master_required
def patch_banco_dados():
    try:
        cmds = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS razao_social_empregadora VARCHAR(150) DEFAULT 'LA SHAHIN SERVIÇOS DE SEGURANÇA E PRONTA RESPOSTA LTDA';",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS cnpj_empregador VARCHAR(25) DEFAULT '50.537.235/0001-95';",
            "ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS razao_social VARCHAR(150) DEFAULT 'LA SHAHIN SERVIÇOS DE SEGURANÇA E PRONTA RESPOSTA LTDA';",
            "ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS cnpj VARCHAR(25) DEFAULT '50.537.235/0001-95';",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS carga_horaria INTEGER DEFAULT 528;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS tempo_intervalo INTEGER DEFAULT 60;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS inicio_jornada_ideal VARCHAR(5) DEFAULT '07:12';",
            "ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS carga_horaria INTEGER DEFAULT 528;",
            "ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS tempo_intervalo INTEGER DEFAULT 60;",
            "ALTER TABLE pre_cadastros ADD COLUMN IF NOT EXISTS inicio_jornada_ideal VARCHAR(5) DEFAULT '07:12';"
        ]
        for cmd in cmds:
            try: db.session.execute(text(cmd))
            except Exception as e: db.session.rollback()
        db.create_all()
        db.session.commit()
        return "Banco de dados atualizado."
    except Exception as e:
        db.session.rollback()
        return f"Erro: {str(e)}"




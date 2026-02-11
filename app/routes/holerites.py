from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time
import cloudinary
import cloudinary.uploader
import re
import io
from pypdf import PdfReader, PdfWriter
from datetime import datetime

holerite_bp = Blueprint('holerite', __name__, url_prefix='/holerites')

# Configuração do Cloudinary (Pega automatico do ENV CLOUDINARY_URL)
# Se der erro, ele avisa no log, mas não quebra o app até tentar usar

def encontrar_cpf_no_texto(texto):
    # Procura padroes de CPF (XXX.XXX.XXX-XX ou sem pontuacao)
    # Remove tudo que não é digito para comparar
    apenas_digitos = re.sub(r'\D', '', texto)
    
    # Varre o banco de usuarios para ver se acha o CPF de algum deles nesse texto
    # (Metodo reverso: verifica se o CPF do usuario esta no texto da pagina)
    # Isso é mais seguro que tentar adivinhar o regex do PDF
    
    users = User.query.filter(User.cpf.isnot(None)).all()
    for user in users:
        cpf_limpo = user.cpf.replace('.', '').replace('-', '').strip()
        if len(cpf_limpo) == 11 and cpf_limpo in apenas_digitos:
            return user
    return None

@holerite_bp.route('/admin/importar', methods=['GET', 'POST'])
@login_required
def admin_importar():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        mes_ref = request.form.get('mes_ref')
        
        if not file or not mes_ref:
            flash('Selecione um arquivo e o mês de referência.')
            return redirect(url_for('holerite.admin_importar'))
            
        try:
            reader = PdfReader(file)
            cont_sucesso = 0
            cont_falha = 0
            
            for i, page in enumerate(reader.pages):
                texto = page.extract_text()
                user_encontrado = encontrar_cpf_no_texto(texto)
                
                if user_encontrado:
                    # Cria um novo PDF só com essa pagina na memoria
                    writer = PdfWriter()
                    writer.add_page(page)
                    
                    output_stream = io.BytesIO()
                    writer.write(output_stream)
                    output_stream.seek(0)
                    
                    # Nome do arquivo no Cloudinary
                    nome_arquivo = f"holerite_{user_encontrado.id}_{mes_ref}_{get_brasil_time().timestamp()}"
                    
                    # Upload para Cloudinary
                    upload_result = cloudinary.uploader.upload(
                        output_stream, 
                        public_id=nome_arquivo,
                        resource_type="auto",
                        folder="holerites"
                    )
                    
                    url_pdf = upload_result.get('secure_url')
                    public_id = upload_result.get('public_id')
                    
                    # Salva no Banco
                    # Verifica se ja existe desse mes para evitar duplicidade
                    existente = Holerite.query.filter_by(user_id=user_encontrado.id, mes_referencia=mes_ref).first()
                    if existente:
                        existente.url_arquivo = url_pdf
                        existente.public_id = public_id
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False # Reseta visualizacao
                    else:
                        novo = Holerite(user_id=user_encontrado.id, mes_referencia=mes_ref, url_arquivo=url_pdf, public_id=public_id)
                        db.session.add(novo)
                    
                    cont_sucesso += 1
                else:
                    cont_falha += 1
            
            db.session.commit()
            flash(f"Processamento concluído! {cont_sucesso} holerites enviados. {cont_falha} páginas não identificadas (sem CPF cadastrado).")
            
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao processar arquivo: {str(e)}")
            
    return render_template('admin_upload_holerite.html')

@holerite_bp.route('/meus-documentos')
@login_required
def meus_holerites():
    # Lista os holerites do usuario logado
    holerites = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.mes_referencia.desc()).all()
    return render_template('meus_holerites.html', holerites=holerites)

@holerite_bp.route('/confirmar-recebimento/<int:id>', methods=['POST'])
@login_required
def confirmar_recebimento(id):
    holerite = Holerite.query.get_or_404(id)
    if holerite.user_id != current_user.id:
        flash('Acesso negado.')
        return redirect(url_for('main.dashboard'))
    
    # Registra o aceite
    if not holerite.visualizado:
        holerite.visualizado = True
        holerite.visualizado_em = get_brasil_time()
        db.session.commit()
        flash('Recebimento confirmado com sucesso!')
        
    # Redireciona para o link do PDF (abre em nova aba geralmente)
    return redirect(holerite.url_arquivo)
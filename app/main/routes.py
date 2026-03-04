from flask import render_template, redirect, url_for, jsonify, request, g, Response, make_response, send_from_directory, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, PontoAjuste, Recibo, Holerite, PreCadastro, Notificacao, PontoResumo, PontoRegistro, HistoricoSaida, PushSubscription, Empresa
from app.utils import get_brasil_time, has_permission, time_to_minutes
from datetime import timedelta
from sqlalchemy import func, text
import traceback
import json
import os
from google.cloud import storage

from app.main import main_bp

@main_bp.route('/')
@login_required
def dashboard():
    if current_user.is_first_access:
        return redirect(url_for('auth.primeiro_acesso'))
    
    if current_user.role == 'Terminal':
        return redirect(url_for('ponto.terminal_scanner'))

    hoje = get_brasil_time().date()

    dados = {
        'hoje': hoje.strftime('%d/%m/%Y'),
        'doc_pendentes': 0,
        'nome_empresa': g.empresa.nome if hasattr(g, 'empresa') and g.empresa else "Vortice SaaS"
    }

    docs_h = Holerite.query.filter_by(user_id=current_user.id, visualizado=False).count()
    docs_r = Recibo.query.filter_by(user_id=current_user.id, visualizado=False).count()
    dados['doc_pendentes'] = docs_h + docs_r

    ultimo_ponto = PontoRegistro.query.filter_by(
        user_id=current_user.id, 
        data_registro=hoje
    ).order_by(PontoRegistro.hora_registro.desc()).first()

    status_ponto = {
        'texto': 'Não Iniciado',
        'badge': 'bg-slate-500',
        'icone': 'fa-coffee',
        'proximo': 'Entrada'
    }

    if ultimo_ponto:
        tipo = ultimo_ponto.tipo.lower()
        if 'entrada' in tipo or 'retorno' in tipo:
            status_ponto = {
                'texto': 'Trabalhando',
                'badge': 'bg-emerald-500',
                'icone': 'fa-briefcase',
                'proximo': 'Saída p/ Almoço' if 'entrada' in tipo else 'Saída'
            }
        elif 'almoço' in tipo and 'saída' in tipo:
            status_ponto = {
                'texto': 'Em Almoço',
                'badge': 'bg-amber-500',
                'icone': 'fa-utensils',
                'proximo': 'Retorno do Almoço'
            }
        elif 'saída' in tipo and 'almoço' not in tipo:
             status_ponto = {
                'texto': 'Encerrado',
                'badge': 'bg-blue-500',
                'icone': 'fa-check-circle',
                'proximo': 'Jornada Concluída'
            }

    admin_stats = {}
    
    # -------------------------------------------------------------------------
    # CORREÇÃO DO MISTÉRIO DOS 5 EFETIVOS (Trava Multi-Tenant Adicionada)
    # -------------------------------------------------------------------------
    if has_permission('USUARIOS'):
        admin_stats['total_users'] = User.query.filter(User.username != '12345678900', User.username != 'terminal', User.empresa_id == g.empresa_id).count()
        admin_stats['pendentes_cadastro'] = PreCadastro.query.filter_by(empresa_id=g.empresa_id).count()

    if has_permission('PONTO'):
        admin_stats['ajustes_pendentes'] = PontoAjuste.query.filter_by(status='Pendente', empresa_id=g.empresa_id).count()

    return render_template('main/dashboard.html', dados=dados, admin=admin_stats, status_ponto=status_ponto)

@main_bp.route('/sw.js')
def service_worker():
    response = make_response(send_from_directory(os.path.join(current_app.root_path, 'static'), 'service-worker.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@main_bp.route('/cdn/logos/<slug>')
def serve_logo(slug):
    bucket_name = os.environ.get('VORTICE_BUCKET', 'vortice-assets')
    icone_padrao = '/static/icons/vortice-icon.png'
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blobs = list(bucket.list_blobs(prefix=f"{slug}/logo/logo_{slug}."))
        if not blobs: return redirect(icone_padrao)
        blob = blobs[0]
        image_data = blob.download_as_bytes()
        return Response(image_data, mimetype=blob.content_type)
    except Exception as e:
        return redirect(icone_padrao)

# ==============================================================================
# 📱 GERADOR DINÂMICO DE MANIFEST PWA (WHITE-LABEL)
# ==============================================================================
@main_bp.route('/manifest.json')
def dynamic_manifest():
    slug = request.args.get('slug')
    empresa_contexto = None

    if slug:
        empresa_contexto = Empresa.query.filter_by(slug=slug).first()
    elif hasattr(g, 'empresa') and g.empresa:
        empresa_contexto = g.empresa

    # Valores padrão Vortice
    app_name = "Vortice Gestão"
    short_name = "Vortice App"
    icon_url = "/static/icons/vortice-icon.png"
    theme_color = "#0f172a"
    
    url_inicial = f"/login/{slug}" if slug else "/"
    
    # Sobrescreve com os dados da empresa (White-label)
    if empresa_contexto:
        app_name = empresa_contexto.nome
        short_name = f"{empresa_contexto.nome.split()[0]} App"
        config = empresa_contexto.config_json or {}
        icon_url = config.get('logo_url') if config.get('logo_url') else icon_url
        theme_color = config.get('cor_primaria', theme_color)

    manifest = {
        "name": app_name,
        "short_name": short_name,
        "description": "O controle total da sua operação e recursos humanos em um único lugar.",
        "start_url": url_inicial,
        "scope": "/",
        "display": "standalone",
        "background_color": "#f8fafc", # Cor de fundo que bate com o body do CSS para evitar flashes brancos
        "theme_color": theme_color,
        "orientation": "portrait-primary", # Bloqueia rotação indesejada no telemóvel
        "prefer_related_applications": False,
        "icons": [
            { "src": icon_url, "sizes": "192x192", "type": "image/png", "purpose": "any maskable" },
            { "src": icon_url, "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
        ]
    }
    
    return jsonify(manifest)

@main_bp.route('/api/notificacoes', methods=['GET'])
@login_required
def buscar_notificacoes():
    notifs = Notificacao.query.filter_by(user_id=current_user.id).order_by(Notificacao.data_criacao.desc()).limit(10).all()
    nao_lidas = Notificacao.query.filter_by(user_id=current_user.id, lida=False).count()
    lista = []
    for n in notifs:
        lista.append({'id': n.id, 'mensagem': n.mensagem, 'link': n.link, 'lida': n.lida, 'tempo': n.data_criacao.strftime('%d/%m %H:%M')})
    return jsonify({'nao_lidas': nao_lidas, 'itens': lista})

@main_bp.route('/api/notificacoes/ler/<int:notif_id>', methods=['POST'])
@login_required
def ler_notificacao(notif_id):
    notif = Notificacao.query.filter_by(id=notif_id, user_id=current_user.id).first()
    if notif:
        notif.lida = True
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@main_bp.route('/api/notificacoes/ler_todas', methods=['POST'])
@login_required
def ler_todas_notificacoes():
    try:
        Notificacao.query.filter_by(user_id=current_user.id, lida=False).update({'lida': True})
        db.session.commit()
        return jsonify({'success': True})
    except:
        db.session.rollback()
        return jsonify({'success': False}), 500

@main_bp.route('/api/notificacoes/limpar', methods=['POST'])
@login_required
def limpar_notificacoes():
    try:
        Notificacao.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return jsonify({'success': True})
    except:
        db.session.rollback()
        return jsonify({'success': False}), 500

@main_bp.route('/api/analytics', methods=['GET'])
@login_required
def api_analytics():
    clean_username = str(current_user.username).replace('.', '').replace('-', '')
    is_master = current_user.role == 'Master' or clean_username == '50097952800'
    
    if not is_master:
        return jsonify({'error': 'Acesso negado'}), 403
        
    try:
        hoje = get_brasil_time().date()
        sete_dias_atras = hoje - timedelta(days=6)
        primeiro_dia_mes = hoje.replace(day=1)

        ponto_hoje = db.session.query(PontoResumo.status_dia, func.count(PontoResumo.id)).filter(PontoResumo.data_referencia == hoje, PontoResumo.empresa_id == g.empresa_id).group_by(PontoResumo.status_dia).all()
        raio_x = {status: qtd for status, qtd in ponto_hoje}
        
        dias_labels = [(sete_dias_atras + timedelta(days=i)).strftime('%d/%m') for i in range(7)]
        risco_faltas = []
        risco_extras = []
        for i in range(7):
            dia_alvo = sete_dias_atras + timedelta(days=i)
            faltas = PontoResumo.query.filter(PontoResumo.data_referencia == dia_alvo, PontoResumo.status_dia == 'Falta', PontoResumo.empresa_id == g.empresa_id).count()
            extras_min = db.session.query(func.sum(PontoResumo.minutos_saldo)).filter(PontoResumo.data_referencia == dia_alvo, PontoResumo.minutos_saldo > 0, PontoResumo.empresa_id == g.empresa_id).scalar() or 0
            risco_faltas.append(faltas)
            risco_extras.append(round(extras_min / 60, 1))

        saidas = db.session.query(User.departamento, func.sum(HistoricoSaida.quantidade)).join(User, User.real_name == HistoricoSaida.colaborador).filter(HistoricoSaida.data_entrega >= primeiro_dia_mes, User.empresa_id == g.empresa_id).group_by(User.departamento).all()
        custos_labels = [s[0] or 'Geral' for s in saidas]
        custos_data = [s[1] for s in saidas]

        total_holerites = db.session.query(Holerite).join(User).filter(Holerite.enviado_em >= primeiro_dia_mes, User.empresa_id == g.empresa_id).count()
        lidos_holerites = db.session.query(Holerite).join(User).filter(Holerite.enviado_em >= primeiro_dia_mes, Holerite.visualizado == True, User.empresa_id == g.empresa_id).count()
        total_recibos = db.session.query(Recibo).join(User).filter(Recibo.created_at >= primeiro_dia_mes, User.empresa_id == g.empresa_id).count()
        lidos_recibos = db.session.query(Recibo).join(User).filter(Recibo.created_at >= primeiro_dia_mes, Recibo.visualizado == True, User.empresa_id == g.empresa_id).count()
        
        total_docs = total_holerites + total_recibos
        docs_lidos = lidos_holerites + lidos_recibos
        escudo_pct = int((docs_lidos / total_docs * 100)) if total_docs > 0 else 100

        pontos_hoje = [0, 0, 0] 
        users = User.query.filter_by(empresa_id=g.empresa_id).all()
        for u in users:
            if u.inicio_jornada_ideal:
                entrada = PontoRegistro.query.filter(PontoRegistro.user_id==u.id, PontoRegistro.data_registro==hoje, PontoRegistro.tipo.ilike('%entrada%')).order_by(PontoRegistro.hora_registro.asc()).first()
                if entrada:
                    hora_ideal = time_to_minutes(u.inicio_jornada_ideal)
                    hora_real = time_to_minutes(entrada.hora_registro)
                    atraso = hora_real - hora_ideal
                    
                    if atraso <= 10: pontos_hoje[0] += 1
                    elif atraso <= 30: pontos_hoje[1] += 1
                    else: pontos_hoje[2] += 1

        return jsonify({
            'raio_x': raio_x,
            'risco': {'labels': dias_labels, 'faltas': risco_faltas, 'extras': risco_extras},
            'custos': {'labels': custos_labels, 'data': custos_data},
            'escudo': escudo_pct,
            'pontualidade': pontos_hoje
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@main_bp.route('/vortice-migrar')
def vortice_migrar():
    try:
        db.create_all()
        tabelas = ['users', 'pre_cadastros', 'itens_estoque', 'historico_entrada', 'historico_saida',
                   'holerites', 'recibos', 'assinaturas_digitais', 'ponto_registros', 'ponto_resumos',
                   'ponto_ajustes', 'atestados', 'periodos_aquisitivos', 'solicitacoes_ausencia',
                   'solicitacoes_uniforme', 'notificacoes', 'push_subscriptions']
        
        for tabela in tabelas:
            try:
                db.session.execute(text(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS empresa_id INTEGER REFERENCES empresas(id) ON DELETE CASCADE;"))
                db.session.execute(text(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP;"))
                db.session.execute(text(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITHOUT TIME ZONE;"))
                db.session.execute(text(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITHOUT TIME ZONE;"))
            except: pass
        db.session.commit()
        return "Migracao SaaS e infraestrutura de auditoria concluidas!"
    except Exception as e:
        db.session.rollback()
        return f"Erro na migracao: {str(e)}"

@main_bp.route('/migrar-rbac')
def migrar_rbac():
    try:
        db.create_all()
        db.session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cargo_id INTEGER REFERENCES roles(id) ON DELETE SET NULL;"))
        db.session.commit()
        return "Motor RBAC Inicializado!"
    except Exception as e:
        db.session.rollback()
        return f"Erro: {str(e)}"

@main_bp.route('/semear-permissoes')
def semear_permissoes():
    from app.models import Permission
    permissoes_padrao = [
        {'codigo': 'PONTO', 'nome': 'Gestão de Ponto (Aprovar/Editar)', 'modulo': 'RH'},
        {'codigo': 'DOCUMENTOS', 'nome': 'Gestão de Documentos (Atestados/Holerites)', 'modulo': 'RH'},
        {'codigo': 'ESTOQUE', 'nome': 'Gestão de Uniformes e EPIs', 'modulo': 'Logística'},
        {'codigo': 'USUARIOS', 'nome': 'Gerir Utilizadores e Acessos', 'modulo': 'Administração'}
    ]
    try:
        for p in permissoes_padrao:
            if not Permission.query.filter_by(codigo=p['codigo']).first():
                db.session.add(Permission(codigo=p['codigo'], nome=p['nome'], modulo=p['modulo']))
        db.session.commit()
        return "Permissões Semeada!"
    except Exception as e:
        db.session.rollback()
        return f"Erro: {str(e)}"

@main_bp.route('/api/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    try:
        sub_info = request.get_json()
        if not sub_info: return jsonify({'success': False, 'error': 'Dados inválidos'}), 400
            
        endpoint = sub_info.get('endpoint')
        keys = sub_info.get('keys', {})
        p256dh = keys.get('p256dh')
        auth = keys.get('auth')
        
        if not endpoint or not p256dh or not auth: return jsonify({'success': False, 'error': 'Chaves criptográficas ausentes'}), 400
            
        existente = PushSubscription.query.filter_by(endpoint=endpoint).first()
        if existente:
            existente.user_id = current_user.id
            db.session.commit()
        else:
            nova_sub = PushSubscription(user_id=current_user.id, endpoint=endpoint, p256dh=p256dh, auth=auth)
            db.session.add(nova_sub)
            db.session.commit()
            
        return jsonify({'success': True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500



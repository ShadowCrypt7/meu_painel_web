import os
import requests
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from dotenv import load_dotenv

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo 


from database import get_db_connection, create_tables, try_add_ativo_column_to_planos, try_add_status_usuario_column, try_add_duracao_dias_to_planos, try_add_data_fim_to_assinaturas, try_add_notificacao_exp_tipo_to_assinaturas

# Defina o seu fuso horário local
FUSO_HORARIO_LOCAL = ZoneInfo("America/Sao_Paulo")

load_dotenv()
try_add_status_usuario_column()
try_add_ativo_column_to_planos()
try_add_duracao_dias_to_planos()
try_add_data_fim_to_assinaturas()
try_add_notificacao_exp_tipo_to_assinaturas() 

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY_PAINEL")

USUARIO_PAINEL = os.getenv("USUARIO_PAINEL")
SENHA_PAINEL = os.getenv("SENHA_PAINEL")
CHAVE_API_BOT = os.getenv("CHAVE_PAINEL")
URL_API_NOTIFICACAO_BOT = os.getenv("URL_API_NOTIFICACAO_BOT")
CHAVE_SECRETA_PARA_BOT = os.getenv("CHAVE_SECRETA_PARA_BOT")

create_tables()

def formatar_data_local(dt_string_do_db):
    if not dt_string_do_db:
        return "" 
    try:
        dt_obj_naive = datetime.strptime(dt_string_do_db, '%Y-%m-%d %H:%M:%S')
        dt_obj_utc = dt_obj_naive.replace(tzinfo=timezone.utc)
        dt_obj_local = dt_obj_utc.astimezone(FUSO_HORARIO_LOCAL)
        return dt_obj_local.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return dt_string_do_db 
    except Exception as e:
        print(f"Erro ao formatar data {dt_string_do_db}: {e}")
        return dt_string_do_db

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['username']
        senha = request.form['password']
        if usuario == USUARIO_PAINEL and senha == SENHA_PAINEL:
            session['usuario_admin'] = usuario
            flash('Login bem-sucedido!', 'success')
            return redirect(url_for('home'))
        flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')

@app.route('/')
def home():
    if 'usuario_admin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    cursor_usuarios_ativos = conn.execute("SELECT COUNT(*) as count FROM usuarios WHERE status_usuario = 'A'")
    total_usuarios_ativos = cursor_usuarios_ativos.fetchone()['count']

    cursor_assinaturas_ativas = conn.execute("""
        SELECT COUNT(a.id_assinatura) as count 
        FROM assinaturas a
        JOIN usuarios u ON a.chat_id_usuario = u.chat_id
        WHERE u.status_usuario = 'A' AND (a.status_pagamento = 'aprovado_manual' OR a.status_pagamento = 'pago_gateway')
    """)
    total_assinaturas_ativas = cursor_assinaturas_ativas.fetchone()['count']

    cursor_novas_assinaturas_7d = conn.execute("""
        SELECT COUNT(*) as count 
        FROM assinaturas 
        WHERE data_compra >= datetime('now', '-7 days') 
    """)
    novas_assinaturas_7dias = cursor_novas_assinaturas_7d.fetchone()['count']

    assinaturas_db = conn.execute('''
        WITH RankedAssinaturas AS (
            SELECT 
                a.id_assinatura, u.chat_id, u.username, u.first_name, 
                p.nome_exibicao as nome_plano, a.id_plano_assinado, a.status_pagamento, 
                a.data_compra, a.data_liberacao, a.data_fim, /* <<< ADICIONADO a.data_fim */
                u.status_usuario,
                ROW_NUMBER() OVER (PARTITION BY u.chat_id 
                                   ORDER BY 
                                       CASE a.status_pagamento
                                           WHEN 'aprovado_manual' THEN 1
                                           WHEN 'pago_gateway' THEN 1
                                           WHEN 'pendente_comprovante' THEN 2
                                           WHEN 'pendente_gateway' THEN 3
                                           ELSE 4
                                       END, 
                                       a.data_compra DESC) as rn
            FROM assinaturas a
            JOIN usuarios u ON u.chat_id = a.chat_id_usuario
            JOIN planos p ON p.id_plano = a.id_plano_assinado
            WHERE u.status_usuario = 'A'
        )
        SELECT * FROM RankedAssinaturas
        WHERE rn = 1
        ORDER BY data_compra DESC;
    ''').fetchall()
    conn.close()

    assinaturas_para_template = []
    for row_original in assinaturas_db:
        row_modificada = dict(row_original)
        row_modificada['data_compra'] = formatar_data_local(row_modificada['data_compra'])
        if row_modificada.get('data_liberacao'):
            row_modificada['data_liberacao'] = formatar_data_local(row_modificada['data_liberacao'])
        
        # Formatar data_fim
        if row_modificada.get('data_fim'):
            row_modificada['data_fim_formatada'] = formatar_data_local(row_modificada['data_fim'])
        else:
            row_modificada['data_fim_formatada'] = "Vitalício"
            
        assinaturas_para_template.append(row_modificada)
    
    return render_template(
        'index.html', 
        assinaturas=assinaturas_para_template,
        total_usuarios_ativos=total_usuarios_ativos,
        total_assinaturas_ativas=total_assinaturas_ativas,
        novas_assinaturas_7dias=novas_assinaturas_7dias    
    )

@app.route('/logout')
def logout():
    session.pop('usuario_admin', None)
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

@app.route('/aprovar_assinatura/<int:id_assinatura>', methods=['POST'])
def aprovar_assinatura(id_assinatura):
    if 'usuario_admin' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT a.id_plano_assinado, a.chat_id_usuario, p.duracao_dias, p.link_conteudo, p.nome_exibicao as nome_plano
            FROM assinaturas a
            JOIN planos p ON a.id_plano_assinado = p.id_plano
            WHERE a.id_assinatura = ? AND a.status_pagamento = 'pendente_comprovante'
        ''', (id_assinatura,))
        dados_assinatura_e_plano = cursor.fetchone()

        if not dados_assinatura_e_plano:
            flash(f'Assinatura ID {id_assinatura} não estava pendente ou não foi encontrada.', 'warning')
            conn.close()
            return redirect(url_for('home'))

        data_liberacao_dt = datetime.now(timezone.utc) 
        data_fim_calculada = None 

        duracao_plano_dias = dados_assinatura_e_plano['duracao_dias']
        if duracao_plano_dias and duracao_plano_dias > 0:
            data_fim_calculada = data_liberacao_dt + timedelta(days=duracao_plano_dias)
        
        data_liberacao_str = data_liberacao_dt.strftime('%Y-%m-%d %H:%M:%S')
        data_fim_str = data_fim_calculada.strftime('%Y-%m-%d %H:%M:%S') if data_fim_calculada else None

        updated_rows = conn.execute('''
            UPDATE assinaturas 
            SET status_pagamento = 'aprovado_manual', 
                data_liberacao = ?,
                data_fim = ?
            WHERE id_assinatura = ? 
        ''', (data_liberacao_str, data_fim_str, id_assinatura)).rowcount
        conn.commit()
        
        if updated_rows > 0:
            flash(f'Assinatura ID {id_assinatura} aprovada manualmente!', 'success')

            if URL_API_NOTIFICACAO_BOT and CHAVE_SECRETA_PARA_BOT:
                payload_notificacao = {
                    "chave_secreta_interna": CHAVE_SECRETA_PARA_BOT,
                    "chat_id": dados_assinatura_e_plano["chat_id_usuario"],
                    "link_conteudo": dados_assinatura_e_plano["link_conteudo"],
                    "nome_plano": dados_assinatura_e_plano["nome_plano"]
                }
                try:
                    print(f"Enviando notificação de aprovação para o bot: {URL_API_NOTIFICACAO_BOT}, payload: {payload_notificacao}")
                    response_bot = requests.post(URL_API_NOTIFICACAO_BOT, json=payload_notificacao, timeout=10)
                    if response_bot.status_code == 200:
                        print(f"Bot notificou sucesso: {response_bot.json().get('mensagem')}")
                        flash('Bot foi notificado para enviar o acesso ao usuário.', 'info')
                    else:
                        print(f"Erro ao notificar bot: Status {response_bot.status_code} - {response_bot.text}")
                        flash(f'Assinatura aprovada, mas falha ao notificar o bot (Status: {response_bot.status_code}). Verifique os logs do bot.', 'warning')
                except requests.exceptions.RequestException as e_req:
                    print(f"Erro de conexão ao tentar notificar bot: {e_req}")
                    flash('Assinatura aprovada, mas erro de conexão ao tentar notificar o bot.', 'danger')
            else:
                flash('URL de notificação do bot ou chave não configurada. Não foi possível notificar o usuário automaticamente.', 'danger')
        else: 
            flash(f'Assinatura ID {id_assinatura} não foi atualizada (talvez já estivesse aprovada).', 'warning')

    except sqlite3.Error as e_sql:
        flash(f'Erro de banco de dados ao aprovar assinatura: {e_sql}', 'danger')
    except Exception as e_geral:
        flash(f'Erro geral ao aprovar assinatura: {e_geral}', 'danger')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('home'))

@app.route('/revogar_assinatura/<int:id_assinatura>', methods=['POST'])
def revogar_assinatura(id_assinatura):
    if 'usuario_admin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    try:
        updated_rows = conn.execute('''
            UPDATE assinaturas 
            SET status_pagamento = 'revogado_manual' 
            WHERE id_assinatura = ? 
        ''', (id_assinatura,)).rowcount
        conn.commit()
        if updated_rows > 0:
            flash(f'Assinatura ID {id_assinatura} revogada.', 'success')
        else:
            flash(f'Assinatura ID {id_assinatura} não encontrada.', 'warning')
    except sqlite3.Error as e:
        flash(f'Erro ao revogar assinatura: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('home'))


@app.route('/api/bot/registrar_assinatura', methods=['POST'])
def api_bot_registrar_assinatura():
    data = request.get_json()
    if not data or data.get("chave_api_bot") != CHAVE_API_BOT:
        return jsonify({"status": "erro", "mensagem": "Chave de API inválida ou dados não enviados"}), 403

    chat_id = data.get('chat_id')
    username = data.get('username') 
    first_name = data.get('first_name')
    id_plano_selecionado = data.get('id_plano') 
    status_pagamento_inicial = data.get('status_pagamento', 'pendente_comprovante')

    if not all([chat_id, first_name, id_plano_selecionado, status_pagamento_inicial]):
        return jsonify({"status": "erro", "mensagem": "Dados incompletos (chat_id, first_name, id_plano, status_pagamento são obrigatórios)"}), 400

    conn = get_db_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO usuarios (chat_id, username, first_name) VALUES (?, ?, ?)",
                       (chat_id, username, first_name))
        
        cursor = conn.execute('''
            INSERT INTO assinaturas (chat_id_usuario, id_plano_assinado, status_pagamento)
            VALUES (?, ?, ?)
        ''', (chat_id, id_plano_selecionado, status_pagamento_inicial))
        id_nova_assinatura = cursor.lastrowid 
        conn.commit()
        return jsonify({"status": "sucesso", "mensagem": "Assinatura registrada com sucesso.", "id_assinatura": id_nova_assinatura}), 201
    except sqlite3.IntegrityError as e: 
        conn.rollback()
        return jsonify({"status": "erro", "mensagem": f"Erro de integridade: {e}. Verifique se o id_plano é válido."}), 400
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"status": "erro", "mensagem": f"Erro no banco de dados: {e}"}), 500
    finally:
        conn.close()

@app.route('/api/bot/verificar_status', methods=['POST'])
# ... (código da API verificar_status continua igual, mas seria bom retornar data_fim aqui também no futuro) ...
# Por agora, vamos manter simples. Se precisar da data_fim no bot via /status, precisarei ajustar aqui.
def api_bot_verificar_status():
    data = request.get_json()
    if not data or data.get("chave_api_bot") != CHAVE_API_BOT:
        return jsonify({"status": "erro", "mensagem": "Chave de API inválida ou dados não enviados"}), 403

    chat_id = data.get('chat_id')
    id_plano_consulta = data.get('id_plano') 

    if not chat_id:
        return jsonify({"status": "erro", "mensagem": "chat_id é obrigatório"}), 400

    conn = get_db_connection()
    try:
        query = '''
            SELECT a.id_plano_assinado, p.nome_exibicao, a.status_pagamento, p.link_conteudo, a.data_fim
            FROM assinaturas a
            JOIN planos p ON a.id_plano_assinado = p.id_plano
            WHERE a.chat_id_usuario = ? 
        '''
        params = [chat_id]
        if id_plano_consulta:
            query += " AND a.id_plano_assinado = ?"
            params.append(id_plano_consulta)
        
        query += " ORDER BY CASE a.status_pagamento WHEN 'aprovado_manual' THEN 1 WHEN 'pago_gateway' THEN 1 ELSE 2 END, a.data_compra DESC LIMIT 1"
        
        assinatura = conn.execute(query, tuple(params)).fetchone()
        conn.close()

        if assinatura:
            data_fim_formatada_api = None
            if assinatura["data_fim"]:
                # A função formatar_data_local espera string, mas o DB retorna string para DATETIME
                data_fim_formatada_api = formatar_data_local(assinatura["data_fim"])

            return jsonify({
                "status": "sucesso", 
                "assinatura_ativa": True, 
                "id_plano": assinatura["id_plano_assinado"],
                "nome_plano": assinatura["nome_exibicao"],
                "status_pagamento": assinatura["status_pagamento"],
                "link_conteudo": assinatura["link_conteudo"] if "aprovado" in assinatura["status_pagamento"] or "pago" in assinatura["status_pagamento"] else None,
                "data_fim": data_fim_formatada_api # Enviando data_fim formatada para o bot
            }), 200
        else:
            return jsonify({"status": "sucesso", "assinatura_ativa": False, "mensagem": "Nenhuma assinatura encontrada para este usuário."}), 200
    except sqlite3.Error as e:
        conn.close()
        return jsonify({"status": "erro", "mensagem": f"Erro no banco de dados: {e}"}), 500


@app.route('/historico_assinaturas')
def historico_assinaturas():
    if 'usuario_admin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    search_username = request.args.get('search_username', '').strip()
    search_chat_id = request.args.get('search_chat_id', '').strip()
    filter_plano_id = request.args.get('filter_plano_id', '')
    filter_status = request.args.get('filter_status', '')

    planos_para_filtro_db = conn.execute("SELECT id_plano, nome_exibicao FROM planos ORDER BY nome_exibicao").fetchall()
    status_assinatura_possiveis = [
        "pendente_comprovante", "aprovado_manual", "revogado_manual", 
        "pago_gateway", "expirado"
    ]

    query_base = '''
        SELECT a.id_assinatura, u.chat_id, u.username, u.first_name, 
               p.nome_exibicao as nome_plano, a.id_plano_assinado, a.status_pagamento, 
               a.data_compra, a.data_liberacao, a.data_fim, /* <<< ADICIONADO a.data_fim */
               u.status_usuario
        FROM assinaturas a
        JOIN usuarios u ON u.chat_id = a.chat_id_usuario
        JOIN planos p ON p.id_plano = a.id_plano_assinado
    '''
    condicoes = []
    parametros = []

    if search_username:
        condicoes.append("(u.username LIKE ? OR (u.username IS NULL AND u.first_name LIKE ?))")
        parametros.extend([f'%{search_username}%', f'%{search_username}%'])
    if search_chat_id:
        try:
            chat_id_int = int(search_chat_id)
            condicoes.append("u.chat_id = ?")
            parametros.append(chat_id_int)
        except ValueError:
            flash("Chat ID inválido para busca. Deve ser um número.", "warning")
    if filter_plano_id:
        condicoes.append("a.id_plano_assinado = ?")
        parametros.append(filter_plano_id)
    if filter_status:
        condicoes.append("a.status_pagamento = ?")
        parametros.append(filter_status)

    if condicoes:
        query_base += " WHERE " + " AND ".join(condicoes)
    query_base += " ORDER BY a.data_compra DESC"
    
    todas_assinaturas_db = conn.execute(query_base, tuple(parametros)).fetchall()
    conn.close()
    
    assinaturas_para_template = []
    for row_original in todas_assinaturas_db:
        row_modificada = dict(row_original)
        row_modificada['data_compra'] = formatar_data_local(row_modificada['data_compra'])
        if row_modificada.get('data_liberacao'):
            row_modificada['data_liberacao'] = formatar_data_local(row_modificada['data_liberacao'])
        
        # Formatar data_fim
        if row_modificada.get('data_fim'):
            row_modificada['data_fim_formatada'] = formatar_data_local(row_modificada['data_fim'])
        else:
            row_modificada['data_fim_formatada'] = "Vitalício"
            
        assinaturas_para_template.append(row_modificada)
        
    return render_template(
        'historico_assinaturas.html', 
        assinaturas=assinaturas_para_template,
        planos_filtro=planos_para_filtro_db,
        status_filtro_lista=status_assinatura_possiveis,
        current_search_username=search_username,
        current_search_chat_id=search_chat_id,
        current_filter_plano_id=filter_plano_id,
        current_filter_status=filter_status
    )

@app.route('/admin/reativar_usuario/<int:chat_id_usuario_para_reativar>', methods=['POST'])
def reativar_usuario(chat_id_usuario_para_reativar):
    if 'usuario_admin' not in session:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        cursor = conn.execute("UPDATE usuarios SET status_usuario = 'A' WHERE chat_id = ? AND status_usuario = 'I'", 
                               (chat_id_usuario_para_reativar,))
        usuario_reativado = cursor.rowcount 
        conn.commit()
        
        if usuario_reativado > 0:
            flash(f'Usuário com Chat ID {chat_id_usuario_para_reativar} foi REATIVADO com sucesso!', 'success')
        else:
            flash(f'Usuário com Chat ID {chat_id_usuario_para_reativar} não foi encontrado com status "Inativo" ou já estava ativo.', 'warning')

    except sqlite3.Error as e:
        if conn: 
            conn.rollback() 
        flash(f'Erro ao reativar usuário: {e}', 'danger')
    finally:
        if conn:
            conn.close()
            
    return redirect(url_for('historico_assinaturas')) 

@app.route('/api/bot/planos', methods=['GET'])
def api_bot_get_planos():
    conn = get_db_connection()
    planos_db = conn.execute("SELECT id_plano, nome_exibicao, preco, descricao, duracao_dias FROM planos WHERE ativo = TRUE").fetchall() # Adicionado duracao_dias
    conn.close()
    planos = [dict(p) for p in planos_db]
    return jsonify({"status": "sucesso", "planos": planos}), 200

@app.route('/admin/desativar_usuario/<int:chat_id_usuario_para_desativar>', methods=['POST'])
def desativar_usuario(chat_id_usuario_para_desativar):
    if 'usuario_admin' not in session:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        cursor = conn.execute("UPDATE usuarios SET status_usuario = 'I' WHERE chat_id = ?", (chat_id_usuario_para_desativar,))
        usuario_desativado = cursor.rowcount 
        conn.commit()
        
        if usuario_desativado > 0:
            flash(f'Usuário com Chat ID {chat_id_usuario_para_desativar} foi desativado com sucesso!', 'success')
        else:
            flash(f'Usuário com Chat ID {chat_id_usuario_para_desativar} não encontrado ou já estava inativo.', 'warning')

    except sqlite3.Error as e:
        if conn:
            conn.rollback() 
        flash(f'Erro ao desativar usuário: {e}', 'danger')
    finally:
        if conn:
            conn.close()
            
    return redirect(url_for('home'))

@app.route('/admin/planos')
# ... (código do admin_planos precisa buscar e passar data_fim, mas ele busca 'duracao_dias' dos planos, não 'data_fim' das assinaturas)
# Ele já busca 'duracao_dias' dos planos, o que é correto para a listagem de planos.
def admin_planos():
    if 'usuario_admin' not in session:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    # A query aqui já busca duracao_dias, que é o que o template admin_planos.html espera
    planos_db = conn.execute('SELECT id_plano, nome_exibicao, preco, descricao, link_conteudo, ativo, duracao_dias FROM planos ORDER BY nome_exibicao').fetchall()
    conn.close()
    
    return render_template('admin_planos.html', planos=planos_db)


@app.route('/admin/planos/novo', methods=['GET', 'POST'])
def admin_adicionar_plano():
    if 'usuario_admin' not in session:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        id_plano = request.form['id_plano']
        nome_exibicao = request.form['nome_exibicao']
        try:
            preco = float(request.form['preco'])
        except ValueError:
            flash('Preço inválido. Use ponto como separador decimal (ex: 19.99).', 'danger')
            return render_template('admin_plano_form.html', acao="Adicionar", plano=request.form) 

        descricao = request.form['descricao']
        link_conteudo = request.form['link_conteudo']
        ativo = 'ativo' in request.form 
        
        tem_expiracao = 'tem_expiracao' in request.form
        duracao_dias_str = request.form.get('duracao_dias', '').strip()
        duracao_dias = None

        if tem_expiracao:
            if not duracao_dias_str:
                flash('Duração em dias é obrigatória se o plano tem expiração.', 'danger')
                return render_template('admin_plano_form.html', acao="Adicionar", plano=request.form)
            try:
                duracao_dias = int(duracao_dias_str)
                if duracao_dias <= 0:
                    raise ValueError("Duração deve ser um número positivo.")
            except ValueError:
                flash('Duração em dias inválida. Deve ser um número inteiro positivo.', 'danger')
                return render_template('admin_plano_form.html', acao="Adicionar", plano=request.form)
        
        if not all([id_plano, nome_exibicao, preco is not None, link_conteudo]):
            flash('ID do Plano, Nome de Exibição, Preço e Link do Conteúdo são obrigatórios.', 'danger')
            return render_template('admin_plano_form.html', acao="Adicionar", plano=request.form)

        conn = get_db_connection()
        try:
            conn.execute('''
                INSERT INTO planos (id_plano, nome_exibicao, preco, descricao, link_conteudo, ativo, duracao_dias)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (id_plano, nome_exibicao, preco, descricao, link_conteudo, ativo, duracao_dias))
            conn.commit()
            flash(f'Plano "{nome_exibicao}" adicionado com sucesso!', 'success')
            return redirect(url_for('admin_planos'))
        except sqlite3.IntegrityError: 
            conn.rollback()
            flash(f'Erro: O ID do Plano "{id_plano}" já existe. Escolha outro ID.', 'danger')
        except sqlite3.Error as e:
            conn.rollback()
            flash(f'Erro no banco de dados ao adicionar plano: {e}', 'danger')
        finally:
            conn.close()
    
    return render_template('admin_plano_form.html', acao="Adicionar", plano=None)

@app.route('/admin/planos/editar/<id_plano_para_editar>', methods=['GET', 'POST'])
def admin_editar_plano(id_plano_para_editar):
    if 'usuario_admin' not in session:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    
    if request.method == 'POST':
        nome_exibicao = request.form['nome_exibicao']
        preco_str = request.form['preco']
        descricao = request.form['descricao']
        link_conteudo = request.form['link_conteudo']
        ativo = 'ativo' in request.form
        tem_expiracao = 'tem_expiracao' in request.form
        duracao_dias_str = request.form.get('duracao_dias', '').strip()
        duracao_dias = None
        
        plano_form_data = {
            'id_plano': id_plano_para_editar,
            'nome_exibicao': nome_exibicao,
            'preco': preco_str, 
            'descricao': descricao,
            'link_conteudo': link_conteudo,
            'ativo': ativo,
            'tem_expiracao': tem_expiracao,
            'duracao_dias': duracao_dias_str
        }

        try:
            preco = float(preco_str)
        except ValueError:
            flash('Preço inválido. Use ponto como separador decimal (ex: 19.99).', 'danger')
            return render_template('admin_plano_form.html', acao="Editar", plano=plano_form_data)

        if tem_expiracao:
            if not duracao_dias_str:
                flash('Duração em dias é obrigatória se o plano tem expiração.', 'danger')
                return render_template('admin_plano_form.html', acao="Editar", plano=plano_form_data)
            try:
                duracao_dias = int(duracao_dias_str)
                if duracao_dias <= 0:
                    raise ValueError("Duração deve ser um número positivo.")
            except ValueError:
                flash('Duração em dias inválida. Deve ser um número inteiro positivo.', 'danger')
                return render_template('admin_plano_form.html', acao="Editar", plano=plano_form_data)
        
        if not all([nome_exibicao, preco is not None, link_conteudo]): 
            flash('Nome de Exibição, Preço e Link do Conteúdo são obrigatórios.', 'danger')
            return render_template('admin_plano_form.html', acao="Editar", plano=plano_form_data)

        try:
            conn.execute('''
                UPDATE planos 
                SET nome_exibicao = ?, preco = ?, descricao = ?, link_conteudo = ?, ativo = ?, duracao_dias = ?
                WHERE id_plano = ?
            ''', (nome_exibicao, preco, descricao, link_conteudo, ativo, duracao_dias, id_plano_para_editar))
            conn.commit()
            flash(f'Plano "{nome_exibicao}" atualizado com sucesso!', 'success')
            conn.close()
            return redirect(url_for('admin_planos'))
        except sqlite3.Error as e:
            conn.rollback()
            flash(f'Erro no banco de dados ao atualizar plano: {e}', 'danger')
            conn.close()
            return render_template('admin_plano_form.html', acao="Editar", plano=plano_form_data)

    else: 
        plano_db = conn.execute('SELECT id_plano, nome_exibicao, preco, descricao, link_conteudo, ativo, duracao_dias FROM planos WHERE id_plano = ?', 
                                (id_plano_para_editar,)).fetchone()
        conn.close()
        
        if plano_db:
            # Adicionar 'tem_expiracao' ao dicionário do plano para o template
            plano_dict_para_form = dict(plano_db)
            plano_dict_para_form['tem_expiracao'] = bool(plano_db['duracao_dias'] and plano_db['duracao_dias'] > 0)
            return render_template('admin_plano_form.html', acao="Editar", plano=plano_dict_para_form)
        else:
            flash('Plano não encontrado.', 'danger')
            return redirect(url_for('admin_planos'))

@app.route('/admin/planos/toggle_ativo/<id_plano_toggle>', methods=['POST'])
def admin_toggle_ativo_plano(id_plano_toggle):
    if 'usuario_admin' not in session:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        plano_atual = conn.execute('SELECT ativo FROM planos WHERE id_plano = ?', (id_plano_toggle,)).fetchone()

        if plano_atual:
            novo_status_ativo = not plano_atual['ativo'] 
            conn.execute('UPDATE planos SET ativo = ? WHERE id_plano = ?', (novo_status_ativo, id_plano_toggle))
            conn.commit()
            acao = "ativado" if novo_status_ativo else "desativado"
            flash(f'Plano "{id_plano_toggle}" foi {acao} com sucesso!', 'success')
        else:
            flash(f'Plano "{id_plano_toggle}" não encontrado.', 'danger')
        
    except sqlite3.Error as e:
        flash(f'Erro no banco de dados ao alterar status do plano: {e}', 'danger')
    finally:
        if conn:
            conn.close()
            
    return redirect(url_for('admin_planos'))

@app.route('/admin/excluir_plano/<id_plano_para_excluir>', methods=['POST'])
def admin_excluir_plano(id_plano_para_excluir):
    if 'usuario_admin' not in session:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        cursor_check = conn.execute('SELECT COUNT(*) as count FROM assinaturas WHERE id_plano_assinado = ?', (id_plano_para_excluir,))
        resultado_check = cursor_check.fetchone()

        if resultado_check and resultado_check['count'] > 0:
            flash(f'Erro: O plano "{id_plano_para_excluir}" não pode ser excluído pois existem {resultado_check["count"]} assinatura(s) vinculada(s) a ele. Considere desativá-lo.', 'danger')
        else:
            cursor_delete = conn.execute('DELETE FROM planos WHERE id_plano = ?', (id_plano_para_excluir,))
            conn.commit()
            if cursor_delete.rowcount > 0:
                flash(f'Plano "{id_plano_para_excluir}" excluído permanentemente com sucesso!', 'success')
            else:
                flash(f'Plano "{id_plano_para_excluir}" não encontrado para exclusão.', 'warning')
                
    except sqlite3.Error as e:
        flash(f'Erro no banco de dados ao tentar excluir plano: {e}', 'danger')
    finally:
        if conn:
            conn.close()
            
    return redirect(url_for('admin_planos'))

@app.route('/admin/excluir_usuario_permanente/<int:chat_id_para_excluir>', methods=['POST'])
def admin_excluir_usuario_permanente(chat_id_para_excluir):
    if 'usuario_admin' not in session:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        conn.execute("BEGIN TRANSACTION;")
        cursor_assinaturas = conn.execute("DELETE FROM assinaturas WHERE chat_id_usuario = ?", (chat_id_para_excluir,))
        assinaturas_removidas_count = cursor_assinaturas.rowcount
        cursor_usuario = conn.execute("DELETE FROM usuarios WHERE chat_id = ?", (chat_id_para_excluir,))
        usuario_removido_count = cursor_usuario.rowcount
        conn.commit() 
        
        if usuario_removido_count > 0:
            flash(f'Usuário com Chat ID {chat_id_para_excluir} e {assinaturas_removidas_count} assinatura(s) foram PERMANENTEMENTE excluídos!', 'success')
        elif assinaturas_removidas_count > 0 : 
             flash(f'{assinaturas_removidas_count} assinatura(s) do Chat ID {chat_id_para_excluir} foram PERMANENTEMENTE excluídas. Usuário não encontrado.', 'warning')
        else:
            flash(f'Nenhum usuário ou assinatura encontrada para o Chat ID {chat_id_para_excluir} para exclusão.', 'info')

    except sqlite3.Error as e:
        if conn:
            conn.rollback() 
        flash(f'Erro de banco de dados ao tentar excluir permanentemente o usuário: {e}', 'danger')
    finally:
        if conn:
            conn.close()
            
    return redirect(url_for('historico_assinaturas'))

@app.route('/api/bot/assinaturas_expirando', methods=['GET'])
def api_bot_assinaturas_expirando():
    # Autenticação da API (importante!)
    chave_recebida = request.args.get('chave_api_bot')
    if chave_recebida != CHAVE_API_BOT: # CHAVE_API_BOT é o os.getenv("CHAVE_PAINEL")
        return jsonify({"status": "erro", "mensagem": "Chave de API inválida"}), 403

    try:
        dias_ate_expirar_str = request.args.get('dias_ate_expirar', '7') # Padrão para 7 dias
        tipo_janela_notificacao = request.args.get('tipo_janela_notificacao') # Ex: "exp_7d", "exp_3d"

        if not tipo_janela_notificacao:
            return jsonify({"status": "erro", "mensagem": "Parâmetro 'tipo_janela_notificacao' é obrigatório."}), 400
        
        dias_ate_expirar = int(dias_ate_expirar_str)
        if dias_ate_expirar <= 0:
            return jsonify({"status": "erro", "mensagem": "'dias_ate_expirar' deve ser positivo."}), 400

    except ValueError:
        return jsonify({"status": "erro", "mensagem": "'dias_ate_expirar' deve ser um número inteiro."}), 400

    conn = get_db_connection()
    try:
        # datetime('now', '+X days') já retorna no formato YYYY-MM-DD HH:MM:SS que o SQLite compara corretamente com data_fim
        data_limite_superior = f"datetime('now', '+{dias_ate_expirar} days')"
        
        # A data_fim deve ser maior ou igual a hoje E menor ou igual à data limite superior.
        # E o tipo de notificação específico não deve ter sido enviado ainda.
        query = f"""
            SELECT 
                a.id_assinatura, 
                a.chat_id_usuario, 
                p.nome_exibicao as nome_plano, 
                a.data_fim,
                u.first_name,
                u.username
            FROM assinaturas a
            JOIN planos p ON a.id_plano_assinado = p.id_plano
            JOIN usuarios u ON a.chat_id_usuario = u.chat_id
            WHERE a.status_pagamento IN ('aprovado_manual', 'pago_gateway')
              AND u.status_usuario = 'A'
              AND a.data_fim IS NOT NULL
              AND a.data_fim >= datetime('now') 
              AND a.data_fim <= {data_limite_superior}
              AND (a.notificacao_expiracao_tipo_enviada IS NULL OR a.notificacao_expiracao_tipo_enviada != ?)
        """
        
        assinaturas_expirando_db = conn.execute(query, (tipo_janela_notificacao,)).fetchall()
        
        assinaturas_formatadas = []
        for row in assinaturas_expirando_db:
            assinaturas_formatadas.append({
                "id_assinatura": row["id_assinatura"],
                "chat_id_usuario": row["chat_id_usuario"],
                "nome_plano": row["nome_plano"],
                "data_fim_formatada": formatar_data_local(row["data_fim"]) if row["data_fim"] else "N/A",
                "first_name": row["first_name"],
                "username": row["username"]
            })
        conn.close()
        return jsonify({"status": "sucesso", "assinaturas": assinaturas_formatadas}), 200
        
    except sqlite3.Error as e_sql:
        if conn: conn.close()
        print(f"Erro SQL em /api/bot/assinaturas_expirando: {e_sql}")
        return jsonify({"status": "erro", "mensagem": f"Erro de banco de dados: {e_sql}"}), 500
    except Exception as e_geral:
        if conn: conn.close()
        print(f"Erro geral em /api/bot/assinaturas_expirando: {e_geral}")
        return jsonify({"status": "erro", "mensagem": f"Erro interno do servidor: {e_geral}"}), 500

@app.route('/api/bot/marcar_notificacao_expiracao', methods=['POST'])
def api_bot_marcar_notificacao_expiracao():
    # Autenticação da API
    # (Você pode usar a mesma chave CHAVE_API_BOT)
    data = request.get_json()
    if not data or data.get("chave_api_bot") != CHAVE_API_BOT:
        return jsonify({"status": "erro", "mensagem": "Chave de API inválida ou dados não enviados"}), 403

    id_assinatura = data.get('id_assinatura')
    tipo_notificacao_enviada = data.get('tipo_notificacao') # Ex: "exp_7d"

    if not id_assinatura or not tipo_notificacao_enviada:
        return jsonify({"status": "erro", "mensagem": "id_assinatura e tipo_notificacao são obrigatórios"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            UPDATE assinaturas 
            SET notificacao_expiracao_tipo_enviada = ?
            WHERE id_assinatura = ?
        ''', (tipo_notificacao_enviada, id_assinatura))
        conn.commit()

        if cursor.rowcount > 0:
            conn.close()
            return jsonify({"status": "sucesso", "mensagem": f"Assinatura {id_assinatura} marcada como notificada para {tipo_notificacao_enviada}."}), 200
        else:
            conn.close()
            return jsonify({"status": "erro", "mensagem": f"Assinatura {id_assinatura} não encontrada ou não necessitou atualização."}), 404
            
    except sqlite3.Error as e_sql:
        if conn: conn.close()
        return jsonify({"status": "erro", "mensagem": f"Erro de banco de dados: {e_sql}"}), 500
    except Exception as e_geral:
        if conn: conn.close()
        return jsonify({"status": "erro", "mensagem": f"Erro interno do servidor: {e_geral}"}), 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5001)) 
    app.run(debug=True, host='0.0.0.0', port=port)

import os
import requests
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from dotenv import load_dotenv

from datetime import datetime, timezone 
from zoneinfo import ZoneInfo 

# Importar funções do nosso módulo de banco de dados
from database import get_db_connection, create_tables, try_add_ativo_column_to_planos, try_add_status_usuario_column

# Defina o seu fuso horário local
# Para Goiás (que geralmente segue o horário de Brasília):
FUSO_HORARIO_LOCAL = ZoneInfo("America/Sao_Paulo")

load_dotenv()
try_add_status_usuario_column()
try_add_ativo_column_to_planos()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY_PAINEL")

USUARIO_PAINEL = os.getenv("USUARIO_PAINEL")
SENHA_PAINEL = os.getenv("SENHA_PAINEL")
CHAVE_API_BOT = os.getenv("CHAVE_PAINEL") # Renomeando para clareza, essa é a chave que o BOT usa
URL_API_NOTIFICACAO_BOT = os.getenv("URL_API_NOTIFICACAO_BOT")
CHAVE_SECRETA_PARA_BOT = os.getenv("CHAVE_SECRETA_PARA_BOT") # Esta é a CHAVE_PAINEL

# Garante que as tabelas sejam criadas ao iniciar o app do painel, se não existirem.
# Isso é seguro por causa do "IF NOT EXISTS" nas queries de criação.
create_tables()

# Em painel.py, pode ser antes das suas rotas

def formatar_data_local(dt_string_do_db):
    if not dt_string_do_db:
        return "" # Ou None, ou algum placeholder

    try:
        # SQLite geralmente armazena datetime como string no formato 'YYYY-MM-DD HH:MM:SS'
        # Primeiro, converte a string para um objeto datetime "naive" (sem fuso)
        dt_obj_naive = datetime.strptime(dt_string_do_db, '%Y-%m-%d %H:%M:%S')
        
        # Assume que este datetime naive do DB está em UTC
        dt_obj_utc = dt_obj_naive.replace(tzinfo=timezone.utc)
        
        # Converte para o fuso horário local definido
        dt_obj_local = dt_obj_utc.astimezone(FUSO_HORARIO_LOCAL)
        
        # Formata para exibição
        return dt_obj_local.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        # Se o formato da string for inesperado, retorna a string original
        return dt_string_do_db 
    except Exception as e:
        print(f"Erro ao formatar data {dt_string_do_db}: {e}")
        return dt_string_do_db # Retorna original em caso de outro erro

# --- Funções de Banco de Dados Específicas do Painel (se necessário) ---
# Por enquanto, a maioria das interações pode ser direta nas rotas.

# --- Rotas de Autenticação e Interface do Admin ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['username']
        senha = request.form['password']
        if usuario == USUARIO_PAINEL and senha == SENHA_PAINEL:
            session['usuario_admin'] = usuario # Chave da sessão mais específica
            flash('Login bem-sucedido!', 'success')
            return redirect(url_for('home'))
        flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')


@app.route('/')
def home():
    if 'usuario_admin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    assinaturas_db = conn.execute('''
        WITH RankedAssinaturas AS (
            SELECT 
                a.id_assinatura, u.chat_id, u.username, u.first_name, 
                p.nome_exibicao as nome_plano, a.id_plano_assinado, a.status_pagamento, 
                a.data_compra, a.data_liberacao, u.status_usuario, -- Adicionamos status_usuario aqui
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

    # Processar as datas para o fuso horário local
    assinaturas_para_template = []
    for row_original in assinaturas_db:
        row_modificada = dict(row_original) # Converte sqlite3.Row para dict para poder modificar
        row_modificada['data_compra'] = formatar_data_local(row_modificada['data_compra'])
        if row_modificada.get('data_liberacao'): # data_liberacao pode ser NULL
            row_modificada['data_liberacao'] = formatar_data_local(row_modificada['data_liberacao'])
        assinaturas_para_template.append(row_modificada)
    
    return render_template('index.html', assinaturas=assinaturas_para_template)

@app.route('/logout')
def logout():
    session.pop('usuario_admin', None)
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

@app.route('/aprovar_assinatura/<int:id_assinatura>', methods=['POST'])
def aprovar_assinatura(id_assinatura):
    if 'usuario_admin' not in session:
        # ... (redirecionar para login) ...
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor() # Usar cursor para pegar dados retornados
        # Pega os dados necessários para notificar o bot ANTES de fazer o commit da aprovação
        cursor.execute('''
            SELECT a.chat_id_usuario, p.link_conteudo, p.nome_exibicao as nome_plano
            FROM assinaturas a
            JOIN planos p ON a.id_plano_assinado = p.id_plano
            WHERE a.id_assinatura = ? AND a.status_pagamento = 'pendente_comprovante'
        ''', (id_assinatura,))
        dados_assinatura = cursor.fetchone()

        if not dados_assinatura:
            flash(f'Assinatura ID {id_assinatura} não estava pendente ou não foi encontrada.', 'warning')
            conn.close()
            return redirect(url_for('home'))

        # Atualiza o status da assinatura
        updated_rows = conn.execute('''
            UPDATE assinaturas 
            SET status_pagamento = 'aprovado_manual', data_liberacao = CURRENT_TIMESTAMP
            WHERE id_assinatura = ? 
        ''', (id_assinatura,)).rowcount # rowcount aqui ainda funciona para o UPDATE
        conn.commit()

        if updated_rows > 0:
            flash(f'Assinatura ID {id_assinatura} aprovada manualmente!', 'success')

            # Agora, notificar o bot para ele avisar o usuário
            if URL_API_NOTIFICACAO_BOT and CHAVE_SECRETA_PARA_BOT:
                payload_notificacao = {
                    "chave_secreta_interna": CHAVE_SECRETA_PARA_BOT,
                    "chat_id": dados_assinatura["chat_id_usuario"],
                    "link_conteudo": dados_assinatura["link_conteudo"],
                    "nome_plano": dados_assinatura["nome_plano"]
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

# --- ROTAS DE API PARA O BOT ---

# Endpoint para o BOT registrar um usuário e uma intenção de assinatura (após seleção de plano / envio de comprovante)
@app.route('/api/bot/registrar_assinatura', methods=['POST'])
def api_bot_registrar_assinatura():
    data = request.get_json()
    if not data or data.get("chave_api_bot") != CHAVE_API_BOT:
        return jsonify({"status": "erro", "mensagem": "Chave de API inválida ou dados não enviados"}), 403

    chat_id = data.get('chat_id')
    username = data.get('username') # Pode ser None
    first_name = data.get('first_name')
    id_plano_selecionado = data.get('id_plano') # Ex: "plano_mensal_basico"
    # O status inicial será definido pelo bot dependendo do fluxo (ex: 'pendente_comprovante')
    status_pagamento_inicial = data.get('status_pagamento', 'pendente_comprovante')

    if not all([chat_id, first_name, id_plano_selecionado, status_pagamento_inicial]):
        return jsonify({"status": "erro", "mensagem": "Dados incompletos (chat_id, first_name, id_plano, status_pagamento são obrigatórios)"}), 400

    conn = get_db_connection()
    try:
        # 1. Garante que o usuário existe na tabela usuarios (INSERT OR IGNORE)
        conn.execute("INSERT OR IGNORE INTO usuarios (chat_id, username, first_name) VALUES (?, ?, ?)",
                       (chat_id, username, first_name))
        
        # 2. Insere a nova assinatura
        # Poderia haver lógica aqui para não duplicar assinaturas pendentes para o mesmo plano
        cursor = conn.execute('''
            INSERT INTO assinaturas (chat_id_usuario, id_plano_assinado, status_pagamento)
            VALUES (?, ?, ?)
        ''', (chat_id, id_plano_selecionado, status_pagamento_inicial))
        id_nova_assinatura = cursor.lastrowid # Pega o ID da assinatura recém-criada
        conn.commit()
        return jsonify({"status": "sucesso", "mensagem": "Assinatura registrada com sucesso.", "id_assinatura": id_nova_assinatura}), 201
    except sqlite3.IntegrityError as e: # Ex: id_plano não existe na tabela planos
        conn.rollback()
        return jsonify({"status": "erro", "mensagem": f"Erro de integridade: {e}. Verifique se o id_plano é válido."}), 400
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"status": "erro", "mensagem": f"Erro no banco de dados: {e}"}), 500
    finally:
        conn.close()

# Endpoint para o BOT verificar o status de uma assinatura de um usuário
@app.route('/api/bot/verificar_status', methods=['POST'])
def api_bot_verificar_status():
    data = request.get_json()
    if not data or data.get("chave_api_bot") != CHAVE_API_BOT:
        return jsonify({"status": "erro", "mensagem": "Chave de API inválida ou dados não enviados"}), 403

    chat_id = data.get('chat_id')
    id_plano_consulta = data.get('id_plano') # Opcional: se o bot quiser status de um plano específico

    if not chat_id:
        return jsonify({"status": "erro", "mensagem": "chat_id é obrigatório"}), 400

    conn = get_db_connection()
    try:
        query = '''
            SELECT a.id_plano_assinado, p.nome_exibicao, a.status_pagamento, p.link_conteudo
            FROM assinaturas a
            JOIN planos p ON a.id_plano_assinado = p.id_plano
            WHERE a.chat_id_usuario = ? 
        '''
        params = [chat_id]
        if id_plano_consulta:
            query += " AND a.id_plano_assinado = ?"
            params.append(id_plano_consulta)
        
        # Prioriza assinaturas ativas ou mais recentes se houver múltiplas
        query += " ORDER BY CASE a.status_pagamento WHEN 'aprovado_manual' THEN 1 WHEN 'pago_gateway' THEN 1 ELSE 2 END, a.data_compra DESC LIMIT 1"
        
        assinatura = conn.execute(query, tuple(params)).fetchone()
        conn.close()

        if assinatura:
            return jsonify({
                "status": "sucesso", 
                "assinatura_ativa": True, 
                "id_plano": assinatura["id_plano_assinado"],
                "nome_plano": assinatura["nome_exibicao"],
                "status_pagamento": assinatura["status_pagamento"],
                "link_conteudo": assinatura["link_conteudo"] if "aprovado" in assinatura["status_pagamento"] or "pago" in assinatura["status_pagamento"] else None
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
    todas_assinaturas_db = conn.execute('''
        SELECT a.id_assinatura, u.chat_id, u.username, u.first_name, 
               p.nome_exibicao as nome_plano, a.id_plano_assinado, a.status_pagamento, 
               a.data_compra, a.data_liberacao, u.status_usuario -- Incluindo status do usuário para info
        FROM assinaturas a
        JOIN usuarios u ON u.chat_id = a.chat_id_usuario
        JOIN planos p ON p.id_plano = a.id_plano_assinado
        ORDER BY a.data_compra DESC
    ''').fetchall()
    conn.close()

    # Processar as datas para o fuso horário local
    assinaturas_para_template = []
    for row_original in todas_assinaturas_db:
        row_modificada = dict(row_original)
        row_modificada['data_compra'] = formatar_data_local(row_modificada['data_compra'])
        if row_modificada.get('data_liberacao'):
            row_modificada['data_liberacao'] = formatar_data_local(row_modificada['data_liberacao'])
        assinaturas_para_template.append(row_modificada)

    return render_template('historico_assinaturas.html', assinaturas=assinaturas_para_template)

@app.route('/admin/reativar_usuario/<int:chat_id_usuario_para_reativar>', methods=['POST'])
def reativar_usuario(chat_id_usuario_para_reativar):
    if 'usuario_admin' not in session:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        # Atualiza o status do usuário para 'A' (Ativo)
        cursor = conn.execute("UPDATE usuarios SET status_usuario = 'A' WHERE chat_id = ? AND status_usuario = 'I'", 
                              (chat_id_usuario_para_reativar,))
        usuario_reativado = cursor.rowcount # Verifica se alguma linha foi afetada
        conn.commit()
        
        if usuario_reativado > 0:
            flash(f'Usuário com Chat ID {chat_id_usuario_para_reativar} foi REATIVADO com sucesso!', 'success')
        else:
            flash(f'Usuário com Chat ID {chat_id_usuario_para_reativar} não foi encontrado com status "Inativo" ou já estava ativo.', 'warning')

    except sqlite3.Error as e:
        if conn: # conn pode não existir se get_db_connection() falhar
            conn.rollback() 
        flash(f'Erro ao reativar usuário: {e}', 'danger')
    finally:
        if conn:
            conn.close()
            
    # Redireciona de volta para o histórico, onde a mudança será visível
    return redirect(url_for('historico_assinaturas'))       

# Endpoint para o BOT obter a lista de planos (opcional, o bot pode ter isso hardcoded)
@app.route('/api/bot/planos', methods=['GET'])
def api_bot_get_planos():
    # Adicionar verificação de chave API se quiser proteger este endpoint
    # if request.headers.get('X-API-KEY') != CHAVE_API_BOT:
    # return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 403
    conn = get_db_connection()
    planos_db = conn.execute("SELECT id_plano, nome_exibicao, preco, descricao FROM planos WHERE ativo = TRUE").fetchall() # Supondo campo 'ativo'
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
        # Atualiza o status do usuário para 'I' (Inativo)
        cursor = conn.execute("UPDATE usuarios SET status_usuario = 'I' WHERE chat_id = ?", (chat_id_usuario_para_desativar,))
        usuario_desativado = cursor.rowcount # Verifica se alguma linha foi afetada
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
def admin_planos():
    if 'usuario_admin' not in session:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    planos_db = conn.execute('SELECT id_plano, nome_exibicao, preco, descricao, link_conteudo, ativo FROM planos ORDER BY nome_exibicao').fetchall()
    conn.close()

    # Criaremos um novo template para esta página
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
            # Re-renderiza o formulário, mas idealmente manteria os dados já preenchidos
            return render_template('admin_plano_form.html', acao="Adicionar", plano=request.form) 

        descricao = request.form['descricao']
        link_conteudo = request.form['link_conteudo']
        # O checkbox 'ativo' envia 'on' se marcado, ou não envia nada se desmarcado
        ativo = 'ativo' in request.form 

        if not all([id_plano, nome_exibicao, preco, link_conteudo]): # Descrição é opcional
            flash('ID do Plano, Nome de Exibição, Preço e Link do Conteúdo são obrigatórios.', 'danger')
            return render_template('admin_plano_form.html', acao="Adicionar", plano=request.form)

        conn = get_db_connection()
        try:
            conn.execute('''
                INSERT INTO planos (id_plano, nome_exibicao, preco, descricao, link_conteudo, ativo)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (id_plano, nome_exibicao, preco, descricao, link_conteudo, ativo))
            conn.commit()
            flash(f'Plano "{nome_exibicao}" adicionado com sucesso!', 'success')
            return redirect(url_for('admin_planos'))
        except sqlite3.IntegrityError: # Ocorre se id_plano (PRIMARY KEY) já existir
            conn.rollback()
            flash(f'Erro: O ID do Plano "{id_plano}" já existe. Escolha outro ID.', 'danger')
        except sqlite3.Error as e:
            conn.rollback()
            flash(f'Erro no banco de dados ao adicionar plano: {e}', 'danger')
        finally:
            conn.close()

    # Para o método GET ou se houver erro no POST e precisarmos mostrar o form novamente
    return render_template('admin_plano_form.html', acao="Adicionar", plano=None)

@app.route('/admin/setup_planos_iniciais_uma_vez_AGORA')
def setup_planos_iniciais_agora():
    if 'usuario_admin' not in session:
        return "Não autorizado", 401
    
    conn = get_db_connection()
    cursor = conn.cursor()
    mensagens_resultado = []
    try:
        link_basico = os.getenv("GRUPO_EXCLUSIVO")
        link_premium = os.getenv("GRUPO_EXCLUSIVO")

        # Lista de planos COM a coluna 'ativo' (o último valor é para 'ativo', 1 = True)
        planos_para_inserir = [
            ('plano_mensal_basico', '🔥 Mensal Básico 🔥', 19.99, 'Plano Mensal com mais de 100 fotos e vídeos', link_basico, 1),
            ('plano_mensal_premium', '😈 Mensal Premium 😈', 39.99, 'Plano Premium com tudo incluso + VIP + Contato', link_premium, 1)
        ]

        for plano_data in planos_para_inserir:
            try:
                # Query INSERT COM a coluna 'ativo' e com 6 placeholders (?)
                cursor.execute("INSERT OR IGNORE INTO planos (id_plano, nome_exibicao, preco, descricao, link_conteudo, ativo) VALUES (?, ?, ?, ?, ?, ?)",
                               plano_data) # INSERT OR IGNORE para não dar erro se já existir
                mensagens_resultado.append(f"Plano '{plano_data[0]}' verificado/inserido.")
            except sqlite3.IntegrityError: # Embora INSERT OR IGNORE deva prevenir isso para PK
                mensagens_resultado.append(f"Plano '{plano_data[0]}' já existe (IntegrityError).")
        
        conn.commit()
        conn.close()
        return "<br>".join(mensagens_resultado) + "<br><br>Processo concluído. Remova ou comente esta rota após o uso."
    except Exception as e:
        if conn:
            conn.close()
        return f"Erro ao inserir planos: {str(e)}"

if __name__ == '__main__':
    # Porta para o Render.com (pega da variável de ambiente PORT) ou 5001 localmente
    port = int(os.getenv("PORT", 5001)) 
    app.run(debug=True, host='0.0.0.0', port=port)
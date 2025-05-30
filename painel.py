import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify # jsonify adicionado para API
from dotenv import load_dotenv

# Importar funções do nosso módulo de banco de dados
from database import get_db_connection, create_tables # Adicionado create_tables para garantir

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY_PAINEL")

USUARIO_PAINEL = os.getenv("USUARIO_PAINEL")
SENHA_PAINEL = os.getenv("SENHA_PAINEL")
CHAVE_API_BOT = os.getenv("CHAVE_PAINEL") # Renomeando para clareza, essa é a chave que o BOT usa

# Garante que as tabelas sejam criadas ao iniciar o app do painel, se não existirem.
# Isso é seguro por causa do "IF NOT EXISTS" nas queries de criação.
create_tables()

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
        SELECT a.id_assinatura, u.chat_id, u.username, u.first_name, 
               p.nome_exibicao as nome_plano, a.id_plano_assinado, a.status_pagamento, 
               a.data_compra, a.data_liberacao
        FROM assinaturas a
        JOIN usuarios u ON u.chat_id = a.chat_id_usuario
        JOIN planos p ON p.id_plano = a.id_plano_assinado
        ORDER BY a.data_compra DESC
    ''').fetchall()
    conn.close()
    
    return render_template('index.html', assinaturas=assinaturas_db)

@app.route('/logout')
def logout():
    session.pop('usuario_admin', None)
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

# Adicione esta nova rota em algum lugar do seu painel.py
@app.route('/admin/setup_planos_iniciais_uma_vez_AGORA') # Nome diferente para garantir
def setup_planos_iniciais_agora():
    if 'usuario_admin' not in session: # Protege a rota
        return "Não autorizado", 401

    conn = get_db_connection()
    cursor = conn.cursor()
    mensagens_resultado = []
    try:
        # Defina os links dos seus grupos aqui ou pegue do .env
        # É importante que GRUPO_EXCLUSIVO_BASICO e GRUPO_EXCLUSIVO_PREMIUM
        # estejam configurados nas variáveis de ambiente do seu serviço no Render.
        link_basico = os.getenv("GRUPO_EXCLUSIVO")
        link_premium = os.getenv("GRUPO_EXCLUSIVO")

        # Garanta que a tabela planos no database.py tem a coluna 'ativo'
        # Ex: ativo BOOLEAN DEFAULT TRUE

        planos_para_inserir = [
            ('plano_mensal_basico', '🔥 Mensal Básico 🔥', 19.99, 'Plano Mensal com mais de 100 fotos e vídeos', link_basico, True),
            ('plano_mensal_premium', '😈 Mensal Premium 😈', 39.99, 'Plano Premium com tudo incluso + VIP + Contato', link_premium, True)
        ]

        for plano_data in planos_para_inserir:
            try:
                cursor.execute("INSERT INTO planos (id_plano, nome_exibicao, preco, descricao, link_conteudo, ativo) VALUES (?, ?, ?, ?, ?, ?)",
                               plano_data)
                mensagens_resultado.append(f"Plano '{plano_data[0]}' inserido com sucesso.")
            except sqlite3.IntegrityError:
                mensagens_resultado.append(f"Plano '{plano_data[0]}' já existe.")

        conn.commit()
        conn.close()
        return "<br>".join(mensagens_resultado) + "<br><br>Processo concluído. Remova ou comente esta rota após o uso."
    except Exception as e:
        if conn:
            conn.close()
        return f"Erro ao inserir planos: {str(e)}"

@app.route('/aprovar_assinatura/<int:id_assinatura>', methods=['POST'])
def aprovar_assinatura(id_assinatura):
    if 'usuario_admin' not in session:
        return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 401 # Se for chamado por JS
        # return redirect(url_for('login')) # Se for form submit direto

    conn = get_db_connection()
    try:
        # Apenas muda o status. A notificação ao usuário será responsabilidade do bot após consultar status.
        # Ou o painel poderia chamar uma API no bot para notificar (mais complexo agora).
        updated_rows = conn.execute('''
            UPDATE assinaturas 
            SET status_pagamento = 'aprovado_manual', data_liberacao = CURRENT_TIMESTAMP
            WHERE id_assinatura = ? AND status_pagamento = 'pendente_comprovante'
        ''', (id_assinatura,)).rowcount
        conn.commit()
        
        if updated_rows > 0:
            flash(f'Assinatura ID {id_assinatura} aprovada manualmente!', 'success')
        else:
            flash(f'Assinatura ID {id_assinatura} não estava pendente ou não foi encontrada.', 'warning')
    except sqlite3.Error as e:
        flash(f'Erro ao aprovar assinatura: {e}', 'danger')
    finally:
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


if __name__ == '__main__':
    # Porta para o Render.com (pega da variável de ambiente PORT) ou 5001 localmente
    port = int(os.getenv("PORT", 5001)) 
    app.run(debug=True, host='0.0.0.0', port=port)
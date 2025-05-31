import sqlite3
import os

print("DEBUG: Script database.py iniciado.") # <--- NOVO PRINT

# Define o caminho do banco de dados na raiz do projeto
# Em ambas as cópias do database.py

# DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_database.db') # Linha ANTIGA
DATABASE_PATH = '/mnt/data/bot_database.db' # Linha NOVA - ajuste '/mnt/data' conforme seu ponto de montagem
print(f"DEBUG: Caminho do banco de dados definido como: {DATABASE_PATH}") # <--- NOVO PRINT

def get_db_connection():
    print("DEBUG: get_db_connection() chamada.") # <--- NOVO PRINT
    """Cria e retorna uma conexão com o banco de dados."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row # Para acessar colunas pelo nome
    print("DEBUG: Conexão com o banco de dados estabelecida.") # <--- NOVO PRINT
    return conn

def create_tables():
    print("DEBUG: create_tables() chamada.") # <--- NOVO PRINT
    """Cria as tabelas no banco de dados se elas não existirem."""
    conn = None # Inicializa conn
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print("DEBUG: Cursor criado.") # <--- NOVO PRINT

        # Tabela de Usuários (do Telegram)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                data_registro DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("DEBUG: Tabela usuarios verificada/criada.") # <--- NOVO PRINT

        

        # Tabela de Planos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS planos (
                id_plano TEXT PRIMARY KEY, 
                nome_exibicao TEXT NOT NULL,
                preco REAL NOT NULL,
                descricao TEXT,
                link_conteudo TEXT NOT NULL,
                ativo BOOLEAN DEFAULT TRUE 
            )
        ''')
        print("DEBUG: Tabela planos verificada/criada.") # <--- NOVO PRINT

        # Tabela de Assinaturas/Vendas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assinaturas (
                id_assinatura INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id_usuario INTEGER NOT NULL,
                id_plano_assinado TEXT NOT NULL,
                data_compra DATETIME DEFAULT CURRENT_TIMESTAMP,
                status_pagamento TEXT NOT NULL, 
                id_transacao_gateway TEXT, 
                data_liberacao DATETIME,
                FOREIGN KEY (chat_id_usuario) REFERENCES usuarios (chat_id),
                FOREIGN KEY (id_plano_assinado) REFERENCES planos (id_plano)
            )
        ''')
        print("DEBUG: Tabela assinaturas verificada/criada.") # <--- NOVO PRINT
        
        conn.commit()
        print("DEBUG: Commit realizado.") # <--- NOVO PRINT
        print("Tabelas verificadas/criadas com sucesso.") # <--- MENSAGEM FINAL ESPERADA
    except Exception as e:
        print(f"ERRO em create_tables: {e}") # <--- NOVO PRINT DE ERRO
    finally:
        if conn:
            conn.close()
            print("DEBUG: Conexão fechada.") # <--- NOVO PRINT

if __name__ == '__main__':
    print("DEBUG: Bloco if __name__ == '__main__' alcançado.") # <--- NOVO PRINT
    create_tables()
    print("DEBUG: create_tables() concluída a partir do bloco __main__.") # <--- NOVO PRINT

    # Comente ou remova a parte de inserir planos por enquanto para simplificar
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO planos (id_plano, nome_exibicao, preco, descricao, link_conteudo) VALUES (?, ?, ?, ?, ?)",
                        ('plano_mensal_basico', '🔥 Mensal Básico 🔥', 19.99, 'Plano Mensal com mais de 100 fotos e vídeos', os.getenv("GRUPO_EXCLUSIVO_BASICO")))
        cursor.execute("INSERT INTO planos (id_plano, nome_exibicao, preco, descricao, link_conteudo) VALUES (?, ?, ?, ?, ?)",
                        ('plano_mensal_premium', '😈 Mensal Premium 😈', 39.99, 'Plano Premium com tudo incluso + VIP + Contato', os.getenv("GRUPO_EXCLUSIVO_PREMIUM")))
        conn.commit()
        print("Planos de exemplo inseridos.")
    except sqlite3.IntegrityError:
       print("Planos de exemplo já existem ou houve um erro.")
    finally:
        if conn: # Garante que conn existe antes de tentar fechar
            conn.close()
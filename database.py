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
                data_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                 status_usuario CHAR(1) DEFAULT 'A' NOT NULL CHECK (status_usuario IN ('A', 'I'))
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

def try_add_status_usuario_column():
    """Tenta adicionar a coluna status_usuario à tabela usuarios se ela não existir."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Verifica se a coluna já existe
        cursor.execute("PRAGMA table_info(usuarios);")
        columns = [col[1] for col in cursor.fetchall()]

        if 'status_usuario' not in columns:
            print("DEBUG: Coluna 'status_usuario' não encontrada. Tentando adicionar...")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN status_usuario CHAR(1) DEFAULT 'A' NOT NULL CHECK (status_usuario IN ('A', 'I'));")
            conn.commit()
            print("DEBUG: Coluna 'status_usuario' adicionada à tabela 'usuarios'.")
        else:
            print("DEBUG: Coluna 'status_usuario' já existe na tabela 'usuarios'.")
    except sqlite3.Error as e:
        print(f"ERRO em try_add_status_usuario_column: {e}")
    finally:
        if conn:
            conn.close()
            print("DEBUG: try_add_status_usuario_column - Conexão fechada.")

def try_add_ativo_column_to_planos():
    """Tenta adicionar a coluna 'ativo' à tabela 'planos' se ela não existir."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verifica se a coluna já existe
        cursor.execute("PRAGMA table_info(planos);")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'ativo' not in columns:
            print("DEBUG: Coluna 'ativo' não encontrada na tabela 'planos'. Tentando adicionar...")
            # Adiciona a coluna com um valor padrão. Para SQLite, BOOLEAN é frequentemente INTEGER 0 ou 1.
            # DEFAULT 1 significa TRUE (ativo)
            cursor.execute("ALTER TABLE planos ADD COLUMN ativo INTEGER DEFAULT 1;") 
            conn.commit()
            print("DEBUG: Coluna 'ativo' (INTEGER DEFAULT 1) adicionada à tabela 'planos'.")
        else:
            print("DEBUG: Coluna 'ativo' já existe na tabela 'planos'.")
    except sqlite3.Error as e:
        print(f"ERRO em try_add_ativo_column_to_planos: {e}")
    finally:
        if conn:
            conn.close()
            print("DEBUG: try_add_ativo_column_to_planos - Conexão fechada.")

# No final do database.py, dentro do if __name__ == '__main__':
if __name__ == '__main__':
    print("DEBUG: Bloco if __name__ == '__main__' em database.py alcançado.")
    create_tables() # Garante que as tabelas base existem (aqui 'planos' já tem 'ativo' na definição)
    try_add_status_usuario_column()
    try_add_ativo_column_to_planos() # <<< ADICIONE A CHAMADA AQUI
    print("DEBUG: Funções de setup de database.py concluídas a partir do bloco __main__.")
    
    # Ajuste a inserção de planos de exemplo para INCLUIR o valor para 'ativo' (6ª coluna)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Seus links de GRUPO_EXCLUSIVO...
        link_basico = os.getenv("GRUPO_EXCLUSIVO")
        link_premium = os.getenv("GRUPO_EXCLUSIVO")

        # Inserindo com 6 valores, incluindo 'ativo' (o último 'True' ou '1')
        cursor.execute("INSERT OR IGNORE INTO planos (id_plano, nome_exibicao, preco, descricao, link_conteudo, ativo) VALUES (?, ?, ?, ?, ?, ?)",
                       ('plano_mensal_basico', '🔥 Mensal Básico 🔥', 19.99, 'Plano Mensal com mais de 100 fotos e vídeos', link_basico, 1)) # 1 para True
        cursor.execute("INSERT OR IGNORE INTO planos (id_plano, nome_exibicao, preco, descricao, link_conteudo, ativo) VALUES (?, ?, ?, ?, ?, ?)",
                       ('plano_mensal_premium', '😈 Mensal Premium 😈', 39.99, 'Plano Premium com tudo incluso + VIP + Contato', link_premium, 1)) # 1 para True
        conn.commit()
        print("Planos de exemplo inseridos/verificados (com coluna ativo).")
    except sqlite3.IntegrityError:
        print("Planos de exemplo já existem ou houve um erro de integridade.")
    except Exception as e_planos:
        print(f"Erro ao inserir planos de exemplo: {e_planos}")
    finally:
        if conn:
            conn.close()            


if __name__ == '__main__':
    print("DEBUG: Bloco if __name__ == '__main__' alcançado.") # <--- NOVO PRINT
    create_tables()
    try_add_status_usuario_column() # Tenta adicionar a coluna se o DB já existia sem ela
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
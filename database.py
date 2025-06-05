import sqlite3
import os

print("DEBUG: Script database.py iniciado.")

# Define o caminho do banco de dados na raiz do projeto
# Em ambas as cópias do database.py

DATABASE_PATH = '/mnt/data/bot_database.db'
print(f"DEBUG: Caminho do banco de dados definido como: {DATABASE_PATH}") 

def get_db_connection():
    print("DEBUG: get_db_connection() chamada.")
    """Cria e retorna uma conexão com o banco de dados."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row # Para acessar colunas pelo nome
    print("DEBUG: Conexão com o banco de dados estabelecida.") 
    return conn

def create_tables():
    print("DEBUG: create_tables() chamada.") 
    """Cria as tabelas no banco de dados se elas não existirem."""
    conn = None # Inicializa conn
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print("DEBUG: Cursor criado.") 

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
        print("DEBUG: Tabela usuarios verificada/criada.") 

        

        # Tabela de Planos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS planos (
                id_plano TEXT PRIMARY KEY, 
                nome_exibicao TEXT NOT NULL,
                preco REAL NOT NULL,
                descricao TEXT,
                link_conteudo TEXT NOT NULL,
                ativo BOOLEAN DEFAULT TRUE,
                duracao_dias INTEGER DEFAULT NULL -- <<< NOVA COLUNA: NULL para vitalício, >0 para dias
            )
        ''')
        print("DEBUG: Tabela planos (com duracao_dias) verificada/criada.")
    

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
                data_fim DATETIME DEFAULT NULL, -- <<< NOVA COLUNA: NULL para vitalício ou indefinido
                FOREIGN KEY (chat_id_usuario) REFERENCES usuarios (chat_id),
                FOREIGN KEY (id_plano_assinado) REFERENCES planos (id_plano)
            )
        ''')
        print("DEBUG: Tabela assinaturas (com data_fim) verificada/criada.")
        
        conn.commit()
        print("DEBUG: Commit realizado.") 
        print("Tabelas verificadas/criadas com sucesso.")
    except Exception as e:
        print(f"ERRO em create_tables: {e}") 
    finally:
        if conn:
            conn.close()
            print("DEBUG: Conexão fechada.") 

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

def try_add_duracao_dias_to_planos():
    """Tenta adicionar a coluna 'duracao_dias' à tabela 'planos' se ela não existir."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(planos);")
        columns = [col[1] for col in cursor.fetchall()]
        if 'duracao_dias' not in columns:
            print("DEBUG: Coluna 'duracao_dias' não encontrada na tabela 'planos'. Tentando adicionar...")
            cursor.execute("ALTER TABLE planos ADD COLUMN duracao_dias INTEGER DEFAULT NULL;")
            conn.commit()
            print("DEBUG: Coluna 'duracao_dias' (INTEGER DEFAULT NULL) adicionada à tabela 'planos'.")
        else:
            print("DEBUG: Coluna 'duracao_dias' já existe na tabela 'planos'.")
    except sqlite3.Error as e:
        print(f"ERRO em try_add_duracao_dias_to_planos: {e}")
    finally:
        if conn:
            conn.close()
            print("DEBUG: try_add_duracao_dias_to_planos - Conexão fechada.")       

def try_add_data_fim_to_assinaturas():
    """Tenta adicionar a coluna 'data_fim' à tabela 'assinaturas' se ela não existir."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(assinaturas);")
        columns = [col[1] for col in cursor.fetchall()]
        if 'data_fim' not in columns:
            print("DEBUG: Coluna 'data_fim' não encontrada na tabela 'assinaturas'. Tentando adicionar...")
            cursor.execute("ALTER TABLE assinaturas ADD COLUMN data_fim DATETIME DEFAULT NULL;")
            conn.commit()
            print("DEBUG: Coluna 'data_fim' (DATETIME DEFAULT NULL) adicionada à tabela 'assinaturas'.")
        else:
            print("DEBUG: Coluna 'data_fim' já existe na tabela 'assinaturas'.")
    except sqlite3.Error as e:
        print(f"ERRO em try_add_data_fim_to_assinaturas: {e}")
    finally:
        if conn:
            conn.close()
                             

if __name__ == '__main__':
    print("DEBUG: Bloco if __name__ == '__main__' em database.py alcançado.")
    create_tables() # Garante que as tabelas base existem (aqui 'planos' já tem 'ativo' na definição)
    try_add_status_usuario_column()
    try_add_ativo_column_to_planos() 
    try_add_duracao_dias_to_planos()
    print("DEBUG: Funções de setup de database.py concluídas a partir do bloco __main__.")
    
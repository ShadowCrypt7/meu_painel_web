import os
import json
from flask import Flask, render_template, request, redirect, url_for, session
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY_PAINEL")

USUARIO_PAINEL = os.getenv("USUARIO_PAINEL")
SENHA_PAINEL = os.getenv("SENHA_PAINEL")
CHAVE_PAINEL = os.getenv("CHAVE_PAINEL")

# 📄 Funções para manipular JSON
def carregar_usuarios():
    try:
        with open('usuarios_aprovados.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return []

def salvar_usuarios(usuarios):
    with open('usuarios_aprovados.json', 'w') as file:
        json.dump(usuarios, file, indent=4)


# 🔐 Rotas do Painel
@app.route('/')
def home():
    if 'usuario' in session:
        usuarios = carregar_usuarios()
        return render_template('index.html', usuarios=usuarios)
    return redirect(url_for('/login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['username']
        senha = request.form['password']
        if usuario == USUARIO_PAINEL and senha == SENHA_PAINEL:
            session['usuario'] = usuario
            return redirect(url_for('/home'))
        return "❌ Login inválido!"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('/login'))

@app.route('/adicionar', methods=['POST'])
def adicionar():
    if 'usuario' not in session:
        return redirect(url_for('/login'))

    username = request.form['username']
    chat_id = request.form['chat_id']

    usuarios = carregar_usuarios()
    usuarios.append({'username': username, 'chat_id': chat_id})
    salvar_usuarios(usuarios)

    return redirect(url_for('/home'))

@app.route('/remover/<username>', methods=['POST'])
def remover(username):
    if 'usuario' not in session:
        return redirect(url_for('/login'))

    usuarios = carregar_usuarios()
    usuarios = [u for u in usuarios if u['username'] != username]
    salvar_usuarios(usuarios)

    return redirect(url_for('/home'))


# 🔗 API - Adiciona usuário via Bot
@app.route('/api/adicionar', methods=['POST'])
def api_adicionar():
    data = request.get_json()

    if not data:
        return {"status": "erro", "mensagem": "JSON não enviado"}, 400

    if data.get("chave_secreta") != CHAVE_PAINEL:
        return {"status": "erro", "mensagem": "Chave inválida"}, 403

    username = data.get('username', '').strip()
    chat_id = data.get('chat_id', '').strip()

    if not username or not chat_id:
        return {"status": "erro", "mensagem": "Dados incompletos"}, 400
    
    if not chat_id.isdigit():
        return {"status": "erro", "mensagem": "chat_id inválido"}, 400

    usuarios = carregar_usuarios()

    if any(u['username'] == username for u in usuarios):
        return {"status": "erro", "mensagem": "Usuário já existe"}, 409

    usuarios.append({'username': username, 'chat_id': chat_id})
    salvar_usuarios(usuarios)

    return {"status": "sucesso", "mensagem": "Usuário adicionado"}, 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

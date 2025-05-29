from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY_PAINEL")

USUARIO_PAINEL = os.getenv("USUARIO_PAINEL")
SENHA_PAINEL = os.getenv("SENHA_PAINEL")
ARQUIVO = 'usuarios_aprovados.json'

def carregar_usuarios():
    if os.path.exists(ARQUIVO):
        try:
            with open(ARQUIVO, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def salvar_usuarios(usuarios):
    with open(ARQUIVO, 'w') as f:
        json.dump(usuarios, f, indent=4)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logado'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        senha = request.form['password']
        if username == USUARIO_PAINEL and senha == SENHA_PAINEL:
            session['logado'] = True
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logado', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    aprovados = carregar_usuarios()
    return render_template('index.html', aprovados=aprovados)

@app.route('/adicionar', methods=['POST'])
@login_required
def adicionar():
    username = request.form['username'].strip()
    chat_id = request.form['chat_id'].strip()
    if not username or not chat_id:
        flash('Preencha todos os campos!', 'warning')
        return redirect(url_for('index'))
    aprovados = carregar_usuarios()
    if any(u['username'] == username for u in aprovados):
        flash('Usuário já está na lista!', 'warning')
        return redirect(url_for('index'))
    aprovados.append({'username': username, 'chat_id': chat_id})
    salvar_usuarios(aprovados)
    flash('Usuário adicionado com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/remover/<username>', methods=['POST'])
@login_required
def remover(username):
    aprovados = carregar_usuarios()
    aprovados = [u for u in aprovados if u['username'] != username]
    salvar_usuarios(aprovados)
    flash('Usuário removido com sucesso!', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

import sqlite3
import os
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "park_pro_2026_completo"
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def obter_conexao():
    conn = sqlite3.connect("estacionamento.db")
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_banco():
    conn = obter_conexao()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, senha TEXT NOT NULL
    )''')
    try:
        cursor.execute("INSERT INTO usuarios (email, senha) VALUES (?, ?)", 
                       ('Jaymepinheiro7854@gmail.com', '21971767894'))
        conn.commit()
    except sqlite3.IntegrityError:
        pass

    cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes (
        id INTEGER PRIMARY KEY, nome TEXT, cnpj TEXT, endereco TEXT, telefone TEXT, horario TEXT, mensagem TEXT, impressora_status TEXT, valor_diaria REAL DEFAULT 50.0, valor_van REAL DEFAULT 30.0, valor_pernoite REAL DEFAULT 40.0, logo TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS anuncios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS veiculos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, placa TEXT NOT NULL, modelo TEXT, cor TEXT, valor REAL DEFAULT 10.0, hora_entrada TEXT, hora_saida TEXT, valor_total REAL, status TEXT DEFAULT 'ATIVO'
    )''')
    conn.commit()
    conn.close()

def get_dados():
    conn = obter_conexao()
    cfg = conn.execute("SELECT * FROM configuracoes WHERE id=1").fetchone()
    anuncios = conn.execute("SELECT * FROM anuncios").fetchall()
    ativos = conn.execute("SELECT * FROM veiculos WHERE status='ATIVO' ORDER BY id DESC").fetchall()
    concluidos = conn.execute("SELECT * FROM veiculos WHERE status='FINALIZADO' ORDER BY id DESC").fetchall()
    usuarios = conn.execute("SELECT * FROM usuarios").fetchall()
    total_geral = conn.execute("SELECT COUNT(*) FROM veiculos").fetchone()[0]
    num_talao = f"{total_geral + 1:04d}"
    conn.close()
    return cfg, anuncios, ativos, concluidos, num_talao, usuarios

HTML_LOGIN = """
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Login - NovaPark Pro</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head>
<body class="bg-light d-flex align-items-center justify-content-center vh-100"><div class="card shadow p-4" style="width: 100%; max-width: 400px;"><h3 class="text-center mb-4 fw-bold text-primary">🚗 NovaPark Pro</h3><form action="/fazer_login" method="POST"><div class="mb-3"><label>E-mail</label><input type="email" name="email" class="form-control" required></div><div class="mb-3"><label>Senha</label><input type="password" name="senha" class="form-control" required></div><button type="submit" class="btn btn-primary w-100">Entrar</button></form></div></body></html>
"""

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Painel - NovaPark Pro</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head>
<body class="bg-light"><div class="container mt-3"><div class="row"><div class="col-12 text-center mb-3"><h3>Painel de Controle</h3><a href="/logout" class="btn btn-danger btn-sm">Sair</a></div><div class="col-6"><button class="btn btn-success w-100 p-3" data-bs-toggle="modal" data-bs-target="#mEntrada">ENTRADA</button></div><div class="col-6"><button class="btn btn-danger w-100 p-3" data-bs-toggle="modal" data-bs-target="#mSaida">SAÍDA</button></div></div></div>
<div class="modal fade" id="mEntrada" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body">
<form action="/entrada" method="POST"><label>Placa:</label><input name="placa" class="form-control mb-2" required>
<label>Modelo:</label><input name="modelo" class="form-control mb-2" required><label>Cor:</label><input name="cor" class="form-control mb-2" required>
<label>Valor:</label><input name="valor" type="number" step="0.01" class="form-control mb-3" required>
<button class="btn btn-success w-100">Registrar</button></form></div></div></div></div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script></body></html>
"""

@app.route('/')
def login(): return render_template_string(HTML_LOGIN)

@app.route('/fazer_login', methods=['POST'])
def fazer_login():
    email = request.form.get('email')
    senha = request.form.get('senha')
    conn = obter_conexao()
    user = conn.execute("SELECT * FROM usuarios WHERE email=? AND senha=?", (email, senha)).fetchone()
    conn.close()
    if user:
        session['email'] = email
        return redirect(url_for('dashboard'))
    return "Login falhou"

@app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect(url_for('login'))
    cfg, anuncios, ativos, concluidos, talao, usuarios = get_dados()
    return render_template_string(HTML_DASHBOARD, cfg=cfg, ativos=ativos, talao_atual=talao)

@app.route('/entrada', methods=['POST'])
def entrada():
    if 'email' not in session: return redirect(url_for('login'))
    cfg, _, _, _, _, _ = get_dados()
    placa = request.form.get('placa', '').upper().strip()
    modelo = request.form.get('modelo', '')
    cor = request.form.get('cor', '')
    
    try:
        valor = float(request.form.get('valor', cfg['valor_diaria']))
    except ValueError:
        valor = float(cfg['valor_diaria'])
        
    hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = obter_conexao()
    conn.execute("INSERT INTO veiculos (placa, modelo, cor, valor, hora_entrada, status) VALUES (?, ?, ?, ?, ?, ?)", 
                 (placa, modelo, cor, valor, hora, 'ATIVO'))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('email', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    inicializar_banco()
    app.run(host='0.0.0.0', port=5000)

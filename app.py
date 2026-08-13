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
    
    # FORÇAR CRIAÇÃO DO USUÁRIO ADMINISTRATIVO
    try:
        cursor.execute("INSERT INTO usuarios (email, senha) VALUES (?, ?)", 
                       ('Jaymepinheiro7854@gmail.com', '21971767894'))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # Já existe, não faz nada

    cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes (
        id INTEGER PRIMARY KEY, nome TEXT, cnpj TEXT, endereco TEXT, telefone TEXT, horario TEXT, mensagem TEXT, impressora_status TEXT, valor_diaria REAL DEFAULT 50.0, valor_van REAL DEFAULT 30.0, valor_pernoite REAL DEFAULT 40.0, logo TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS anuncios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS veiculos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, placa TEXT NOT NULL, modelo TEXT, cor TEXT, valor REAL DEFAULT 10.0, hora_entrada TEXT, hora_saida TEXT, valor_total REAL, status TEXT DEFAULT 'ATIVO'
    )''')
    
    cols_c = [col[1] for col in cursor.execute("PRAGMA table_info(configuracoes)").fetchall()]
    if 'valor_diaria' not in cols_c: cursor.execute("ALTER TABLE configuracoes ADD COLUMN valor_diaria REAL DEFAULT 50.0")
    if 'valor_van' not in cols_c: cursor.execute("ALTER TABLE configuracoes ADD COLUMN valor_van REAL DEFAULT 30.0")
    if 'valor_pernoite' not in cols_c: cursor.execute("ALTER TABLE configuracoes ADD COLUMN valor_pernoite REAL DEFAULT 40.0")
    if 'impressora_status' not in cols_c: cursor.execute("ALTER TABLE configuracoes ADD COLUMN impressora_status TEXT")
    if 'logo' not in cols_c: cursor.execute("ALTER TABLE configuracoes ADD COLUMN logo TEXT")

    cols_v = [col[1] for col in cursor.execute("PRAGMA table_info(veiculos)").fetchall()]
    if 'valor' not in cols_v: cursor.execute("ALTER TABLE veiculos ADD COLUMN valor REAL DEFAULT 10.0")
    if 'modelo' not in cols_v: cursor.execute("ALTER TABLE veiculos ADD COLUMN modelo TEXT")
    if 'cor' not in cols_v: cursor.execute("ALTER TABLE veiculos ADD COLUMN cor TEXT")
    if 'valor_total' not in cols_v: cursor.execute("ALTER TABLE veiculos ADD COLUMN valor_total REAL")
    if 'hora_saida' not in cols_v: cursor.execute("ALTER TABLE veiculos ADD COLUMN hora_saida TEXT")
    if 'status' not in cols_v: cursor.execute("ALTER TABLE veiculos ADD COLUMN status TEXT DEFAULT 'ATIVO'")

    cursor.execute("SELECT COUNT(*) FROM configuracoes")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO configuracoes (id, nome, cnpj, endereco, telefone, horario, mensagem, impressora_status, valor_diaria, valor_van, valor_pernoite, logo) VALUES (1, 'NovaPark Pro', '00.000.000/0001-00', 'Rua Exemplo, 123', '(21) 99999-9999', '07:00-22:00', 'Seja Bem-Vindo!', 'Thermer Bluetooth', 50.0, 30.0, 40.0, '')")

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
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - NovaPark Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>.eye-btn { cursor: pointer; position: absolute; right: 15px; top: 35px; }</style>
</head>
<body class="bg-light d-flex align-items-center justify-content-center vh-100">
    <div class="card shadow p-4" style="width: 100%; max-width: 400px;">
        <h3 class="text-center mb-4 fw-bold text-primary">🚗 NovaPark Pro</h3>
        <form action="/fazer_login" method="POST">
            <div class="mb-3"><label class="form-label">E-mail</label><input type="email" name="email" class="form-control" required></div>
            <div class="mb-3 position-relative">
                <label class="form-label">Senha</label>
                <input type="password" name="senha" id="senhaLogin" class="form-control" required>
                <span class="eye-btn" onclick="let s=document.getElementById('senhaLogin'); s.type=(s.type=='password'?'text':'password');">👁️</span>
            </div>
            <button type="submit" class="btn btn-primary w-100 mb-2">Entrar</button>
        </form>
    </div>
</body>
</html>
"""

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Painel - NovaPark Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    <script src="https://unpkg.com/html5-qrcode"></script>
    <style>
        .btn-grid { height: 75px; font-weight: bold; color: white; display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: 6px; border: none; width: 100%; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        @media print { body * { visibility: hidden; } #printableArea, #printableArea * { visibility: visible; } #printableArea { position: absolute; left: 0; top: 0; width: 100%; font-family: monospace; } }
    </style>
</head>
<body class="bg-light">
    <div style="background-color: #d35400; color: white; text-align: center; padding: 8px; font-size: 14px; font-weight: bold; display: flex; justify-content: center; align-items: center; gap: 10px;">
        {% if cfg.logo %}<img src="{{ cfg.logo }}" alt="Logo" style="max-height: 25px; max-width: 100px; object-fit: contain; background: white; padding: 2px; border-radius: 3px;">{% else %}🅿️ {{ cfg.nome }}{% endif %}
        | <a href="/logout" class="text-white text-decoration-underline">Sair</a>
    </div>
    <div class="container mt-3">
        <div class="row"><div class="col-6"><button class="btn-grid bg-success" data-bs-toggle="modal" data-bs-target="#mEntrada">📥 ENTRADA</button></div>
        <div class="col-6"><button class="btn-grid bg-danger" data-bs-toggle="modal" data-bs-target="#mSaida">📤 SAÍDA</button></div>
        <div class="col-6"><button class="btn-grid bg-secondary" data-bs-toggle="modal" data-bs-target="#mPatio">🅿️ PÁTIO</button></div>
        <div class="col-6"><button class="btn-grid" style="background-color: #34495e;" data-bs-toggle="modal" data-bs-target="#mConfig">⚙️ CONFIG</button></div></div>
    </div>
    
    <!-- MODAIS E ROTAS CONTINUAM IGUAIS AO SEU CÓDIGO ORIGINAL ... -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ... [Mantenha aqui todas as rotas (entrada, saida, salvar_config, etc) do seu arquivo original] ...

if __name__ == '__main__':
    inicializar_banco()
    app.run(host='0.0.0.0', port=5000)

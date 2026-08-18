import os
import sqlite3
from datetime import datetime
from flask import Flask, redirect, render_template_string, request, session, url_for

app = Flask(__name__)
app.secret_key = "novapark_secret_key_segura"

DB_NAME = "estacionamento.db"


def init_db():
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            valor_hora REAL,
            tolerancia INTEGER,
            vagas INTEGER
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS veiculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placa TEXT,
            entrada TEXT,
            saida TEXT,
            valor_pago REAL,
            status TEXT
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS caixa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            descricao TEXT,
            tipo TEXT,
            valor REAL
        )
    """)
  cursor.execute("SELECT COUNT(*) FROM config")
  if cursor.fetchone()[0] == 0:
    cursor.execute(
        "INSERT INTO config (nome, valor_hora, tolerancia, vagas) VALUES (?, ?,"
        " ?, ?)",
        ("J manfrenate estacionamento", 10.0, 15, 50),
    )
  conn.commit()
  conn.close()


init_db()

# --- TEMPLATES HTML ---
HTML_LOGIN = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - NovaPark Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-dark d-flex align-items-center justify-content-center vh-100">
    <div class="card shadow p-4" style="width: 100%; max-width: 400px;">
        <h3 class="text-center mb-4 text-primary">🚗 NovaPark Pro</h3>
        {% if erro %}
            <div class="alert alert-danger py-2">{{ erro }}</div>
        {% endif %}
        <form method="POST">
            <div class="mb-3">
                <label class="form-label">Senha de Acesso</label>
                <input type="password" name="senha" class="form-control" required autofocus>
            </div>
            <button type="submit" class="btn btn-primary w-100">Entrar</button>
        </form>
    </div>
</body>
</html>
"""

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ config[1] }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body class="bg-dark text-light">
    <nav class="navbar navbar-dark bg-secondary shadow-sm px-3">
        <span class="navbar-brand mb-0 h1"><i class="fas fa-parking"></i> {{ config[1] }}</span>
        <a href="/logout" class="btn btn-danger btn-sm">Sair</a>
    </nav>

    <div class="container my-4" style="max-width: 600px;">
        <!-- Bloco Superior de Resumo -->
        <div class="row g-2 mb-3">
            <div class="col-6">
                <div class="card bg-light text-dark p-3 text-center shadow-sm">
                    <small class="text-muted">Vagas: <strong>{{ config[4] }}</strong></small>
                    <hr class="my-1">
                    <span class="text-danger fw-bold">Nº 000{{ veiculos_ativos|length + 1 }}</span>
                </div>
            </div>
            <div class="col-6">
                <div class="card bg-secondary text-light p-3 text-center shadow-sm d-flex justify-content-center">
                    <span>Ativos: <strong>{{ veiculos_ativos|length }}</strong> | Caixa: <strong>R$ {{ "%.2f"|format(caixa_total) }}</strong></span>
                </div>
            </div>
        </div>

        <!-- Botões de Acesso Principal -->
        <div class="d-grid gap-3">
            <a href="/nova_entrada" class="btn btn-success btn-lg py-3 text-start px-4 shadow"><i class="fas fa-sign-in-alt me-2"></i> **ENTRADA**</a>
            <a href="/patio" class="btn btn-secondary btn-lg py-3 text-start px-4 shadow"><i class="fas fa-car me-2"></i> **PÁTIO** ({{ veiculos_ativos|length }})</a>
            <a href="/caixa" class="btn btn-warning btn-lg py-3 text-start px-4 text-dark shadow"><i class="fas fa-cash-register me-2"></i> **CAIXA**</a>
            <a href="/config" class="btn btn-dark btn-lg py-3 text-start px-4 border shadow"><i class="fas fa-cog me-2"></i> **CONFIG**</a>
        </div>
    </div>
</body>
</html>
"""

HTML_ENTRADA = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nova Entrada</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://unpkg.com/html5-qrcode" type="text/javascript"></script>
</head>
<body class="bg-dark text-light">
    <div class="container my-5" style="max-width: 500px;">
        <div class="card bg-secondary text-light p-4 shadow">
            <h3 class="mb-3 text-success">Registrar Entrada</h3>
            <form method="POST" class="mb-3">
                <div class="mb-3">
                    <label class="form-label">Placa do Veículo</label>
                    <input type="text" name="placa" class="form-control text-uppercase" placeholder="Ex: ABC-1234" required autofocus>
                </div>
                <button type="submit" class="btn btn-success w-100">Cadastrar Entrada</button>
            </form>
            <hr>
            <button class="btn btn-dark mb-3" onclick="initScanner()">Ler QR Code (Câmera)</button>
            <div id="reader" style="width: 100%;"></div>
            <a href="/dashboard" class="btn btn-outline-light mt-3">Voltar ao Painel</a>
        </div>
    </div>
    <script>
        function initScanner() {
            const scanner = new Html5QrcodeScanner("reader", { fps: 10, qrbox: 250 });
            scanner.render((decodedText) => {
                window.location.href = "/nova_entrada?placa=" + encodeURIComponent(decodedText);
            }, (error) => {});
        }
    </script>
</body>
</html>
"""

HTML_PATIO = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pátio - Veículos Ativos</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-dark text-light">
    <div class="container my-4" style="max-width: 600px;">
        <h3>Veículos no Pátio</h3>
        <hr>
        <div class="list-group">
            {% for v in veiculos %}
            <div class="list-group-item bg-secondary text-light d-flex justify-content-between align-items-center mb-2">
                <div>
                    <h5 class="mb-1 text-warning">Placa: {{ v[1] }}</h5>
                    <small>Entrada: {{ v[2] }}</small>
                </div>
                <a href="/saida/{{ v[0] }}" class="btn btn-danger btn-sm">Dar Saída</a>
            </div>
            {% else %}
            <p class="text-muted">Nenhum veículo estacionado no momento.</p>
            {% endfor %}
        </div>
        <a href="/dashboard" class="btn btn-light mt-3">Voltar</a>
    </div>
</body>
</html>
"""

HTML_SAIDA = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Saída de Veículo</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-dark text-light">
    <div class="container my-5" style="max-width: 450px;">
        <div class="card bg-secondary text-light p-4 shadow">
            <h3>Comprovante de Saída</h3>
            <hr>
            <p><strong>Placa:</strong> {{ veiculo[1] }}</p>
            <p><strong>Entrada:</strong> {{ veiculo[2] }}</p>
            <p><strong>Saída:</strong> {{ saida_str }}</p>
            <p><strong>Tempo:</strong> {{ tempo_horas|round(2) }} horas</p>
            <h4 class="text-warning text-center my-3">Total: R$ {{ "%.2f"|format(valor_a_pagar) }}</h4>
            <form action="/finalizar_saida/{{ veiculo[0] }}" method="POST">
                <input type="hidden" name="valor" value="{{ valor_a_pagar }}">
                <button type="submit" class="btn btn-success w-100 mb-2">Confirmar Pagamento</button>
            </form>
            <a href="/patio" class="btn btn-outline-light w-100">Cancelar</a>
        </div>
    </div>
</body>
</html>
"""

HTML_CAIXA = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Extrato do Caixa</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-dark text-light">
    <div class="container my-4" style="max-width: 600px;">
        <h3>Movimentações do Caixa</h3>
        <h4 class="text-success">Total Arrecadado: R$ {{ "%.2f"|format(total) }}</h4>
        <hr>
        <ul class="list-group mb-3">
            {% for c in caixa %}
            <li class="list-group-item bg-secondary text-light d-flex justify-content-between align-items-center">
                <span>{{ c[1] }} - {{ c[2] }}</span>
                <span class="badge bg-success">R$ {{ "%.2f"|format(c[4]) }}</span>
            </li>
            {% else %}
            <p class="text-muted">Nenhuma movimentação registrada.</p>
            {% endfor %}
        </ul>
        <a href="/dashboard" class="btn btn-light">Voltar</a>
    </div>
</body>
</html>
"""

HTML_CONFIG = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Configurações</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-dark text-light">
    <div class="container my-5" style="max-width: 500px;">
        <div class="card bg-secondary text-light p-4 shadow">
            <h3 class="mb-3">Configurações</h3>
            <form method="POST">
                <div class="mb-3">
                    <label class="form-label">Nome do Estacionamento</label>
                    <input type="text" name="nome" class="form-control" value="{{ config[1] }}" required>
                </div>
                <div class="mb-3">
                    <label class="form-label">Valor por Hora (R$)</label>
                    <input type="number" step="0.01" name="valor_hora" class="form-control" value="{{ config[2] }}" required>
                </div>
                <div class="mb-3">
                    <label class="form-label">Tolerância (min)</label>
                    <input type="number" name="tolerancia" class="form-control" value="{{ config[3] }}" required>
                </div>
                <div class="mb-3">
                    <label class="form-label">Vagas Totais</label>
                    <input type="number" name="vagas" class="form-control" value="{{ config[4] }}" required>
                </div>
                <button type="submit" class="btn btn-primary w-100">Salvar Alterações</button>
            </form>
            <a href="/dashboard" class="btn btn-outline-light mt-3 w-100">Voltar</a>
        </div>
    </div>
</body>
</html>
"""


# --- ROTAS ---
@app.route("/", methods=["GET", "POST"])
def login():
  erro = None
  if request.method == "POST":
    if request.form.get("senha") == "admin123":
      session["user"] = "admin"
      return redirect(url_for("dashboard"))
    else:
      erro = "Senha incorreta!"
  return render_template_string(HTML_LOGIN, erro=erro)


@app.route("/logout")
def logout():
  session.pop("user", None)
  return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
  if "user" not in session:
    return redirect(url_for("login"))
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute("SELECT * FROM config WHERE id=1")
  config = cursor.fetchone()
  cursor.execute(
      "SELECT id, placa, entrada FROM veiculos WHERE status='ativo'"
  )
  veiculos_ativos = cursor.fetchall()
  cursor.execute("SELECT SUM(valor) FROM caixa WHERE tipo='entrada'")
  res = cursor.fetchone()[0]
  caixa_total = res if res else 0.0
  conn.close()
  return render_template_string(
      HTML_DASHBOARD,
      config=config,
      veiculos_ativos=veiculos_ativos,
      caixa_total=caixa_total,
  )


@app.route("/nova_entrada", methods=["GET", "POST"])
def nova_entrada():
  if "user" not in session:
    return redirect(url_for("login"))
  placa = request.form.get("placa") or request.args.get("placa")
  if placa:
    placa = placa.upper().strip()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO veiculos (placa, entrada, status) VALUES (?, ?, 'ativo')",
        (placa, agora),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("patio"))
  return render_template_string(HTML_ENTRADA)


@app.route("/patio")
def patio():
  if "user" not in session:
    return redirect(url_for("login"))
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute(
      "SELECT id, placa, entrada FROM veiculos WHERE status='ativo'"
  )
  veiculos = cursor.fetchall()
  conn.close()
  return render_template_string(HTML_PATIO, veiculos=veiculos)


@app.route("/saida/<int:id>")
def saida(id):
  if "user" not in session:
    return redirect(url_for("login"))
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute("SELECT * FROM veiculos WHERE id=?", (id,))
  veiculo = cursor.fetchone()
  cursor.execute("SELECT * FROM config WHERE id=1")
  config = cursor.fetchone()
  conn.close()

  dt_entrada = datetime.strptime(veiculo[2], "%Y-%m-%d %H:%M:%S")
  dt_saida = datetime.now()
  diff_horas = (dt_saida - dt_entrada).total_seconds() / 3600.0
  valor_a_pagar = max(diff_horas * config[2], config[2] / 2)
  saida_str = dt_saida.strftime("%Y-%m-%d %H:%M:%S")

  return render_template_string(
      HTML_SAIDA,
      veiculo=veiculo,
      saida_str=saida_str,
      tempo_horas=diff_horas,
      valor_a_pagar=valor_a_pagar,
  )


@app.route("/finalizar_saida/<int:id>", methods=["POST"])
def finalizar_saida(id):
  if "user" not in session:
    return redirect(url_for("login"))
  valor = float(request.form.get("valor", 0))
  saida_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  data_hoje = datetime.now().strftime("%Y-%m-%d")

  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute(
      "UPDATE veiculos SET saida=?, valor_pago=?, status='finalizado' WHERE"
      " id=?",
      (saida_str, valor, id),
  )
  cursor.execute(
      "INSERT INTO caixa (data, descricao, tipo, valor) VALUES (?, ?,"
      " 'entrada', ?)",
      (data_hoje, f"Ticket #{id}", valor),
  )
  conn.commit()
  conn.close()
  return redirect(url_for("patio"))


@app.route("/caixa")
def caixa():
  if "user" not in session:
    return redirect(url_for("login"))
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute("SELECT * FROM caixa")
  caixa = cursor.fetchall()
  cursor.execute("SELECT SUM(valor) FROM caixa WHERE tipo='entrada'")
  res = cursor.fetchone()[0]
  total = res if res else 0.0
  conn.close()
  return render_template_string(HTML_CAIXA, caixa=caixa, total=total)


@app.route("/config", methods=["GET", "POST"])
def config():
  if "user" not in session:
    return redirect(url_for("login"))
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  if request.method == "POST":
    nome = request.form.get("nome")
    valor_hora = float(request.form.get("valor_hora"))
    tolerancia = int(request.form.get("tolerancia"))
    vagas = int(request.form.get("vagas"))
    cursor.execute(
        "UPDATE config SET nome=?, valor_hora=?, tolerancia=?, vagas=? WHERE"
        " id=1",
        (nome, valor_hora, tolerancia, vagas),
    )
    conn.commit()
  cursor.execute("SELECT * FROM config WHERE id=1")
  config = cursor.fetchone()
  conn.close()
  return render_template_string(HTML_CONFIG, config=config)


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=True)


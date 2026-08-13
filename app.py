
import sqlite3
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
    cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes (
        id INTEGER PRIMARY KEY, nome TEXT, cnpj TEXT, endereco TEXT, telefone TEXT, horario TEXT, mensagem TEXT, impressora_status TEXT, valor_diaria REAL DEFAULT 50.0, valor_van REAL DEFAULT 30.0, valor_pernoite REAL DEFAULT 40.0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS anuncios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS veiculos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, placa TEXT NOT NULL, modelo TEXT, cor TEXT, valor REAL DEFAULT 10.0, hora_entrada TEXT, hora_saida TEXT, valor_total REAL, status TEXT DEFAULT 'ATIVO'
    )''')
    
    cols_c = [col[1] for col in cursor.execute("PRAGMA table_info(configuracoes)").fetchall()]
    if 'valor_diaria' not in cols_c:
        cursor.execute("ALTER TABLE configuracoes ADD COLUMN valor_diaria REAL DEFAULT 50.0")
    if 'valor_van' not in cols_c:
        cursor.execute("ALTER TABLE configuracoes ADD COLUMN valor_van REAL DEFAULT 30.0")
    if 'valor_pernoite' not in cols_c:
        cursor.execute("ALTER TABLE configuracoes ADD COLUMN valor_pernoite REAL DEFAULT 40.0")
    if 'impressora_status' not in cols_c:
        cursor.execute("ALTER TABLE configuracoes ADD COLUMN impressora_status TEXT")

    cols_v = [col[1] for col in cursor.execute("PRAGMA table_info(veiculos)").fetchall()]
    if 'valor' not in cols_v:
        cursor.execute("ALTER TABLE veiculos ADD COLUMN valor REAL DEFAULT 10.0")
    if 'modelo' not in cols_v:
        cursor.execute("ALTER TABLE veiculos ADD COLUMN modelo TEXT")
    if 'cor' not in cols_v:
        cursor.execute("ALTER TABLE veiculos ADD COLUMN cor TEXT")
    if 'valor_total' not in cols_v:
        cursor.execute("ALTER TABLE veiculos ADD COLUMN valor_total REAL")
    if 'hora_saida' not in cols_v:
        cursor.execute("ALTER TABLE veiculos ADD COLUMN hora_saida TEXT")
    if 'status' not in cols_v:
        cursor.execute("ALTER TABLE veiculos ADD COLUMN status TEXT DEFAULT 'ATIVO'")

    cursor.execute("SELECT COUNT(*) FROM configuracoes")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO configuracoes (id, nome, cnpj, endereco, telefone, horario, mensagem, impressora_status, valor_diaria, valor_van, valor_pernoite) VALUES (1, 'GLPPARK PRO', '00.000.000/0001-00', 'Rua Exemplo, 123', '(21) 99999-9999', '07:00-22:00', 'Seja Bem-Vindo!', 'Thermer Bluetooth', 50.0, 30.0, 40.0)")

    conn.commit()
    conn.close()

def get_dados():
    conn = obter_conexao()
    cfg = conn.execute("SELECT * FROM configuracoes WHERE id=1").fetchone()
    anuncios = conn.execute("SELECT * FROM anuncios").fetchall()
    ativos = conn.execute("SELECT * FROM veiculos WHERE status='ATIVO' ORDER BY id DESC").fetchall()
    concluidos = conn.execute("SELECT * FROM veiculos WHERE status='FINALIZADO' ORDER BY id DESC").fetchall()
    
    # Pega o próximo ID global gerado ou total de registros criados para simular o Nº do Talão atual
    total_geral = conn.execute("SELECT COUNT(*) FROM veiculos").fetchone()[0]
    num_talao = f"{total_geral + 1:04d}"
    
    conn.close()
    return cfg, anuncios, ativos, concluidos, num_talao

HTML_LOGIN = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Glppark Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>.eye-btn { cursor: pointer; position: absolute; right: 15px; top: 35px; }</style>
</head>
<body class="bg-light d-flex align-items-center justify-content-center vh-100">
    <div class="card shadow p-4" style="width: 100%; max-width: 400px;">
        <h3 class="text-center mb-4 fw-bold text-primary">🚗 Glppark Pro</h3>
        <form action="/fazer_login" method="POST">
            <div class="mb-3"><label class="form-label">E-mail</label><input type="email" name="email" class="form-control" required></div>
            <div class="mb-3 position-relative">
                <label class="form-label">Senha</label>
                <input type="password" name="senha" id="senhaLogin" class="form-control" required>
                <span class="eye-btn" onclick="let s=document.getElementById('senhaLogin'); s.type=(s.type=='password'?'text':'password');">👁️</span>
            </div>
            <button type="submit" class="btn btn-primary w-100 mb-2">Entrar</button>
        </form>
        <div class="text-center mt-3"><a href="/cadastro" class="text-decoration-none small fw-bold">Criar Cadastro Novo</a></div>
    </div>
</body>
</html>
"""

HTML_CADASTRO = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cadastro - Glppark Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>.eye-btn { cursor: pointer; position: absolute; right: 15px; top: 35px; }</style>
</head>
<body class="bg-light d-flex align-items-center justify-content-center vh-100">
    <div class="card shadow p-4" style="width: 100%; max-width: 400px;">
        <h3 class="text-center mb-4 text-success fw-bold">Novo Cadastro</h3>
        <form action="/cadastro" method="POST">
            <div class="mb-3"><label class="form-label">E-mail</label><input type="email" name="email" class="form-control" required></div>
            <div class="mb-3 position-relative">
                <label class="form-label">Senha</label>
                <input type="password" name="senha" id="senhaCad" class="form-control" required>
                <span class="eye-btn" onclick="let s=document.getElementById('senhaCad'); s.type=(s.type=='password'?'text':'password');">👁️</span>
            </div>
            <button type="submit" class="btn btn-success w-100 mb-2">Cadastrar</button>
        </form>
        <div class="text-center mt-3"><a href="/" class="text-decoration-none small">Voltar ao Login</a></div>
    </div>
</body>
</html>
"""

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Painel - Glppark Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    <script src="https://unpkg.com/html5-qrcode"></script>
    <style>
        .btn-grid { height: 75px; font-weight: bold; color: white; display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: 6px; border: none; width: 100%; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        @media print {
            body * { visibility: hidden; }
            #printableArea, #printableArea * { visibility: visible; }
            #printableArea { position: absolute; left: 0; top: 0; width: 100%; font-family: monospace; }
        }
    </style>
</head>
<body class="bg-light">
    <div style="background-color: #d35400; color: white; text-align: center; padding: 6px; font-size: 13px; font-weight: bold;">
        {{ cfg.nome }} | <a href="/logout" class="text-white">Sair</a>
    </div>
    <div class="container mt-3">
        <div class="row mb-2">
            <div class="col-6"><div class="card text-center p-2 fw-bold text-secondary bg-white border" style="font-size: 12px;">Vagas: <span class="text-dark">50</span> | Talão: <span class="text-danger">Nº {{ talao_atual }}</span></div></div>
            <div class="col-6"><div class="card text-center p-2 fw-bold text-white bg-dark" style="font-size: 12px;">Ativos: {{ ativos|length }} | Saídas: {{ concluidos|length }}</div></div>
        </div>
        <div class="row">
            <div class="col-6"><button class="btn-grid bg-success" data-bs-toggle="modal" data-bs-target="#mEntrada">📥 ENTRADA</button></div>
            <div class="col-6"><button class="btn-grid bg-danger" data-bs-toggle="modal" data-bs-target="#mSaida">📤 SAÍDA & SCANNER</button></div>
            <div class="col-6"><button class="btn-grid bg-secondary" data-bs-toggle="modal" data-bs-target="#mPatio">🅿️ PÁTIO</button></div>
            <div class="col-6"><button class="btn-grid" style="background-color: #34495e;" data-bs-toggle="modal" data-bs-target="#mConfig">⚙️ CONFIG</button></div>
            <div class="col-6"><button class="btn-grid" style="background-color: #e67e22;" data-bs-toggle="modal" data-bs-target="#mCaixa">📦 CAIXA</button></div>
            <div class="col-6"><button class="btn-grid" style="background-color: #8e44ad;" data-bs-toggle="modal" data-bs-target="#mEstatisticas">📊 ESTATÍSTICAS</button></div>
            <div class="col-12"><button class="btn-grid bg-primary" data-bs-toggle="modal" data-bs-target="#mAnuncios">📢 ANÚNCIOS</button></div>
        </div>
    </div>

    <!-- MODAL ENTRADA -->
    <div class="modal fade" id="mEntrada" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body">
        <h5 class="fw-bold mb-3">Registrar Entrada (Talão Nº {{ talao_atual }})</h5>
        <form action="/entrada" method="POST">
            <label class="small">Placa:</label><input name="placa" class="form-control mb-2 text-uppercase" placeholder="Ex: ABC-1234" required>
            
            <label class="small fw-bold">Modelo do Carro / Fabricante:</label>
            <select name="modelo" class="form-select mb-2" required>
                <option value="" disabled selected>Selecione o modelo...</option>
                <optgroup label="Fiat">
                    <option value="Fiat Uno">Fiat Uno</option>
                    <option value="Fiat Palio">Fiat Palio</option>
                    <option value="Fiat Mobi">Fiat Mobi</option>
                    <option value="Fiat Argo">Fiat Argo</option>
                    <option value="Fiat Strada">Fiat Strada</option>
                    <option value="Fiat Toro">Fiat Toro</option>
                    <option value="Fiat Fiorino">Fiat Fiorino</option>
                </optgroup>
                <optgroup label="Volkswagen">
                    <option value="VW Gol">VW Gol</option>
                    <option value="VW Polo">VW Polo</option>
                    <option value="VW Saveiro">VW Saveiro</option>
                    <option value="VW Voyage">VW Voyage</option>
                    <option value="VW T-Cross">VW T-Cross</option>
                    <option value="VW Nivus">VW Nivus</option>
                    <option value="VW Fox">VW Fox</option>
                </optgroup>
                <optgroup label="Chevrolet">
                    <option value="Chevrolet Onix">Chevrolet Onix</option>
                    <option value="Chevrolet Prisma">Chevrolet Prisma</option>
                    <option value="Chevrolet Tracker">Chevrolet Tracker</option>
                    <option value="Chevrolet S10">Chevrolet S10</option>
                    <option value="Chevrolet Montana">Chevrolet Montana</option>
                    <option value="Chevrolet Classic">Chevrolet Classic</option>
                </optgroup>
                <optgroup label="Hyundai">
                    <option value="Hyundai HB20">Hyundai HB20</option>
                    <option value="Hyundai Creta">Hyundai Creta</option>
                    <option value="Hyundai Tucson">Hyundai Tucson</option>
                </optgroup>
                <optgroup label="Toyota / Honda">
                    <option value="Toyota Corolla">Toyota Corolla</option>
                    <option value="Toyota Hilux">Toyota Hilux</option>
                    <option value="Toyota Etios">Toyota Etios</option>
                    <option value="Honda Civic">Honda Civic</option>
                    <option value="Honda Fit">Honda Fit</option>
                    <option value="Honda HR-V">Honda HR-V</option>
                </optgroup>
                <optgroup label="Renault / Ford / Jeep">
                    <option value="Renault Kwid">Renault Kwid</option>
                    <option value="Renault Sandero">Renault Sandero</option>
                    <option value="Renault Logan">Renault Logan</option>
                    <option value="Ford Ka">Ford Ka</option>
                    <option value="Ford Ranger">Ford Ranger</option>
                    <option value="Jeep Renegade">Jeep Renegade</option>
                    <option value="Jeep Compass">Jeep Compass</option>
                </optgroup>
                <optgroup label="Outros / Motos">
                    <option value="Moto Honda CG">Moto Honda CG</option>
                    <option value="Moto Yamaha">Moto Yamaha</option>
                    <option value="Van / Utilitário">Van / Utilitário</option>
                    <option value="Outro Veículo">Outro Veículo</option>
                </optgroup>
            </select>

            <label class="small fw-bold">Cor:</label>
            <select name="cor" class="form-select mb-3" required>
                <option value="" disabled selected>Selecione a cor...</option>
                <option value="Branco">Branco</option>
                <option value="Preto">Preto</option>
                <option value="Prata">Prata</option>
                <option value="Cinza">Cinza</option>
                <option value="Vermelho">Vermelho</option>
                <option value="Azul">Azul</option>
                <option value="Verde">Verde</option>
                <option value="Amarelo">Amarelo</option>
                <option value="Marrom">Marrom</option>
                <option value="Bege">Bege</option>
                <option value="Outra Cor">Outra Cor</option>
            </select>

            <label class="small">Valor por Hora (R$):</label><input name="valor" type="number" step="0.01" value="10.00" class="form-control mb-3" required>
            <button class="btn btn-success w-100">Registrar e Imprimir</button>
        </form>
    </div></div></div></div>

    <!-- MODAL COMPROVANTE DE ENTRADA -->
    {% if qr_entrada %}
    <div class="modal fade show" id="modalEntradaSucesso" tabindex="-1" style="display: block; background: rgba(0,0,0,0.6);" aria-modal="true" role="dialog">
        <div class="modal-dialog modal-dialog-centered"><div class="modal-content"><div class="modal-body text-center bg-white p-4">
            
            <div id="printableArea">
                <h5 class="fw-bold mb-1">{{ cfg.nome }}</h5>
                <p class="small mb-1">CNPJ: {{ cfg.cnpj }}</p>
                <p class="small mb-1">{{ cfg.endereco }}</p>
                <p class="small mb-2">Tel: {{ cfg.telefone }}</p>
                <hr style="border-top: dashed 1px #000;">
                <p class="fw-bold mb-1 text-uppercase">COMPROVANTE DE ENTRADA</p>
                <p class="small text-danger fw-bold mb-1">TALÃO Nº: {{ talao_atual }}</p>
                <p class="small mb-1">Placa: <strong>{{ placa_recente }}</strong></p>
                <p class="small mb-1">Modelo: {{ modelo_recente }} | Cor: {{ cor_recente }}</p>
                <p class="small mb-1">Entrada: {{ qr_entrada.split('|')[1].replace('ENTRADA:', '') }}</p>
                <p class="small mb-2">Valor/Hora: R$ {{ "%.2f"|format(valor_recente) }}</p>
                <div id="qrcodeEntrada" class="d-flex justify-content-center my-3"></div>
                <p class="small mb-2"><strong>Mensagem:</strong> {{ cfg.mensagem }}</p>
                {% if anuncios %}
                <hr style="border-top: dashed 1px #000;">
                <p class="small text-muted mb-1"><strong>Anúncios / Avisos:</strong></p>
                {% for a in anuncios %}
                <p class="small mb-1">- {{ a.texto }}</p>
                {% endfor %}
                {% endif %}
                <hr style="border-top: dashed 1px #000;">
            </div>

            <script>
                document.addEventListener("DOMContentLoaded", function() {
                    new QRCode(document.getElementById("qrcodeEntrada"), { text: `{{ qr_entrada|safe }}`, width: 140, height: 140 });
                    window.print();
                });
            </script>
            <a href="/dashboard" class="btn btn-success w-100 mt-2">OK / Concluir</a>
        </div></div></div>
    </div>
    {% endif %}

    <!-- MODAL COMPROVANTE DE SAÍDA -->
    {% if saida_recente %}
    <div class="modal fade show" id="modalSaidaSucesso" tabindex="-1" style="display: block; background: rgba(0,0,0,0.6);" aria-modal="true" role="dialog">
        <div class="modal-dialog modal-dialog-centered"><div class="modal-content"><div class="modal-body text-center bg-white p-4">
            
            <div id="printableArea">
                <h5 class="fw-bold mb-1">{{ cfg.nome }}</h5>
                <p class="small mb-1">CNPJ: {{ cfg.cnpj }}</p>
                <p class="small mb-1">{{ cfg.endereco }}</p>
                <p class="small mb-2">Tel: {{ cfg.telefone }}</p>
                <hr style="border-top: dashed 1px #000;">
                <p class="fw-bold mb-1 text-uppercase">COMPROVANTE DE SAÍDA (BAIXA)</p>
                <p class="small mb-1">Placa: <strong>{{ saida_recente.placa }}</strong></p>
                <p class="small mb-1">Entrada: {{ saida_recente.hora_entrada }}</p>
                <p class="small mb-1">Saída: {{ saida_recente.hora_saida }}</p>
                <p class="fs-5 fw-bold text-success my-2">Total a Pagar: R$ {{ "%.2f"|format(saida_recente.valor_total) }}</p>
                <p class="small mb-2"><strong>Mensagem:</strong> {{ cfg.mensagem }}</p>
                {% if anuncios %}
                <hr style="border-top: dashed 1px #000;">
                <p class="small text-muted mb-1"><strong>Anúncios / Avisos:</strong></p>
                {% for a in anuncios %}
                <p class="small mb-1">- {{ a.texto }}</p>
                {% endfor %}
                {% endif %}
                <hr style="border-top: dashed 1px #000;">
            </div>

            <script>
                document.addEventListener("DOMContentLoaded", function() {
                    window.print();
                });
            </script>
            <a href="/dashboard" class="btn btn-primary w-100 mt-2">OK / Concluir</a>
        </div></div></div>
    </div>
    {% endif %}

    <!-- MODAL SAÍDA COM CÂMERA SCANNER E ENTRADA MANUAL -->
    <div class="modal fade" id="mSaida" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body text-center">
        <h5 class="fw-bold mb-3">Escanear ou Digitar Saída</h5>
        <div id="reader" style="width: 100%;"></div>
        
        <form action="/saida_scanner" method="POST" class="mt-3">
            <div class="input-group">
                <input type="text" name="placa" id="placaScaneada" class="form-control text-uppercase" placeholder="Placa ou Código do QR" required>
                <button class="btn btn-danger" type="submit">Dar Baixa</button>
            </div>
        </form>

        <script>
            function onScanSuccess(decodedText) {
                document.getElementById('placaScaneada').value = decodedText;
                document.forms[document.forms.length - 1].submit();
            }
            try {
                let html5QrcodeScanner = new Html5QrcodeScanner("reader", { fps: 10, qrbox: 225 });
                html5QrcodeScanner.render(onScanSuccess);
            } catch (e) {
                console.log("Câmera indisponível.");
            }
        </script>
        <a href="/dashboard" class="btn btn-secondary w-100 mt-3">Fechar</a>
    </div></div></div></div>

    <!-- MODAL PÁTIO -->
    <div class="modal fade" id="mPatio" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body">
        <h5>Veículos Ativos & Comprovantes QR</h5>
        {% for c in ativos %}
        <div class="border-bottom pb-2 mb-2">
            <form action="/editar/{{ c.id }}" method="POST" class="d-flex gap-1 mb-1 align-items-center">
                <input name="placa" value="{{ c.placa }}" class="form-control form-control-sm text-uppercase" required style="width: 85px;">
                <input name="modelo" value="{{ c.modelo }}" class="form-control form-control-sm">
                <button class="btn btn-warning btn-sm">Salvar</button>
                <a href="/excluir/{{ c.id }}" class="btn btn-danger btn-sm">X</a>
            </form>
            <a href="/reimprimir/{{ c.id }}" class="btn btn-info btn-sm w-100 text-white fw-bold">🖨️ Ver / Imprimir Comprovante QR Code</a>
        </div>
        {% else %}<p class="text-muted">Pátio vazio.</p>{% endfor %}
        <a href="/dashboard" class="btn btn-secondary w-100 mt-3">Fechar</a>
    </div></div></div></div>

    <!-- MODAL CAIXA -->
    <div class="modal fade" id="mCaixa" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content"><div class="modal-body">
        <h5>Histórico de Caixa & Baixas</h5>
        <table class="table table-sm"><thead><tr><th>Placa</th><th>Entrada</th><th>Saída</th><th>Valor</th></tr></thead><tbody>
            {% for c in concluidos %}
            <tr><td>{{ c.placa }}</td><td>{{ c.hora_entrada }}</td><td>{{ c.hora_saida }}</td><td>R$ {{ "%.2f"|format(c.valor_total if c.valor_total else c.valor) }}</td></tr>
            {% else %}<tr><td colspan="4" class="text-center text-muted">Nenhum registro no caixa.</td></tr>{% endfor %}
        </tbody></table>
        <a href="/dashboard" class="btn btn-secondary w-100 mt-3">Fechar</a>
    </div></div></div></div>

    <!-- MODAL ESTATÍSTICAS -->
    <div class="modal fade" id="mEstatisticas" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body text-center">
        <h5>Estatísticas do Estacionamento</h5>
        <p class="mt-3">Total de Vagas: <strong>50</strong></p>
        <p>Talão Atual: <strong>Nº {{ talao_atual }}</strong></p>
        <p>Total de Veículos Ativos: <strong>{{ ativos|length }}</strong></p>
        <p>Total de Veículos Finalizados: <strong>{{ concluidos|length }}</strong></p>
        <a href="/dashboard" class="btn btn-secondary w-100 mt-3">Fechar</a>
    </div></div></div></div>

    <!-- MODAL CONFIG -->
    <div class="modal fade" id="mConfig" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body">
        <form action="/salvar_config" method="POST">
            <label class="small">Nome:</label><input name="nome" value="{{ cfg.nome }}" class="form-control mb-2" required>
            <label class="small">CNPJ:</label><input name="cnpj" value="{{ cfg.cnpj }}" class="form-control mb-2">
            <label class="small">Endereço:</label><input name="endereco" value="{{ cfg.endereco }}" class="form-control mb-2">
            <label class="small">Telefone:</label><input name="telefone" value="{{ cfg.telefone }}" class="form-control mb-2">
            <label class="small">Horário de Funcionamento:</label><input name="horario" value="{{ cfg.horario }}" class="form-control mb-2">
            
            <div class="row">
                <div class="col-4"><label class="small fw-bold">Diária (R$):</label><input name="valor_diaria" type="number" step="0.01" value="{{ cfg.valor_diaria }}" class="form-control mb-2" required></div>
                <div class="col-4"><label class="small fw-bold">Van/Caminh.:</label><input name="valor_van" type="number" step="0.01" value="{{ cfg.valor_van }}" class="form-control mb-2" required></div>
                <div class="col-4"><label class="small fw-bold">Pernoite (R$):</label><input name="valor_pernoite" type="number" step="0.01" value="{{ cfg.valor_pernoite }}" class="form-control mb-2" required></div>
            </div>

            <label class="small">Mensagem:</label><input name="mensagem" value="{{ cfg.mensagem }}" class="form-control mb-2">
            <label class="small fw-bold text-primary">Impressora Bluetooth Portátil:</label>
            <input name="imp" value="{{ cfg.impressora_status }}" class="form-control mb-3" placeholder="Ex: Thermer" required>
            <button class="btn btn-dark w-100 mb-2">Salvar Configurações</button>
        </form>
        <a href="/dashboard" class="btn btn-secondary w-100">Fechar</a>
    </div></div></div></div>

    <!-- MODAL ANÚNCIOS -->
    <div class="modal fade" id="mAnuncios" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body">
        <h5>Gerenciar Anúncios</h5>
        <form action="/add_anuncio" method="POST" class="input-group mb-3">
            <input name="texto" class="form-control" placeholder="Novo anúncio..." required>
            <button class="btn btn-primary">Adicionar</button>
        </form>
        {% for a in anuncios %}
        <div class="d-flex justify-content-between align-items-center border-bottom p-2 mb-1 bg-white">
            <span class="small text-truncate" style="max-width: 75%;">{{ a.texto }}</span>
            <a href="/del_anuncio/{{ a.id }}" class="btn btn-danger btn-sm px-3">Excluir</a>
        </div>
        {% else %}<p class="text-muted small">Nenhum anúncio cadastrado.</p>{% endfor %}
        <a href="/dashboard" class="btn btn-secondary w-100 mt-3">Fechar</a>
    </div></div></div></div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

@app.route('/')
def login():
    return render_template_string(HTML_LOGIN)

@app.route('/fazer_login', methods=['POST'])
def fazer_login():
    email = request.form.get('email')
    senha = request.form.get('senha')
    conn = obter_conexao()
    user = conn.execute("SELECT * FROM usuarios WHERE email = ? AND senha = ?", (email, senha)).fetchone()
    conn.close()
    if user:
        session['email'] = email
        return redirect(url_for('dashboard'))
    return f"Login incorreto. <a href='/'>Voltar</a>"

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        try:
            conn = obter_conexao()
            conn.execute("INSERT INTO usuarios (email, senha) VALUES (?, ?)", (email, senha))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except:
            return "Email já cadastrado! <a href='/cadastro'>Tentar novamente</a>"
    return render_template_string(HTML_CADASTRO)

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))
    cfg, anuncios, ativos, concluidos, talao_atual = get_dados()
    return render_template_string(HTML_DASHBOARD, cfg=cfg, anuncios=anuncios, ativos=ativos, concluidos=concluidos, talao_atual=talao_atual, qr_entrada=None, saida_recente=None)

@app.route('/entrada', methods=['GET', 'POST'])
def entrada():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    cfg, anuncios, ativos, concluidos, talao_atual = get_dados()
    
    if request.method == 'POST':
        placa = request.form.get('placa', '').upper().strip()
        modelo = request.form.get('modelo', '')
        cor = request.form.get('cor', '')
        valor = float(request.form.get('valor', 10.0))
        hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = obter_conexao()
        conn.execute("INSERT INTO veiculos (placa, modelo, cor, valor, hora_entrada) VALUES (?, ?, ?, ?, ?)", (placa, modelo, cor, valor, hora))
        conn.commit()
        conn.close()
        
        cfg, anuncios, ativos, concluidos, talao_atual = get_dados()
        qr_texto = f"PLACA:{placa}|ENTRADA:{hora}"
        
        return render_template_string(HTML_DASHBOARD, cfg=cfg, anuncios=anuncios, ativos=ativos, concluidos=concluidos, talao_atual=talao_atual, qr_entrada=qr_texto, placa_recente=placa, modelo_recente=modelo, cor_recente=cor, valor_recente=valor, saida_recente=None)
    
    return redirect(url_for('dashboard'))

@app.route('/reimprimir/<int:id>')
def reimprimir(id):
    if 'email' not in session:
        return redirect(url_for('login'))
    conn = obter_conexao()
    v = conn.execute("SELECT * FROM veiculos WHERE id=?", (id,)).fetchone()
    cfg = conn.execute("SELECT * FROM configuracoes WHERE id=1").fetchone()
    anuncios = conn.execute("SELECT * FROM anuncios").fetchall()
    ativos = conn.execute("SELECT * FROM veiculos WHERE status='ATIVO' ORDER BY id DESC").fetchall()
    concluidos = conn.execute("SELECT * FROM veiculos WHERE status='FINALIZADO' ORDER BY id DESC").fetchall()
    total_geral = conn.execute("SELECT COUNT(*) FROM veiculos").fetchone()[0]
    talao_atual = f"{total_geral:04d}"
    conn.close()

    if not v:
        return redirect(url_for('dashboard'))

    qr_texto = f"PLACA:{v['placa']}|ENTRADA:{v['hora_entrada']}"
    return render_template_string(HTML_DASHBOARD, cfg=cfg, anuncios=anuncios, ativos=ativos, concluidos=concluidos, talao_atual=talao_atual, qr_entrada=qr_texto, placa_recente=v['placa'], modelo_recente=v['modelo'], cor_recente=v['cor'], valor_recente=v['valor'], saida_recente=None)

@app.route('/saida_scanner', methods=['POST'])
def saida_scanner():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    texto_scaneado = request.form.get('placa', '').strip()
    if "PLACA:" in texto_scaneado:
        try:
            placa = texto_scaneado.split("PLACA:")[1].split("|")[0].upper().strip()
        except:
            placa = texto_scaneado.upper().strip()
    else:
        placa = texto_scaneado.upper().strip()

    conn = obter_conexao()
    v = conn.execute("SELECT * FROM veiculos WHERE placa=? AND status='ATIVO'", (placa,)).fetchone()
    
    if not v:
        conn.close()
        return f"<h3>Veículo com placa '{placa}' não encontrado no pátio ativo.</h3><a href='/dashboard'>Voltar</a>"

    fmt = "%Y-%m-%d %H:%M:%S"
    entrada = datetime.strptime(v['hora_entrada'], fmt)
    saida = datetime.now()
    tempo_total = saida - entrada
    horas = tempo_total.total_seconds() / 3600
    if horas < 0.1: horas = 0.1
    
    val_hora = v['valor'] if v['valor'] is not None else 10.0
    valor_final = horas * val_hora
    hora_saida_str = saida.strftime(fmt)
    
    conn.execute("UPDATE veiculos SET status='FINALIZADO', hora_saida=?, valor_total=? WHERE id=?", (hora_saida_str, valor_final, v['id']))
    conn.commit()
    
    cfg = conn.execute("SELECT * FROM configuracoes WHERE id=1").fetchone()
    anuncios = conn.execute("SELECT * FROM anuncios").fetchall()
    ativos = conn.execute("SELECT * FROM veiculos WHERE status='ATIVO' ORDER BY id DESC").fetchall()
    concluidos = conn.execute("SELECT * FROM veiculos WHERE status='FINALIZADO' ORDER BY id DESC").fetchall()
    total_geral = conn.execute("SELECT COUNT(*) FROM veiculos").fetchone()[0]
    talao_atual = f"{total_geral:04d}"
    
    v_atualizado = conn.execute("SELECT * FROM veiculos WHERE id=:id", {"id": v['id']}).fetchone()
    conn.close()
    
    return render_template_string(HTML_DASHBOARD, cfg=cfg, anuncios=anuncios, ativos=ativos, concluidos=concluidos, talao_atual=talao_atual, saida_recente=v_atualizado, qr_entrada=None)

@app.route('/editar/<int:id>', methods=['POST'])
def editar(id):
    if 'email' not in session:
        return redirect(url_for('login'))
    conn = obter_conexao()
    conn.execute("UPDATE veiculos SET placa=?, modelo=? WHERE id=?", (request.form['placa'].upper().strip(), request.form['modelo'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/excluir/<int:id>')
def excluir(id):
    if 'email' not in session:
        return redirect(url_for('login'))
    conn = obter_conexao()
    conn.execute("DELETE FROM veiculos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/salvar_config', methods=['POST'])
def salvar_config():
    if 'email' not in session:
        return redirect(url_for('login'))
    try:
        conn = obter_conexao()
        conn.execute("UPDATE configuracoes SET nome=?, cnpj=?, endereco=?, telefone=?, horario=?, mensagem=?, impressora_status=?, valor_diaria=?, valor_van=?, valor_pernoite=? WHERE id=1",
                     (
                         request.form.get('nome', ''),
                         request.form.get('cnpj', ''),
                         request.form.get('endereco', ''),
                         request.form.get('telefone', ''),
                         request.form.get('horario', ''),
                         request.form.get('mensagem', ''),
                         request.form.get('imp', ''),
                         float(request.form.get('valor_diaria', 50.0)),
                         float(request.form.get('valor_van', 30.0)),
                         float(request.form.get('valor_pernoite', 40.0))
                     ))
        conn.commit()
        conn.close()
    except Exception as e:
        return f"Erro ao salvar configurações: {e}. <a href='/dashboard'>Voltar</a>"
    return redirect(url_for('dashboard'))

@app.route('/add_anuncio', methods=['POST'])

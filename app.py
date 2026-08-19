import os
import random
import sqlite3
import base64
import secrets
import json
import math
import csv
import io
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from flask import Flask, render_template_string, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-no-render")
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")

def agora_brasilia():
    """Retorna o horário atual oficial de Brasília."""
    return datetime.now(FUSO_BRASIL)

def agora_banco():
    """Retorna o horário de Brasília no formato usado pelo banco."""
    return agora_brasilia().strftime('%Y-%m-%d %H:%M:%S')

class Conexao:
    def __init__(self):
        url = os.environ.get('DATABASE_URL', '')
        self.pg = bool(url)
        if self.pg:
            if not psycopg2:
                raise RuntimeError('psycopg2 não instalado')
            self.raw = psycopg2.connect(url, cursor_factory=RealDictCursor)
        else:
            self.raw = sqlite3.connect('estacionamento.db')
            self.raw.row_factory = sqlite3.Row
    def execute(self, sql, params=()):
        if self.pg:
            sql = sql.replace('?', '%s')
            if isinstance(params, dict):
                for chave in params: sql = sql.replace(':' + chave, '%(' + chave + ')s')
            cur = self.raw.cursor(); cur.execute(sql, params); return cur
        return self.raw.execute(sql, params)
    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()
    def close(self): self.raw.close()

def obter_conexao(): return Conexao()

def inicializar_banco():
    conn = obter_conexao()
    auto = 'SERIAL PRIMARY KEY' if conn.pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    conn.execute(f'''CREATE TABLE IF NOT EXISTS empresas (id {auto}, nome TEXT NOT NULL, codigo TEXT UNIQUE NOT NULL, ativo INTEGER DEFAULT 1, plano TEXT DEFAULT 'Basico', valor_mensal REAL DEFAULT 0, vencimento TEXT, status_assinatura TEXT DEFAULT 'ATIVA', limite_funcionarios INTEGER DEFAULT 3, teste_ate TEXT, principal INTEGER DEFAULT 0)''')
    conn.execute(f'''CREATE TABLE IF NOT EXISTS usuarios (id {auto}, empresa_id INTEGER NOT NULL, nome TEXT, email TEXT UNIQUE NOT NULL, senha TEXT NOT NULL, perfil TEXT DEFAULT 'funcionario')''')
    conn.execute(f'''CREATE TABLE IF NOT EXISTS configuracoes (id {auto}, empresa_id INTEGER UNIQUE NOT NULL, nome TEXT, cnpj TEXT, endereco TEXT, telefone TEXT, horario TEXT, mensagem TEXT, impressora_status TEXT, valor_diaria REAL DEFAULT 50, valor_van REAL DEFAULT 30, valor_pernoite REAL DEFAULT 40, valor_hora REAL DEFAULT 10, valor_fracao REAL DEFAULT 5, minutos_fracao INTEGER DEFAULT 30, taxa_talao REAL DEFAULT 30, total_vagas INTEGER DEFAULT 50, logo TEXT)''')
    conn.execute(f'''CREATE TABLE IF NOT EXISTS anuncios (id {auto}, empresa_id INTEGER NOT NULL, texto TEXT)''')
    conn.execute(f'''CREATE TABLE IF NOT EXISTS veiculos (id {auto}, empresa_id INTEGER NOT NULL, offline_id TEXT, placa TEXT NOT NULL, modelo TEXT, cor TEXT, valor REAL DEFAULT 10, tipo_tarifa TEXT DEFAULT 'diaria', numero_talao TEXT, hora_entrada TEXT, hora_saida TEXT, valor_total REAL, status TEXT DEFAULT 'ATIVO', forma_pagamento TEXT, desconto REAL DEFAULT 0, talao_perdido INTEGER DEFAULT 0, mensalista_id INTEGER, cancelado INTEGER DEFAULT 0, observacao TEXT)''')
    conn.execute(f'''CREATE TABLE IF NOT EXISTS mensalistas (id {auto}, empresa_id INTEGER NOT NULL, nome TEXT NOT NULL, documento TEXT, telefone TEXT, placa TEXT NOT NULL, modelo TEXT, valor_mensal REAL DEFAULT 0, dia_vencimento INTEGER DEFAULT 10, ativo INTEGER DEFAULT 1)''')
    conn.execute(f'''CREATE TABLE IF NOT EXISTS caixas (id {auto}, empresa_id INTEGER NOT NULL, usuario_id INTEGER NOT NULL, aberto_em TEXT, fechado_em TEXT, saldo_inicial REAL DEFAULT 0, saldo_final REAL, status TEXT DEFAULT 'ABERTO')''')
    conn.execute(f'''CREATE TABLE IF NOT EXISTS movimentos_caixa (id {auto}, empresa_id INTEGER NOT NULL, caixa_id INTEGER, usuario_id INTEGER, veiculo_id INTEGER, tipo TEXT NOT NULL, descricao TEXT, valor REAL DEFAULT 0, forma_pagamento TEXT, criado_em TEXT)''')
    conn.execute(f'''CREATE TABLE IF NOT EXISTS auditoria (id {auto}, empresa_id INTEGER NOT NULL, usuario_id INTEGER, acao TEXT, detalhes TEXT, criado_em TEXT)''')
    # Migra automaticamente a versão antiga, preservando os dados existentes.
    tabelas_colunas = {
        'empresas': [
            ('plano',"TEXT DEFAULT 'Basico'"),('valor_mensal','REAL DEFAULT 0'),('vencimento','TEXT'),
            ('status_assinatura',"TEXT DEFAULT 'ATIVA'"),('limite_funcionarios','INTEGER DEFAULT 3'),('teste_ate','TEXT'),('principal','INTEGER DEFAULT 0')
        ],
        'usuarios': [('empresa_id','INTEGER'),('nome','TEXT'),('email','TEXT'),('senha','TEXT'),('perfil',"TEXT DEFAULT 'funcionario'")],
        'configuracoes': [
            ('empresa_id','INTEGER'),('nome',"TEXT DEFAULT 'GLPPARK'"),('cnpj','TEXT'),('endereco','TEXT'),
            ('telefone','TEXT'),('horario','TEXT'),('mensagem','TEXT'),('impressora_status','TEXT'),
            ('valor_diaria','REAL DEFAULT 50'),('valor_van','REAL DEFAULT 30'),('valor_pernoite','REAL DEFAULT 40'),
            ('valor_hora','REAL DEFAULT 10'),('valor_fracao','REAL DEFAULT 5'),('minutos_fracao','INTEGER DEFAULT 30'),
            ('taxa_talao','REAL DEFAULT 30'),('total_vagas','INTEGER DEFAULT 50'),('logo','TEXT')
        ],
        'anuncios': [('empresa_id','INTEGER'),('texto','TEXT')],
        'veiculos': [
            ('empresa_id','INTEGER'),('offline_id','TEXT'),('placa','TEXT'),('modelo','TEXT'),('cor','TEXT'),
            ('valor','REAL DEFAULT 10'),('tipo_tarifa',"TEXT DEFAULT 'diaria'"),('numero_talao','TEXT'),
            ('hora_entrada','TEXT'),('hora_saida','TEXT'),('valor_total','REAL'),('status',"TEXT DEFAULT 'ATIVO'"),
            ('forma_pagamento','TEXT'),('desconto','REAL DEFAULT 0'),('talao_perdido','INTEGER DEFAULT 0'),
            ('mensalista_id','INTEGER'),('cancelado','INTEGER DEFAULT 0'),('observacao','TEXT')
        ]
    }
    if conn.pg:
        for tabela, colunas in tabelas_colunas.items():
            for coluna, tipo in colunas: conn.execute(f'ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS {coluna} {tipo}')
    else:
        for tabela, colunas in tabelas_colunas.items():
            existentes = {r[1] for r in conn.execute(f'PRAGMA table_info({tabela})').fetchall()}
            for coluna, tipo in colunas:
                if coluna not in existentes: conn.execute(f'ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}')
    # Garante uma empresa administrativa GLPPARK fixa e independente da ordem dos IDs.
    principal = conn.execute("SELECT id FROM empresas WHERE COALESCE(principal,0)=1 ORDER BY id LIMIT 1").fetchone()
    if not principal:
        por_codigo = conn.execute("SELECT id FROM empresas WHERE codigo=? LIMIT 1", ('glppark-principal',)).fetchone()
        if por_codigo:
            principal_id = por_codigo['id']
            conn.execute("UPDATE empresas SET principal=1,ativo=1,status_assinatura='ATIVA',plano='Premium',valor_mensal=0,limite_funcionarios=999 WHERE id=?", (principal_id,))
        elif conn.pg:
            principal_id = conn.execute("INSERT INTO empresas(nome,codigo,ativo,plano,valor_mensal,status_assinatura,limite_funcionarios,principal) VALUES (?,?,?,?,?,?,?,1) RETURNING id", ('GLPPARK — Administração', 'glppark-principal', 1, 'Premium', 0, 'ATIVA', 999)).fetchone()['id']
        else:
            principal_id = conn.execute("INSERT INTO empresas(nome,codigo,ativo,plano,valor_mensal,status_assinatura,limite_funcionarios,principal) VALUES (?,?,?,?,?,?,?,1)", ('GLPPARK — Administração', 'glppark-principal', 1, 'Premium', 0, 'ATIVA', 999)).lastrowid
    else:
        principal_id = principal['id']

    # Evita que qualquer empresa cliente/teste vire Administrador Geral por engano.
    conn.execute("UPDATE empresas SET principal=0 WHERE id<>? AND COALESCE(principal,0)<>0", (principal_id,))
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_empresa_principal_unica ON empresas(principal) WHERE principal=1')

    cfg_principal = conn.execute("SELECT id FROM configuracoes WHERE empresa_id=?", (principal_id,)).fetchone()
    if not cfg_principal:
        conn.execute("""INSERT INTO configuracoes (empresa_id,nome,cnpj,endereco,telefone,horario,mensagem,impressora_status,valor_diaria,valor_van,valor_pernoite,logo)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (principal_id,'GLPPARK','','','','07:00-22:00','Administração Geral GLPPARK','Thermer Bluetooth',50,30,40,''))

    legado = conn.execute('SELECT COUNT(*) AS total FROM configuracoes WHERE empresa_id IS NULL').fetchone()
    total_legado = legado['total'] if hasattr(legado, 'keys') else legado[0]
    if total_legado:
        empresa_legada = principal_id
        for tabela in ('usuarios','configuracoes','anuncios','veiculos'):
            conn.execute(f'UPDATE {tabela} SET empresa_id=? WHERE empresa_id IS NULL', (empresa_legada,))
        conn.execute("UPDATE usuarios SET perfil='admin' WHERE empresa_id=?", (empresa_legada,))
    # Remove somente o nome antigo usado no protótipo; os demais nomes são preservados.
    conn.execute(
        "UPDATE configuracoes SET nome='GLPPARK' WHERE LOWER(COALESCE(nome,'')) LIKE ?",
        ('%manfrenate%',)
    )
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_offline_empresa ON veiculos(empresa_id, offline_id)')
    conn.commit()
    conn.close()

def gerar_numero_talao(conn):
    """Gera um talão aleatório de 5 dígitos ainda não utilizado."""
    for _ in range(1000):
        numero = str(random.randint(10000, 99999))
        existe = conn.execute(
            "SELECT 1 FROM veiculos WHERE empresa_id=? AND numero_talao=? LIMIT 1", (session['empresa_id'], numero)
        ).fetchone()
        if not existe:
            return numero
    raise RuntimeError("Não foi possível gerar um número de talão disponível.")


def get_dados():
    empresa_id = session['empresa_id']
    conn = obter_conexao()
    cfg = conn.execute("SELECT * FROM configuracoes WHERE empresa_id=?", (empresa_id,)).fetchone()
    anuncios = conn.execute("SELECT * FROM anuncios WHERE empresa_id=?", (empresa_id,)).fetchall()
    ativos = conn.execute("SELECT * FROM veiculos WHERE empresa_id=? AND status='ATIVO' ORDER BY id DESC", (empresa_id,)).fetchall()
    concluidos = conn.execute("SELECT * FROM veiculos WHERE empresa_id=? AND status='FINALIZADO' ORDER BY id DESC", (empresa_id,)).fetchall()
    
    num_talao = gerar_numero_talao(conn)
    
    conn.close()
    return cfg, anuncios, ativos, concluidos, num_talao

def registrar_auditoria(conn, acao, detalhes=''):
    conn.execute("INSERT INTO auditoria(empresa_id,usuario_id,acao,detalhes,criado_em) VALUES(?,?,?,?,?)", (session['empresa_id'], session.get('usuario_id'), acao, detalhes, agora_banco()))

def obter_caixa_aberto(conn):
    return conn.execute("SELECT * FROM caixas WHERE empresa_id=? AND status='ABERTO' ORDER BY id DESC LIMIT 1", (session['empresa_id'],)).fetchone()

PLANOS_GLPPARK = {
    'Basico': {
        'limite_funcionarios': 3,
        'valor_sugerido': 49.90,
        'recursos': {'entrada','saida','patio','config','caixa'}
    },
    'Pro': {
        'limite_funcionarios': 10,
        'valor_sugerido': 89.90,
        'recursos': {'entrada','saida','patio','config','caixa','estatisticas','mensalistas','relatorios'}
    },
    'Premium': {
        'limite_funcionarios': 999,
        'valor_sugerido': 149.90,
        'recursos': {'entrada','saida','patio','config','caixa','estatisticas','mensalistas','relatorios','financeiro','anuncios'}
    },
}

def recurso_liberado(recurso, plano=None):
    plano = plano or session.get('plano', 'Basico')
    dados = PLANOS_GLPPARK.get(plano, PLANOS_GLPPARK['Basico'])
    return recurso in dados['recursos']

def exigir_recurso(recurso):
    if not recurso_liberado(recurso):
        plano = session.get('plano', 'Basico')
        return f"<h3>Recurso não disponível no plano {plano}.</h3><p>Altere o plano na Gestão GLPPARK para liberar esta função.</p><a href='/dashboard'>Voltar</a>", 403
    return None

def status_empresa(emp):
    """Retorna ATIVA, TESTE, VENCIDA ou SUSPENSA sem apagar dados da empresa.

    Prioridade:
    1. SUSPENSA
    2. VENCIDA
    3. TESTE
    4. ATIVA
    """
    if not emp:
        return 'SUSPENSA'

    if int(emp['ativo'] or 0) != 1 or str(emp['status_assinatura'] or '').upper() == 'SUSPENSA':
        return 'SUSPENSA'

    hoje = agora_brasilia().date()

    vencimento = (emp['vencimento'] or '').strip()
    if vencimento:
        try:
            data_vencimento = datetime.strptime(vencimento, '%Y-%m-%d').date()
            if hoje > data_vencimento:
                return 'VENCIDA'
        except ValueError:
            pass

    teste_ate = (emp['teste_ate'] or '').strip()
    if teste_ate:
        try:
            data_teste = datetime.strptime(teste_ate, '%Y-%m-%d').date()
            if hoje <= data_teste:
                return 'TESTE'
        except ValueError:
            pass

    return 'ATIVA'

def acesso_empresa_liberado(emp):
    return status_empresa(emp) in ('ATIVA', 'TESTE')

def calcular_cobranca(v, cfg, minutos, talao_perdido=False, desconto=0):
    if minutos <= 15 or v['tipo_tarifa'] == 'mensalista':
        bruto = 0.0
    elif v['tipo_tarifa'] == 'hora':
        bruto = float(cfg['valor_hora'])
        if minutos > 60:
            fracoes = math.ceil((minutos - 60) / max(1, int(cfg['minutos_fracao'])))
            bruto += fracoes * float(cfg['valor_fracao'])
    else:
        bruto = float(v['valor'] or 0)
    if talao_perdido: bruto += float(cfg['taxa_talao'] or 0)
    return max(0.0, bruto - max(0.0, float(desconto or 0)))

HTML_LOGIN = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - GLPPARK</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>.eye-btn { cursor: pointer; position: absolute; right: 15px; top: 35px; }</style>
</head>
<body class="bg-light d-flex align-items-center justify-content-center vh-100">
    <div class="card shadow p-4" style="width: 100%; max-width: 400px;">
        <h3 class="text-center mb-4 fw-bold text-primary">🚗 GLPPARK</h3>
        <form action="/fazer_login" method="POST">
            <div class="mb-3"><label class="form-label">E-mail</label><input type="email" name="email" class="form-control" required></div>
            <div class="mb-3 position-relative">
                <label class="form-label">Senha</label>
                <input type="password" name="senha" id="senhaLogin" class="form-control" required>
                <span class="eye-btn" onclick="let s=document.getElementById('senhaLogin'); s.type=(s.type=='password'?'text':'password');">👁️</span>
            </div>
            <button type="submit" class="btn btn-primary w-100 mb-2">Entrar</button>
        </form>
        <div class="text-center mt-3"><a href="mailto:guilhermelucenaibnf@gmail.com?subject=Contrata%C3%A7%C3%A3o%20GLPPARK" class="text-decoration-none small fw-bold">Solicitar acesso ao GLPPARK</a></div>
        <div class="text-center mt-2"><a href="/politica-privacidade" class="text-decoration-none small text-secondary">Política de Privacidade</a></div>
    </div>
</body>
</html>
"""

HTML_CADASTRO = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cadastro - GLPPARK</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>.eye-btn { cursor: pointer; position: absolute; right: 15px; top: 35px; }</style>
</head>
<body class="bg-light d-flex align-items-center justify-content-center vh-100">
    <div class="card shadow p-4" style="width: 100%; max-width: 400px;">
        <h3 class="text-center mb-4 text-success fw-bold">Novo Cadastro</h3>
        <form action="/cadastro" method="POST">
            <div class="mb-3"><label class="form-label">Nome da empresa</label><input name="empresa" class="form-control" required></div>
            <div class="mb-3"><label class="form-label">Seu nome</label><input name="nome_usuario" class="form-control" required></div>
            <div class="mb-3"><label class="form-label">E-mail</label><input type="email" name="email" class="form-control" required></div>
            <div class="mb-3 position-relative">
                <label class="form-label">Senha</label>
                <input type="password" name="senha" id="senhaCad" class="form-control" required>
                <span class="eye-btn" onclick="let s=document.getElementById('senhaCad'); s.type=(s.type=='password'?'text':'password');">👁️</span>
            </div>
            <button type="submit" class="btn btn-success w-100 mb-2">Cadastrar</button>
        </form>
        <div class="text-center mt-3"><a href="/" class="text-decoration-none small">Voltar ao Login</a></div>
        <div class="text-center mt-2"><a href="/politica-privacidade" class="text-decoration-none small text-secondary">Política de Privacidade</a></div>
    </div>
</body>
</html>
"""

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Painel - GLPPARK</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#d35400">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    <script src="https://unpkg.com/html5-qrcode"></script>
    <style>
        .btn-grid { height: 75px; font-weight: bold; color: white; display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: 6px; border: none; width: 100%; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
@media print {
    @page {
        size: 58mm auto;
        margin: 0;
    }

    html, body {
        width: 58mm !important;
        height: auto !important;
        min-height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: visible !important;
    }

    body * {
        visibility: hidden;
    }

    #printableArea,
    #printableArea * {
        visibility: visible;
    }

    #printableArea {
        position: fixed !important;
        left: 0 !important;
        top: 0 !important;
        width: 58mm !important;
        height: auto !important;
        min-height: 0 !important;
        margin: 0 !important;
        padding: 2mm !important;
        box-sizing: border-box;
        font-family: monospace;
        text-align: center;
        overflow: visible !important;
    }
}
  
    </style>
</head>
<body class="bg-light">
    <div style="background-color: #d35400; color: white; padding: 6px 10px; font-size: 13px; font-weight: bold; display:flex; justify-content:space-between; align-items:center; gap:8px;">
        <div style="display:flex; align-items:center; gap:8px; min-width:0; flex:1;">
            {% if cfg.logo %}<img src="/logo?v={{ cfg.id }}" alt="Logo" style="max-height:32px; max-width:110px; object-fit:contain; background:white; padding:2px; border-radius:3px; flex-shrink:0;">{% endif %}
            <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{{ cfg.nome }} | <a href="/logout" class="text-white">Sair</a></span>
        </div>
        <span id="relogioGlppark" style="white-space:nowrap; flex-shrink:0; font-variant-numeric:tabular-nums;">🕐 --:--</span>
    </div>
    <div class="container mt-3">
        <div class="alert alert-light border py-2 px-3 mb-2 d-flex justify-content-between align-items-center flex-wrap gap-1" style="font-size:12px;">
            <span><strong>Plano:</strong> {{ session.plano|default('Basico') }}</span>
            <span><strong>Status:</strong> {{ session.status_assinatura|default('ATIVA') }}</span>
            {% if empresa_vencimento %}<span><strong>Vencimento:</strong> {{ empresa_vencimento }}</span>{% endif %}
        </div>
        {% if aviso_vencimento %}<div class="alert alert-warning py-2 small">{{ aviso_vencimento }}</div>{% endif %}
        <div class="row mb-2">
            <div class="col-6"><div class="card text-center p-2 fw-bold text-secondary bg-white border" style="font-size: 12px;">Livres: <span class="text-dark">{{ [cfg.total_vagas - (ativos|length), 0]|max }}</span>/{{ cfg.total_vagas }} | Talão: <span class="text-danger">Nº {{ talao_atual }}</span></div></div>
            <div class="col-6"><div class="card text-center p-2 fw-bold text-white bg-dark" style="font-size: 12px;">Ativos: {{ ativos|length }} | Saídas: {{ concluidos|length }}</div></div>
        </div>
        <div class="row">
            <div class="col-6"><button class="btn-grid bg-success" data-bs-toggle="modal" data-bs-target="#mEntrada">📥 ENTRADA</button></div>
            <div class="col-6"><button class="btn-grid bg-danger" data-bs-toggle="modal" data-bs-target="#mSaida">📤 SAÍDA & SCANNER</button></div>
            <div class="col-6"><button class="btn-grid bg-secondary" data-bs-toggle="modal" data-bs-target="#mPatio">🅿️ PÁTIO</button></div>
            {% if session.perfil == 'admin' %}
            {% if recurso_liberado('config') %}<div class="col-6"><button class="btn-grid" style="background-color: #34495e;" data-bs-toggle="modal" data-bs-target="#mConfig">⚙️ CONFIG</button></div>{% endif %}
            {% if recurso_liberado('caixa') %}<div class="col-6"><button class="btn-grid" style="background-color: #e67e22;" data-bs-toggle="modal" data-bs-target="#mCaixa">📦 CAIXA</button></div>{% endif %}
            {% if recurso_liberado('estatisticas') %}<div class="col-6"><button class="btn-grid" style="background-color: #8e44ad;" data-bs-toggle="modal" data-bs-target="#mEstatisticas">📊 ESTATÍSTICAS</button></div>{% endif %}
            {% if recurso_liberado('anuncios') %}<div class="col-12"><button class="btn-grid bg-primary" data-bs-toggle="modal" data-bs-target="#mAnuncios">📢 ANÚNCIOS</button></div>{% endif %}
            {% if recurso_liberado('mensalistas') %}<div class="col-6"><button class="btn-grid bg-success" onclick="location.href='/mensalistas'">👤 MENSALISTAS</button></div>{% endif %}
            {% if recurso_liberado('financeiro') %}<div class="col-6"><button class="btn-grid bg-dark" onclick="location.href='/financeiro'">💰 FINANCEIRO</button></div>{% endif %}
            {% if recurso_liberado('relatorios') %}<div class="col-12"><button class="btn-grid" style="background:#0d6efd" onclick="location.href='/relatorios'">📄 RELATÓRIOS</button></div>{% endif %}
            {% endif %}
        </div>
    </div>

    <!-- MODAL ENTRADA -->
    <div class="modal fade" id="mEntrada" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body">
        <h5 class="fw-bold mb-3">Registrar Entrada (Talão Nº {{ talao_atual }})</h5>
        <form action="/entrada" method="POST">
            <input type="hidden" name="numero_talao" value="{{ talao_atual }}">
            <label class="small">Placa:</label><input name="placa" class="form-control mb-2 text-uppercase" placeholder="Ex: ABC-1234" required>
            
            <label class="small fw-bold">Modelo / fabricante:</label>
            <input name="modelo" list="listaModelos" class="form-control mb-2" placeholder="Digite para pesquisar, ex.: Corolla" autocomplete="off" required>
            <datalist id="listaModelos">
                <option value="Fiat 500"><option value="Fiat Argo"><option value="Fiat Bravo"><option value="Fiat Cronos"><option value="Fiat Doblo"><option value="Fiat Fastback"><option value="Fiat Fiorino"><option value="Fiat Freemont"><option value="Fiat Grand Siena"><option value="Fiat Idea"><option value="Fiat Linea"><option value="Fiat Marea"><option value="Fiat Mobi"><option value="Fiat Palio"><option value="Fiat Pulse"><option value="Fiat Punto"><option value="Fiat Siena"><option value="Fiat Strada"><option value="Fiat Tempra"><option value="Fiat Tipo"><option value="Fiat Toro"><option value="Fiat Uno">
                <option value="Volkswagen Amarok"><option value="Volkswagen Bora"><option value="Volkswagen Brasília"><option value="Volkswagen CrossFox"><option value="Volkswagen Fox"><option value="Volkswagen Fusca"><option value="Volkswagen Gol"><option value="Volkswagen Golf"><option value="Volkswagen Jetta"><option value="Volkswagen Kombi"><option value="Volkswagen Nivus"><option value="Volkswagen Parati"><option value="Volkswagen Passat"><option value="Volkswagen Polo"><option value="Volkswagen Santana"><option value="Volkswagen Saveiro"><option value="Volkswagen SpaceFox"><option value="Volkswagen T-Cross"><option value="Volkswagen Taos"><option value="Volkswagen Tiguan"><option value="Volkswagen Up"><option value="Volkswagen Virtus"><option value="Volkswagen Voyage">
                <option value="Chevrolet Agile"><option value="Chevrolet Astra"><option value="Chevrolet Blazer"><option value="Chevrolet Camaro"><option value="Chevrolet Captiva"><option value="Chevrolet Celta"><option value="Chevrolet Classic"><option value="Chevrolet Cobalt"><option value="Chevrolet Corsa"><option value="Chevrolet Cruze"><option value="Chevrolet Equinox"><option value="Chevrolet Meriva"><option value="Chevrolet Montana"><option value="Chevrolet Monza"><option value="Chevrolet Onix"><option value="Chevrolet Prisma"><option value="Chevrolet S10"><option value="Chevrolet Spin"><option value="Chevrolet Tracker"><option value="Chevrolet Trailblazer"><option value="Chevrolet Vectra"><option value="Chevrolet Zafira">
                <option value="Ford Bronco"><option value="Ford Courier"><option value="Ford EcoSport"><option value="Ford Edge"><option value="Ford Escort"><option value="Ford F-1000"><option value="Ford Fiesta"><option value="Ford Focus"><option value="Ford Fusion"><option value="Ford Ka"><option value="Ford Maverick"><option value="Ford Mustang"><option value="Ford Ranger"><option value="Ford Territory"><option value="Ford Transit">
                <option value="Toyota Bandeirante"><option value="Toyota Camry"><option value="Toyota Corolla"><option value="Toyota Corolla Cross"><option value="Toyota Etios"><option value="Toyota Hilux"><option value="Toyota Prius"><option value="Toyota RAV4"><option value="Toyota SW4"><option value="Toyota Yaris">
                <option value="Honda Accord"><option value="Honda City"><option value="Honda Civic"><option value="Honda CR-V"><option value="Honda Fit"><option value="Honda HR-V"><option value="Honda WR-V"><option value="Honda ZR-V">
                <option value="Hyundai Azera"><option value="Hyundai Creta"><option value="Hyundai Elantra"><option value="Hyundai HB20"><option value="Hyundai HB20S"><option value="Hyundai i30"><option value="Hyundai ix35"><option value="Hyundai Santa Fe"><option value="Hyundai Sonata"><option value="Hyundai Tucson"><option value="Hyundai Veracruz">
                <option value="Renault Captur"><option value="Renault Clio"><option value="Renault Duster"><option value="Renault Fluence"><option value="Renault Kardian"><option value="Renault Kangoo"><option value="Renault Kwid"><option value="Renault Logan"><option value="Renault Master"><option value="Renault Megane"><option value="Renault Oroch"><option value="Renault Sandero"><option value="Renault Scenic"><option value="Renault Stepway">
                <option value="Jeep Cherokee"><option value="Jeep Commander"><option value="Jeep Compass"><option value="Jeep Grand Cherokee"><option value="Jeep Renegade"><option value="Jeep Wrangler">
                <option value="Nissan Frontier"><option value="Nissan Kicks"><option value="Nissan Leaf"><option value="Nissan Livina"><option value="Nissan March"><option value="Nissan Pathfinder"><option value="Nissan Sentra"><option value="Nissan Tiida"><option value="Nissan Versa"><option value="Nissan X-Trail">
                <option value="Peugeot 2008"><option value="Peugeot 206"><option value="Peugeot 207"><option value="Peugeot 208"><option value="Peugeot 3008"><option value="Peugeot 307"><option value="Peugeot 308"><option value="Peugeot 408"><option value="Peugeot 5008"><option value="Peugeot Boxer"><option value="Peugeot Expert"><option value="Peugeot Partner">
                <option value="Citroën Aircross"><option value="Citroën C3"><option value="Citroën C3 Aircross"><option value="Citroën C4 Cactus"><option value="Citroën C4 Lounge"><option value="Citroën C5"><option value="Citroën Jumpy"><option value="Citroën Xsara Picasso">
                <option value="Mitsubishi ASX"><option value="Mitsubishi Eclipse Cross"><option value="Mitsubishi L200"><option value="Mitsubishi Lancer"><option value="Mitsubishi Outlander"><option value="Mitsubishi Pajero"><option value="Mitsubishi Pajero Sport"><option value="Mitsubishi Triton">
                <option value="Kia Bongo"><option value="Kia Carnival"><option value="Kia Cerato"><option value="Kia Mohave"><option value="Kia Niro"><option value="Kia Picanto"><option value="Kia Sorento"><option value="Kia Soul"><option value="Kia Sportage"><option value="Kia Stonic">
                <option value="Chery Arrizo 5"><option value="Chery Arrizo 6"><option value="Chery Celer"><option value="Chery Face"><option value="Chery QQ"><option value="Caoa Chery Tiggo 2"><option value="Caoa Chery Tiggo 3X"><option value="Caoa Chery Tiggo 5X"><option value="Caoa Chery Tiggo 7"><option value="Caoa Chery Tiggo 8">
                <option value="BYD Dolphin"><option value="BYD Dolphin Mini"><option value="BYD Han"><option value="BYD King"><option value="BYD Seal"><option value="BYD Song Plus"><option value="BYD Tan"><option value="GWM Haval H6"><option value="GWM Ora 03"><option value="GWM Tank 300"><option value="JAC E-JS1"><option value="JAC J3"><option value="JAC T40"><option value="JAC T50"><option value="JAC T60">
                <option value="BMW Série 1"><option value="BMW Série 3"><option value="BMW Série 5"><option value="BMW X1"><option value="BMW X3"><option value="BMW X5"><option value="Mercedes-Benz Classe A"><option value="Mercedes-Benz Classe C"><option value="Mercedes-Benz GLA"><option value="Mercedes-Benz GLC"><option value="Mercedes-Benz Sprinter"><option value="Audi A3"><option value="Audi A4"><option value="Audi Q3"><option value="Audi Q5"><option value="Volvo XC40"><option value="Volvo XC60"><option value="Volvo XC90"><option value="Land Rover Defender"><option value="Land Rover Discovery"><option value="Land Rover Range Rover Evoque"><option value="Porsche Cayenne"><option value="Porsche Macan"><option value="Tesla Model 3"><option value="Tesla Model Y">
                <option value="Suzuki Jimny"><option value="Suzuki S-Cross"><option value="Suzuki Vitara"><option value="Subaru Forester"><option value="Subaru Impreza"><option value="Subaru XV"><option value="RAM 1500"><option value="RAM 2500"><option value="RAM Rampage"><option value="Iveco Daily"><option value="Mercedes-Benz Accelo"><option value="Mercedes-Benz Atego"><option value="Scania Caminhão"><option value="Volvo Caminhão"><option value="Van / Utilitário"><option value="Ônibus / Micro-ônibus">
                <option value="Moto Honda Biz"><option value="Moto Honda Bros"><option value="Moto Honda CB"><option value="Moto Honda CG"><option value="Moto Honda Pop"><option value="Moto Honda XRE"><option value="Moto Yamaha Fazer"><option value="Moto Yamaha Factor"><option value="Moto Yamaha Lander"><option value="Moto Yamaha NMax"><option value="Moto Yamaha XTZ"><option value="Moto Suzuki"><option value="Moto Kawasaki"><option value="Moto BMW"><option value="Moto Harley-Davidson"><option value="Outro veículo">
            </datalist>
            <div class="form-text mb-2">Pesquise na lista ou digite livremente qualquer modelo.</div>

            <label class="small fw-bold">Cor:</label>
            <input name="cor" list="listaCores" class="form-control mb-3" placeholder="Digite ou escolha a cor" autocomplete="off" required>
            <datalist id="listaCores"><option value="Branco"><option value="Branco perolizado"><option value="Preto"><option value="Preto fosco"><option value="Prata"><option value="Cinza"><option value="Cinza grafite"><option value="Grafite"><option value="Chumbo"><option value="Vermelho"><option value="Vermelho vinho"><option value="Bordô"><option value="Azul"><option value="Azul marinho"><option value="Azul claro"><option value="Verde"><option value="Verde escuro"><option value="Amarelo"><option value="Laranja"><option value="Marrom"><option value="Bege"><option value="Dourado"><option value="Bronze"><option value="Roxo"><option value="Rosa"><option value="Creme"><option value="Cobre"><option value="Champanhe"><option value="Bicolor"><option value="Adesivado / Personalizado"><option value="Outra cor"></datalist>

            <label class="small fw-bold">Tipo de tarifa:</label>
            <select name="tipo_tarifa" id="tipoTarifa" class="form-select mb-2" onchange="atualizarTarifa()" required>
                <option value="diaria" data-valor="{{ cfg.valor_diaria }}">Diária — R$ {{ "%.2f"|format(cfg.valor_diaria) }}</option>
                <option value="van" data-valor="{{ cfg.valor_van }}">Van/Caminhonete — R$ {{ "%.2f"|format(cfg.valor_van) }}</option>
                <option value="pernoite" data-valor="{{ cfg.valor_pernoite }}">Pernoite — R$ {{ "%.2f"|format(cfg.valor_pernoite) }}</option>
                <option value="hora" data-valor="{{ cfg.valor_hora }}">Hora e fração — R$ {{ "%.2f"|format(cfg.valor_hora) }}</option>
                <option value="mensalista" data-valor="0">Mensalista cadastrado</option>
            </select>
            <label class="small">Valor da tarifa (R$):</label>
            <input name="valor" id="valorTarifa" type="number" step="0.01" value="{{ cfg.valor_diaria }}" class="form-control mb-2" readonly>
            <p class="small text-muted">Tolerância: até 15 minutos, total R$ 0,00. Acima disso, cobra a tarifa completa.</p>
            <script>
                function atualizarTarifa() {
                    const seletor = document.getElementById('tipoTarifa');
                    document.getElementById('valorTarifa').value = seletor.options[seletor.selectedIndex].dataset.valor;
                }
            </script>
            <button class="btn btn-success w-100">Registrar e Imprimir</button>
        </form>
    </div></div></div></div>

    <!-- MODAL COMPROVANTE DE ENTRADA -->
    {% if qr_entrada %}
    <div class="modal fade show" id="modalEntradaSucesso" tabindex="-1" style="display: block; background: rgba(0,0,0,0.6);" aria-modal="true" role="dialog">
        <div class="modal-dialog modal-dialog-centered"><div class="modal-content"><div class="modal-body text-center bg-white p-4">
            
            <div id="printableArea">
                {% if cfg.logo %}<img src="/logo?v={{ cfg.id }}" alt="Logo" style="width:28px; height:28px; object-fit:contain; display:block; margin:0 auto 4px auto;">{% endif %}
                <h5 class="fw-bold mb-1">{{ cfg.nome }}</h5>
                <p class="small mb-1">CNPJ: {{ cfg.cnpj }}</p>
                <p class="small mb-1">{{ cfg.endereco }}</p>
                <p class="small mb-2">Tel: {{ cfg.telefone }}</p>
                <hr style="border-top: dashed 1px #000;">
                <p class="fw-bold mb-1 text-uppercase">COMPROVANTE DE ENTRADA</p>
                <p class="small text-danger fw-bold mb-1">TALÃO Nº: {{ talao_atual }}</p>
                <p class="small mb-1">Placa: <strong>{{ placa_recente }}</strong></p>
                <p class="small mb-1">Modelo: {{ modelo_recente }} | Cor: {{ cor_recente }}</p>
                <p class="small mb-1">Entrada: {{ qr_entrada.split('|')[-1].replace('ENTRADA:', '') }}</p>
                <p class="small mb-1">Tarifa: {{ tipo_tarifa_recente|title }}</p>
                <p class="small mb-2">Valor da tarifa: R$ {{ "%.2f"|format(valor_recente) }}</p>
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
                    setTimeout(function() {
    window.print();
}, 500);
                });
            </script>
            <button type="button" class="btn btn-success w-100 mt-2" onclick="window.location.replace('/dashboard')">OK / Concluir</button>
        </div></div></div>
    </div>
    {% endif %}

    <!-- MODAL COMPROVANTE DE SAÍDA -->
    {% if saida_recente %}
    <div class="modal fade show" id="modalSaidaSucesso" tabindex="-1" style="display: block; background: rgba(0,0,0,0.6);" aria-modal="true" role="dialog">
        <div class="modal-dialog modal-dialog-centered"><div class="modal-content"><div class="modal-body text-center bg-white p-4">
            
            <div id="printableArea">
                {% if cfg.logo %}<img src="/logo?v={{ cfg.id }}" alt="Logo" style="max-height:55px; max-width:160px; object-fit:contain; margin-bottom:5px;"><br>{% endif %}
                <h5 class="fw-bold mb-1">{{ cfg.nome }}</h5>
                <p class="small mb-1">CNPJ: {{ cfg.cnpj }}</p>
                <p class="small mb-1">{{ cfg.endereco }}</p>
                <p class="small mb-2">Tel: {{ cfg.telefone }}</p>
                <hr style="border-top: dashed 1px #000;">
                <p class="fw-bold mb-1 text-uppercase">COMPROVANTE DE SAÍDA (BAIXA)</p>
                <p class="small mb-1">Placa: <strong>{{ saida_recente.placa }}</strong></p>
                <p class="small mb-1">Entrada: {{ saida_recente.hora_entrada }}</p>
                <p class="small mb-1">Saída: {{ saida_recente.hora_saida }}</p>
                <p class="small mb-1">Tarifa: {{ saida_recente.tipo_tarifa|default('diaria', true)|title }}</p>
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
            <button type="button" class="btn btn-primary w-100 mt-2" onclick="window.location.replace('/dashboard')">OK / Concluir</button>
        </div></div></div>
    </div>
    {% endif %}

    <!-- MODAL SAÍDA COM CÂMERA SCANNER E ENTRADA MANUAL -->
    <div class="modal fade" id="mSaida" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body text-center">
        <h5 class="fw-bold mb-3">Escanear ou Digitar Saída</h5>
        <div id="reader" style="width: 100%;"></div>
        
        <form action="/saida_scanner" method="POST" class="mt-3">
            <select name="forma_pagamento" class="form-select mb-2" required><option value="Dinheiro">Dinheiro</option><option value="Pix">Pix</option><option value="Cartão de débito">Cartão de débito</option><option value="Cartão de crédito">Cartão de crédito</option></select>
            <label class="form-check text-start mb-2"><input class="form-check-input" type="checkbox" name="talao_perdido" value="1"> Talão perdido</label>
            {% if session.perfil == 'admin' %}<input name="desconto" type="number" step="0.01" min="0" class="form-control mb-2" placeholder="Desconto autorizado (R$)">{% endif %}
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
        <button type="button" class="btn btn-secondary w-100 mt-3" data-bs-dismiss="modal">Fechar</button>
    </div></div></div></div>

    <!-- MODAL PÁTIO -->
    <div class="modal fade" id="mPatio" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body">
        <h5>Veículos Ativos & Comprovantes QR</h5>
        {% for c in ativos %}
        <div class="border-bottom pb-2 mb-2">
            {% if session.perfil == 'admin' %}
            <form action="/editar/{{ c.id }}" method="POST" class="d-flex gap-1 mb-1 align-items-center">
                <input name="placa" value="{{ c.placa }}" class="form-control form-control-sm text-uppercase" required style="width: 85px;">
                <input name="modelo" value="{{ c.modelo }}" class="form-control form-control-sm">
                <button class="btn btn-warning btn-sm">Salvar</button>
                <a href="/excluir/{{ c.id }}" class="btn btn-danger btn-sm">X</a>
            </form>
            {% else %}<p class="mb-1"><strong>{{ c.placa }}</strong> — {{ c.modelo }}</p>{% endif %}
            <a href="/reimprimir/{{ c.id }}" class="btn btn-info btn-sm w-100 text-white fw-bold">🖨️ Ver / Imprimir Comprovante QR Code</a>
        </div>
        {% else %}<p class="text-muted">Pátio vazio.</p>{% endfor %}
        <button type="button" class="btn btn-secondary w-100 mt-3" data-bs-dismiss="modal">Fechar</button>
    </div></div></div></div>

    <!-- MODAL CAIXA -->
    <div class="modal fade" id="mCaixa" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content"><div class="modal-body">
        <h5>Histórico de Caixa & Baixas</h5>
        <table class="table table-sm"><thead><tr><th>Placa</th><th>Entrada</th><th>Saída</th><th>Valor</th></tr></thead><tbody>
            {% for c in concluidos %}
            <tr><td>{{ c.placa }}</td><td>{{ c.hora_entrada }}</td><td>{{ c.hora_saida }}</td><td>R$ {{ "%.2f"|format(c.valor_total if c.valor_total else c.valor) }}</td></tr>
            {% else %}<tr><td colspan="4" class="text-center text-muted">Nenhum registro no caixa.</td></tr>{% endfor %}
        </tbody></table>
        <button type="button" class="btn btn-secondary w-100 mt-3" data-bs-dismiss="modal">Fechar</button>
    </div></div></div></div>

    <!-- MODAL ESTATÍSTICAS -->
    <div class="modal fade" id="mEstatisticas" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body text-center">
        <h5>Estatísticas do Estacionamento</h5>
        <p class="mt-3">Total de Vagas: <strong>{{ cfg.total_vagas }}</strong></p>
        <p>Talão Atual: <strong>Nº {{ talao_atual }}</strong></p>
        <p>Total de Veículos Ativos: <strong>{{ ativos|length }}</strong></p>
        <p>Total de Veículos Finalizados: <strong>{{ concluidos|length }}</strong></p>
        <button type="button" class="btn btn-secondary w-100 mt-3" data-bs-dismiss="modal">Fechar</button>
    </div></div></div></div>

    <!-- MODAL CONFIG -->
    <div class="modal fade" id="mConfig" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-body">
        <form action="/salvar_config" method="POST" enctype="multipart/form-data">
            <label class="small">Nome:</label><input name="nome" value="{{ cfg.nome }}" class="form-control mb-2" required>
            <label class="small fw-bold text-primary">Logo do estacionamento:</label>
            <input name="logo_arquivo" type="file" accept="image/png,image/jpeg,image/webp,image/gif" class="form-control mb-2">
            <div class="form-text mb-2">Escolha uma imagem do celular (PNG, JPG, WEBP ou GIF).</div>
            {% if cfg.logo %}
            <div class="text-center mb-2">
                <img src="/logo?v={{ cfg.id }}" alt="Prévia da logo" style="max-height:70px; max-width:180px; object-fit:contain;">
                <div><label class="small text-danger"><input type="checkbox" name="remover_logo" value="1"> Remover logo atual</label></div>
            </div>
            {% endif %}
            <label class="small">CNPJ:</label><input name="cnpj" value="{{ cfg.cnpj }}" class="form-control mb-2">
            <label class="small">Endereço:</label><input name="endereco" value="{{ cfg.endereco }}" class="form-control mb-2">
            <label class="small">Telefone:</label><input name="telefone" value="{{ cfg.telefone }}" class="form-control mb-2">
            <label class="small">Horário de Funcionamento:</label><input name="horario" value="{{ cfg.horario }}" class="form-control mb-2">
            
            <div class="row">
                <div class="col-4"><label class="small fw-bold">Diária (R$):</label><input name="valor_diaria" type="number" step="0.01" value="{{ cfg.valor_diaria }}" class="form-control mb-2" required></div>
                <div class="col-4"><label class="small fw-bold">Van/Caminh.:</label><input name="valor_van" type="number" step="0.01" value="{{ cfg.valor_van }}" class="form-control mb-2" required></div>
                <div class="col-4"><label class="small fw-bold">Pernoite (R$):</label><input name="valor_pernoite" type="number" step="0.01" value="{{ cfg.valor_pernoite }}" class="form-control mb-2" required></div>
            </div>
            <div class="row"><div class="col-4"><label class="small fw-bold">1ª hora:</label><input name="valor_hora" type="number" step="0.01" value="{{ cfg.valor_hora }}" class="form-control mb-2"></div><div class="col-4"><label class="small fw-bold">Fração:</label><input name="valor_fracao" type="number" step="0.01" value="{{ cfg.valor_fracao }}" class="form-control mb-2"></div><div class="col-4"><label class="small fw-bold">Min. fração:</label><input name="minutos_fracao" type="number" value="{{ cfg.minutos_fracao }}" class="form-control mb-2"></div></div>
            <div class="row"><div class="col-6"><label class="small fw-bold">Perda do talão:</label><input name="taxa_talao" type="number" step="0.01" value="{{ cfg.taxa_talao }}" class="form-control mb-2"></div><div class="col-6"><label class="small fw-bold">Total de vagas:</label><input name="total_vagas" type="number" value="{{ cfg.total_vagas }}" class="form-control mb-2"></div></div>

            <label class="small">Mensagem:</label><input name="mensagem" value="{{ cfg.mensagem }}" class="form-control mb-2">
            <label class="small fw-bold text-primary">Impressora Bluetooth Portátil:</label>
            <input name="imp" value="{{ cfg.impressora_status }}" class="form-control mb-3" placeholder="Ex: Thermer" required>
            <button class="btn btn-dark w-100 mb-2">Salvar Configurações</button>
        </form>
        {% if session.perfil == 'admin' %}<a href="/funcionarios" class="btn btn-primary w-100 mb-2">👥 Gerenciar Funcionários</a>{% endif %}
        <button type="button" class="btn btn-secondary w-100" data-bs-dismiss="modal">Fechar</button>
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
        <button type="button" class="btn btn-secondary w-100 mt-3" data-bs-dismiss="modal">Fechar</button>
    </div></div></div></div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
    function atualizarRelogioGlppark() {
        const el = document.getElementById('relogioGlppark');
        if (!el) return;
        const agora = new Date();
        const hora = agora.toLocaleTimeString('pt-BR', {
            timeZone: 'America/Sao_Paulo',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
        el.textContent = '🕐 ' + hora;
    }
    atualizarRelogioGlppark();
    setInterval(atualizarRelogioGlppark, 1000);

    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
    window.addEventListener('load', function () {
        if (!navigator.onLine) return location.replace('/offline');
        fetch('/api/offline_snapshot').then(r => r.ok ? r.json() : null).then(d => {
            if (!d) return;
            localStorage.setItem('novapark_empresa_atual', d.empresa_chave);
            const fila = JSON.parse(localStorage.getItem('novapark_fila_' + d.empresa_chave) || '[]');
            if (fila.length) return location.replace('/offline');
            if (!fila.length) {
                localStorage.setItem('novapark_dados_' + d.empresa_chave, JSON.stringify(d.veiculos));
                localStorage.setItem('novapark_config_' + d.empresa_chave, JSON.stringify(d.config));
            }
        }).catch(() => {});
    });
    window.addEventListener('offline', () => location.replace('/offline'));
    </script>
</body>
</html>
"""

HTML_PRIVACIDADE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Política de Privacidade — GLPPARK</title><style>body{margin:0;background:#f5f6f8;color:#202124;font-family:Arial,sans-serif;line-height:1.6}.top{background:#111827;color:white;padding:22px}.wrap{max-width:850px;margin:auto;padding:22px}.card{background:white;border-radius:12px;padding:22px;box-shadow:0 2px 10px #0001}h1{margin:0}h2{margin-top:28px;color:#0f766e}a{color:#0d6efd}.voltar{display:inline-block;margin-top:24px;padding:10px 16px;background:#111827;color:white;text-decoration:none;border-radius:7px}</style></head><body><header class="top"><div class="wrap"><h1>Política de Privacidade do GLPPARK</h1><div>Última atualização: 16 de agosto de 2026</div></div></header><main class="wrap"><article class="card"><p>Esta Política de Privacidade explica como o aplicativo GLPPARK trata dados pessoais no fornecimento de serviços de gestão de estacionamentos, em conformidade com a Lei Geral de Proteção de Dados Pessoais — LGPD (Lei nº 13.709/2018).</p><h2>1. Responsáveis pelo tratamento</h2><p>Cada empresa de estacionamento cadastrada é responsável pelas decisões sobre os dados de seus clientes, veículos e funcionários. O GLPPARK atua como fornecedor da plataforma e operador desses dados para viabilizar o serviço. Contato da plataforma: <a href="mailto:guilhermelucenaibnf@gmail.com">guilhermelucenaibnf@gmail.com</a>.</p><h2>2. Dados tratados</h2><p>O sistema pode tratar: nome, e-mail, credenciais protegidas, empresa, CNPJ, telefone e endereço; placa, modelo, cor e horários do veículo; dados de mensalistas; valores, descontos e formas de pagamento; registros de caixa, auditoria, anúncios e configurações. O GLPPARK não solicita dados completos de cartão e não processa diretamente pagamentos bancários.</p><h2>3. Câmera e QR Code</h2><p>A câmera é acessada somente após autorização do usuário, para ler QR Codes e facilitar a saída de veículos. O aplicativo não grava vídeo nem envia imagens da câmera para armazenamento.</p><h2>4. Funcionamento offline</h2><p>Para continuar funcionando sem internet, o aplicativo pode armazenar temporariamente no dispositivo dados operacionais, configurações, logo, entradas e saídas pendentes. Quando a conexão retorna, esses registros são sincronizados com a conta da empresa autenticada. Recomenda-se proteger o aparelho com senha ou biometria.</p><h2>5. Finalidades e bases legais</h2><p>Os dados são usados para autenticação, controle de acesso, execução do serviço de estacionamento, emissão de comprovantes, gestão de pátio e caixa, prevenção de duplicidades, segurança, auditoria, relatórios, suporte e cumprimento de obrigações legais ou contratuais. O tratamento pode se basear na execução de contrato, cumprimento de obrigação legal, exercício regular de direitos e legítimo interesse, conforme o caso.</p><h2>6. Compartilhamento e infraestrutura</h2><p>Os dados não são vendidos. Eles podem ser tratados por prestadores de infraestrutura estritamente necessários para hospedagem, banco de dados, segurança e funcionamento do aplicativo, sujeitos às respectivas medidas contratuais e técnicas. Uma empresa não tem acesso aos dados de outra empresa.</p><h2>7. Segurança</h2><p>O GLPPARK utiliza separação lógica por empresa, controle de perfis, senhas protegidas, conexão HTTPS, registros de auditoria e medidas para evitar sincronizações duplicadas. Nenhum sistema é totalmente imune a incidentes; por isso, administradores devem manter contas e dispositivos protegidos.</p><h2>8. Retenção e exclusão</h2><p>Os dados são conservados durante a prestação do serviço e pelo período necessário ao atendimento das finalidades, obrigações legais, prevenção de fraudes e exercício de direitos. Solicitações de correção, exportação ou exclusão serão avaliadas conforme a LGPD e eventuais deveres de retenção.</p><h2>9. Direitos dos titulares</h2><p>O titular pode solicitar confirmação de tratamento, acesso, correção, informação sobre compartilhamento, portabilidade quando aplicável, anonimização, bloqueio ou exclusão de dados desnecessários, além de revogar consentimento quando essa for a base utilizada. A solicitação deve ser enviada à empresa de estacionamento responsável ou ao contato da plataforma.</p><h2>10. Crianças e adolescentes</h2><p>O GLPPARK é destinado à gestão empresarial de estacionamentos e não é direcionado a crianças. Dados de menores não devem ser cadastrados sem fundamento legal adequado.</p><h2>11. Alterações</h2><p>Esta política poderá ser atualizada para refletir mudanças legais, técnicas ou funcionais. A data da versão mais recente ficará disponível nesta página.</p><h2>12. Contato</h2><p>Responsável pela plataforma: Guilherme de Lucena Pereira.<br>E-mail: <a href="mailto:guilhermelucenaibnf@gmail.com">guilhermelucenaibnf@gmail.com</a>.<br>Brasil.</p><a class="voltar" href="/">Voltar ao GLPPARK</a></article></main></body></html>"""

@app.route('/politica-privacidade')
def politica_privacidade():
    return HTML_PRIVACIDADE

@app.route('/')
def login():
    return render_template_string(HTML_LOGIN)

@app.route('/fazer_login', methods=['POST'])
def fazer_login():
    email = request.form.get('email')
    senha = request.form.get('senha')
    conn = obter_conexao()
    user = conn.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
    emp = conn.execute("SELECT * FROM empresas WHERE id=?", (user['empresa_id'],)).fetchone() if user else None
    conn.close()
    senha_ok = user and (check_password_hash(user['senha'], senha) if user['senha'].startswith(('pbkdf2:', 'scrypt:')) else user['senha'] == senha)
    if senha_ok:
        situacao = status_empresa(emp)
        if not acesso_empresa_liberado(emp):
            mensagem = 'Assinatura vencida. Entre em contato com a administração do GLPPARK.' if situacao == 'VENCIDA' else 'Empresa suspensa. Entre em contato com a administração do GLPPARK.'
            return f"<h3>{mensagem}</h3><a href='/'>Voltar ao login</a>", 403
        session['email'] = email
        session['usuario_id'] = user['id']
        session['empresa_id'] = user['empresa_id']
        session['perfil'] = user['perfil']
        session['plano'] = emp['plano'] or 'Basico'
        session['status_assinatura'] = situacao
        return redirect(url_for('dashboard'))
    return f"Login incorreto. <a href='/'>Voltar</a>"

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    # Cadastro público desativado: novas empresas são criadas somente pela gestão GLPPARK.
    return redirect(url_for('login'))

@app.route('/gestao-glppark', methods=['GET', 'POST'])
def gestao_glppark():
    """Painel privado do proprietário do GLPPARK para liberar novas empresas."""
    senha_mestra = os.environ.get('MASTER_PASSWORD', '').strip()
    if not senha_mestra:
        return "MASTER_PASSWORD ainda não foi configurada no servidor.", 503

    erro = ''
    sucesso = ''
    if request.method == 'POST' and request.form.get('acao') == 'login':
        if secrets.compare_digest(request.form.get('senha', ''), senha_mestra):
            session['gestor_glppark'] = True
            return redirect(url_for('gestao_glppark'))
        erro = 'Senha de gestão incorreta.'

    if not session.get('gestor_glppark'):
        html = """<!doctype html><html lang="pt-BR"><head><meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8"><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"><title>Gestão GLPPARK</title></head><body class="bg-light d-flex align-items-center justify-content-center vh-100"><div class="card shadow p-4" style="width:100%;max-width:420px"><h3 class="text-center mb-3">🔐 Gestão GLPPARK</h3>{% if erro %}<div class="alert alert-danger">{{ erro }}</div>{% endif %}<form method="post"><input type="hidden" name="acao" value="login"><label class="form-label">Senha mestra</label><input class="form-control mb-3" type="password" name="senha" required><button class="btn btn-dark w-100">Entrar</button></form><a class="btn btn-link mt-2" href="/">Voltar ao login</a></div></body></html>"""
        return render_template_string(html, erro=erro)

    if request.method == 'POST' and request.form.get('acao') == 'criar_empresa':
        empresa = request.form.get('empresa', '').strip()
        nome = request.form.get('nome_usuario', '').strip()
        email = request.form.get('email', '').lower().strip()
        senha = request.form.get('senha', '')
        plano = request.form.get('plano', 'Basico')
        if plano not in PLANOS_GLPPARK:
            plano = 'Basico'
        valor_mensal = float(request.form.get('valor_mensal', PLANOS_GLPPARK[plano]['valor_sugerido']) or PLANOS_GLPPARK[plano]['valor_sugerido'])
        vencimento = request.form.get('vencimento', '').strip()
        dias_teste = max(0, int(request.form.get('dias_teste', 0) or 0))
        teste_ate = (agora_brasilia().date() + timedelta(days=dias_teste)).isoformat() if dias_teste else ''
        status_inicial = 'TESTE' if dias_teste else 'ATIVA'
        limite_funcionarios = PLANOS_GLPPARK[plano]['limite_funcionarios']
        if not empresa or not nome or not email or len(senha) < 6:
            erro = 'Preencha todos os campos. A senha inicial precisa ter pelo menos 6 caracteres.'
        else:
            conn = obter_conexao()
            try:
                codigo = secrets.token_hex(5)
                if conn.pg:
                    empresa_id = conn.execute("INSERT INTO empresas (nome,codigo,ativo,plano,valor_mensal,vencimento,status_assinatura,limite_funcionarios,teste_ate) VALUES (?,?,?,?,?,?,?,?,?) RETURNING id", (empresa, codigo, 1, plano, valor_mensal, vencimento or None, status_inicial, limite_funcionarios, teste_ate or None)).fetchone()['id']
                else:
                    empresa_id = conn.execute("INSERT INTO empresas (nome,codigo,ativo,plano,valor_mensal,vencimento,status_assinatura,limite_funcionarios,teste_ate) VALUES (?,?,?,?,?,?,?,?,?)", (empresa, codigo, 1, plano, valor_mensal, vencimento or None, status_inicial, limite_funcionarios, teste_ate or None)).lastrowid
                conn.execute("INSERT INTO usuarios (empresa_id,nome,email,senha,perfil) VALUES (?,?,?,?,?)", (empresa_id, nome, email, generate_password_hash(senha), 'admin'))
                conn.execute("""INSERT INTO configuracoes (empresa_id,nome,cnpj,endereco,telefone,horario,mensagem,impressora_status,valor_diaria,valor_van,valor_pernoite,logo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (empresa_id, empresa, '', '', '', '07:00-22:00', 'Seja Bem-Vindo!', 'Thermer Bluetooth', 50, 30, 40, ''))
                conn.commit()
                sucesso = f'Empresa {empresa} liberada com sucesso.'
            except Exception:
                conn.rollback()
                erro = 'Não foi possível criar a empresa. Verifique se o e-mail já está cadastrado.'
            finally:
                conn.close()

    if request.method == 'POST' and request.form.get('acao') == 'criar_empresa_teste':
        plano = request.form.get('plano_teste', 'Basico')
        if plano not in PLANOS_GLPPARK:
            plano = 'Basico'
        dias_teste = max(1, min(90, int(request.form.get('dias_teste_auto', 7) or 7)))
        token = secrets.token_hex(3)
        empresa = f'Empresa Teste {token.upper()}'
        nome = 'Administrador Teste'
        email = f'teste-{token}@glppark.local'
        senha = 'Teste@' + secrets.token_hex(3)
        valor = PLANOS_GLPPARK[plano]['valor_sugerido']
        limite = PLANOS_GLPPARK[plano]['limite_funcionarios']
        teste_ate = (agora_brasilia().date() + timedelta(days=dias_teste)).isoformat()
        conn = obter_conexao()
        try:
            codigo = secrets.token_hex(5)
            if conn.pg:
                empresa_id = conn.execute("INSERT INTO empresas (nome,codigo,ativo,plano,valor_mensal,vencimento,status_assinatura,limite_funcionarios,teste_ate) VALUES (?,?,?,?,?,?,?,?,?) RETURNING id", (empresa,codigo,1,plano,valor,None,'TESTE',limite,teste_ate)).fetchone()['id']
            else:
                empresa_id = conn.execute("INSERT INTO empresas (nome,codigo,ativo,plano,valor_mensal,vencimento,status_assinatura,limite_funcionarios,teste_ate) VALUES (?,?,?,?,?,?,?,?,?)", (empresa,codigo,1,plano,valor,None,'TESTE',limite,teste_ate)).lastrowid
            conn.execute("INSERT INTO usuarios (empresa_id,nome,email,senha,perfil) VALUES (?,?,?,?,?)", (empresa_id,nome,email,generate_password_hash(senha),'admin'))
            conn.execute("INSERT INTO configuracoes (empresa_id,nome,cnpj,endereco,telefone,horario,mensagem,impressora_status,valor_diaria,valor_van,valor_pernoite,logo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (empresa_id,empresa,'','','','07:00-22:00','Ambiente de teste GLPPARK','Thermer Bluetooth',50,30,40,''))
            conn.commit()
            sucesso = f'Empresa de teste criada. Login: {email} | Senha: {senha} | Plano: {plano} | Teste até: {teste_ate}'
        except Exception as e:
            conn.rollback(); erro = f'Não foi possível criar a empresa de teste: {e}'
        finally:
            conn.close()

    if request.method == 'POST' and request.form.get('acao') in ('gerar_funcionarios_teste','simular_vencimento','excluir_empresa_teste'):
        eid = int(request.form.get('empresa_id', 0) or 0)
        conn = obter_conexao()
        try:
            principal = conn.execute("SELECT id FROM empresas WHERE COALESCE(principal,0)=1 ORDER BY id LIMIT 1").fetchone()
            principal_id_check = principal['id'] if principal else None
            emp = conn.execute("SELECT * FROM empresas WHERE id=?", (eid,)).fetchone()
            if not emp:
                erro = 'Empresa não encontrada.'
            elif eid == principal_id_check:
                erro = 'A Empresa principal do GLPPARK é protegida e não pode usar esta ação de teste.'
            elif request.form.get('acao') == 'gerar_funcionarios_teste':
                plano_atual = emp['plano'] or 'Basico'
                limite = int(emp['limite_funcionarios'] or 3)

                # Recomeça o teste desta empresa para o resultado ficar sempre visível e previsível.
                conn.execute(
                    "DELETE FROM usuarios WHERE empresa_id=? AND perfil='funcionario' AND email LIKE ?",
                    (eid, '%@glppark.local')
                )

                if plano_atual == 'Premium':
                    alvo = 15
                    limite_texto = 'ilimitado'
                elif plano_atual == 'Pro':
                    alvo = 10
                    limite_texto = '10'
                else:
                    alvo = 3
                    limite_texto = '3'

                for n in range(1, alvo + 1):
                    token = secrets.token_hex(3)
                    email = f'func-{eid}-{token}@glppark.local'
                    conn.execute(
                        "INSERT INTO usuarios(empresa_id,nome,email,senha,perfil) VALUES(?,?,?,?,?)",
                        (eid, f'Funcionário Teste {n}', email, generate_password_hash('Teste@123'), 'funcionario')
                    )

                conn.commit()
                if plano_atual == 'Premium':
                    sucesso = f'{alvo} funcionário(s) de teste criado(s). O plano Premium permanece ilimitado.'
                else:
                    sucesso = f'{alvo} funcionário(s) de teste criado(s). O limite do plano é {limite_texto}.'
            elif request.form.get('acao') == 'simular_vencimento':
                ontem = (agora_brasilia().date() - timedelta(days=1)).isoformat()
                conn.execute("UPDATE empresas SET teste_ate=NULL,vencimento=?,ativo=1,status_assinatura='ATIVA' WHERE id=?", (ontem,eid))
                conn.commit(); sucesso = 'Vencimento simulado. A empresa agora deve aparecer como VENCIDA e ter o login bloqueado.'
            else:
                # Exclui apenas empresa secundária criada para testes e todos os dados vinculados.
                for tabela in ('movimentos_caixa','caixas','auditoria','veiculos','mensalistas','anuncios','configuracoes','usuarios'):
                    conn.execute(f"DELETE FROM {tabela} WHERE empresa_id=?", (eid,))
                conn.execute("DELETE FROM empresas WHERE id=?", (eid,))
                conn.commit(); sucesso = 'Empresa de teste e seus dados foram excluídos.'
        except Exception as e:
            conn.rollback(); erro = f'Falha na ação de teste: {e}'
        finally:
            conn.close()

    if request.method == 'POST' and request.form.get('acao') in ('atualizar_empresa','trocar_plano','suspender_empresa','reativar_empresa'):
        eid = int(request.form.get('empresa_id', 0) or 0)
        conn = obter_conexao()
        try:
            acao = request.form.get('acao')
            principal = conn.execute("SELECT id FROM empresas WHERE COALESCE(principal,0)=1 ORDER BY id LIMIT 1").fetchone()
            principal_id = principal['id'] if principal else None
            if acao == 'suspender_empresa':
                if eid == principal_id:
                    erro = 'A Empresa principal do GLPPARK não pode ser suspensa.'
                else:
                    conn.execute("UPDATE empresas SET ativo=0,status_assinatura='SUSPENSA' WHERE id=?", (eid,))
                    sucesso = 'Empresa suspensa com sucesso.'
            elif acao == 'reativar_empresa':
                conn.execute("UPDATE empresas SET ativo=1,status_assinatura='ATIVA' WHERE id=?", (eid,))
                sucesso = 'Empresa reativada com sucesso.'
            elif acao == 'trocar_plano':
                plano = request.form.get('plano', 'Basico')
                if plano not in PLANOS_GLPPARK:
                    plano = 'Basico'
                valor = PLANOS_GLPPARK[plano]['valor_sugerido']
                limite = PLANOS_GLPPARK[plano]['limite_funcionarios']
                conn.execute("UPDATE empresas SET plano=?,valor_mensal=?,limite_funcionarios=? WHERE id=?", (plano, valor, limite, eid))
                sucesso = f'Plano alterado para {plano} com sucesso.'
            else:
                plano = request.form.get('plano', 'Basico')
                if plano not in PLANOS_GLPPARK: plano = 'Basico'
                valor = float(request.form.get('valor_mensal', PLANOS_GLPPARK[plano]['valor_sugerido']) or PLANOS_GLPPARK[plano]['valor_sugerido'])
                venc = request.form.get('vencimento', '').strip()
                limite = PLANOS_GLPPARK[plano]['limite_funcionarios']
                conn.execute("UPDATE empresas SET plano=?,valor_mensal=?,vencimento=?,limite_funcionarios=? WHERE id=?", (plano,valor,venc or None,limite,eid))
                sucesso = 'Plano comercial atualizado.'
            conn.commit()
        except Exception as e:
            conn.rollback(); erro = f'Não foi possível atualizar a empresa: {e}'
        finally:
            conn.close()

    conn = obter_conexao()
    empresas = conn.execute("SELECT e.*,u.nome AS admin_nome,u.email FROM empresas e LEFT JOIN usuarios u ON u.empresa_id=e.id AND u.perfil='admin' ORDER BY e.id DESC").fetchall()
    principal = conn.execute("SELECT id FROM empresas WHERE COALESCE(principal,0)=1 ORDER BY id LIMIT 1").fetchone()
    principal_id = principal['id'] if principal else None
    conn.close()
    total_empresas = len(empresas)
    total_ativas = sum(1 for e in empresas if status_empresa(e) in ('ATIVA','TESTE'))
    total_vencidas = sum(1 for e in empresas if status_empresa(e) == 'VENCIDA')
    total_suspensas = sum(1 for e in empresas if status_empresa(e) == 'SUSPENSA')
    receita_prevista = sum(float(e['valor_mensal'] or 0) for e in empresas if status_empresa(e) in ('ATIVA','TESTE'))
    html = """<!doctype html><html lang="pt-BR"><head><meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8"><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"><title>Gestão GLPPARK</title><style>
    body{background:#f4f5f7}.wrap{max-width:980px;margin:auto}.empresa-card{border:0;border-left:5px solid #d35400;border-radius:12px}.mini{font-size:.86rem}.empresa-email{overflow-wrap:anywhere}.status-box{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.dados-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.dado{background:#f8f9fa;border-radius:8px;padding:9px}.dado b{display:block;font-size:.78rem;color:#6c757d;margin-bottom:2px}.acoes-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.acoes-grid .full{grid-column:1/-1}@media(max-width:576px){.container{padding-left:12px;padding-right:12px}.topo h3{font-size:1.35rem}.dados-grid,.acoes-grid{grid-template-columns:1fr}.acoes-grid .full{grid-column:auto}.empresa-card{border-left-width:4px}.card-body{padding:14px}.form-label{font-size:.9rem;font-weight:600}}
    </style></head><body><div class="container py-3 wrap"><div class="topo d-flex justify-content-between align-items-center mb-3"><h3 class="mb-0">🚗 Gestão GLPPARK</h3><a href="/gestao-glppark/sair" class="btn btn-outline-danger btn-sm">Sair</a></div>{% if erro %}<div class="alert alert-danger">{{ erro }}</div>{% endif %}{% if sucesso %}<div class="alert alert-success">{{ sucesso }}</div>{% endif %}
    <div class="row g-2 mb-3"><div class="col-6 col-md-3"><div class="card p-2 text-center"><small>Empresas</small><b>{{total_empresas}}</b></div></div><div class="col-6 col-md-3"><div class="card p-2 text-center"><small>Ativas/Teste</small><b class="text-success">{{total_ativas}}</b></div></div><div class="col-6 col-md-3"><div class="card p-2 text-center"><small>Vencidas/Suspensas</small><b class="text-danger">{{total_vencidas + total_suspensas}}</b></div></div><div class="col-6 col-md-3"><div class="card p-2 text-center"><small>Receita prevista/mês</small><b>R$ {{'%.2f'|format(receita_prevista)}}</b></div></div></div><div class="card shadow-sm p-3 mb-3 border-warning"><h5>🧪 Modo de teste rápido</h5><p class="small text-muted mb-2">Cria login fictício automaticamente, sem precisar usar outro e-mail real.</p><form method="post"><input type="hidden" name="acao" value="criar_empresa_teste"><div class="row g-2"><div class="col-6"><label class="form-label">Plano</label><select name="plano_teste" class="form-select"><option value="Basico">Básico</option><option value="Pro">Pro</option><option value="Premium">Premium</option></select></div><div class="col-6"><label class="form-label">Dias de teste</label><input name="dias_teste_auto" type="number" min="1" max="90" value="7" class="form-control"></div></div><button class="btn btn-warning w-100 mt-2 fw-bold">Criar empresa de teste automaticamente</button></form></div><div class="card shadow-sm p-3 mb-3"><h5>Liberar nova empresa</h5><form method="post"><input type="hidden" name="acao" value="criar_empresa"><div class="row g-2"><div class="col-md-6"><label class="form-label">Empresa</label><input name="empresa" class="form-control" placeholder="Nome da empresa" required></div><div class="col-md-6"><label class="form-label">Administrador</label><input name="nome_usuario" class="form-control" placeholder="Nome do administrador" required></div><div class="col-md-6"><label class="form-label">E-mail</label><input name="email" type="email" class="form-control" placeholder="E-mail do administrador" required></div><div class="col-md-6"><label class="form-label">Senha inicial</label><input name="senha" type="password" minlength="6" class="form-control" placeholder="Mínimo 6 caracteres" required></div><div class="col-6 col-md-3"><label class="form-label">Plano</label><select name="plano" id="novoPlano" class="form-select"><option value="Basico">Basico</option><option value="Pro">Pro</option><option value="Premium">Premium</option></select></div><div class="col-6 col-md-3"><label class="form-label">Mensalidade</label><input name="valor_mensal" id="novoValor" type="number" step=".01" min="0" class="form-control" value="49.90"></div><div class="col-12 col-md-3"><label class="form-label">Vencimento</label><input name="vencimento" type="date" class="form-control"></div><div class="col-12 col-md-3"><label class="form-label">Dias de teste</label><input name="dias_teste" type="number" min="0" value="0" class="form-control"></div></div><button class="btn btn-success w-100 mt-3">Liberar empresa</button></form></div>
    <h5 class="mb-2">Empresas cadastradas</h5>
    <div class="d-grid gap-3">{% for e in empresas %}{% set st=status_empresa(e) %}<div class="card empresa-card shadow-sm"><div class="card-body"><div class="d-flex justify-content-between gap-2 align-items-start mb-3"><div><h5 class="mb-1">{{e.nome}}{% if e.id==principal_id %} <span class="badge bg-dark">GLPPARK — Administrador Geral</span>{% endif %}</h5><div class="mini text-muted">{{e.admin_nome or 'Administrador não informado'}}</div><div class="mini text-muted empresa-email">{{e.email or ''}}</div></div><span class="badge {% if st in ['ATIVA','TESTE'] %}bg-success{% elif st=='VENCIDA' %}bg-warning text-dark{% else %}bg-danger{% endif %}">{{st}}</span></div>
    <div class="dados-grid mb-3"><div class="dado"><b>Plano atual</b>{{e.plano or 'Basico'}}</div><div class="dado"><b>Mensalidade</b>R$ {{'%.2f'|format(e.valor_mensal or 0)}}</div><div class="dado"><b>Vencimento</b>{{e.vencimento or 'Não definido'}}</div><div class="dado"><b>Limite de funcionários</b>{% if (e.plano or 'Basico')=='Premium' %}Ilimitado{% else %}{{e.limite_funcionarios or 3}}{% endif %}</div>{% if e.teste_ate %}<div class="dado"><b>Teste até</b>{{e.teste_ate}}</div>{% endif %}</div>
    <div class="mb-3">
<label class="form-label">Trocar plano</label>
<form method="post">
<input type="hidden" name="acao" value="trocar_plano">
<input type="hidden" name="empresa_id" value="{{e.id}}">
<select name="plano" class="form-select mb-2" required>
<option value="Basico" {% if e.plano=='Basico' %}selected{% endif %}>Básico — R$ 49,90 — 3 funcionários</option>
<option value="Pro" {% if e.plano=='Pro' %}selected{% endif %}>Pro — R$ 89,90 — 10 funcionários</option>
<option value="Premium" {% if e.plano=='Premium' %}selected{% endif %}>Premium — R$ 149,90 — ilimitado</option>
</select>
<button class="btn btn-dark w-100">Aplicar plano selecionado</button>
</form>
</div>
<form method="post" class="mb-2"><input type="hidden" name="acao" value="atualizar_empresa"><input type="hidden" name="empresa_id" value="{{e.id}}"><input type="hidden" name="plano" value="{{e.plano or 'Basico'}}"><div class="row g-2"><div class="col-12 col-sm-6"><label class="form-label">Valor mensal personalizado</label><input name="valor_mensal" type="number" step=".01" min="0" value="{{e.valor_mensal or 0}}" class="form-control"></div><div class="col-12 col-sm-6"><label class="form-label">Vencimento</label><input name="vencimento" type="date" value="{{e.vencimento or ''}}" class="form-control"></div></div><button class="btn btn-primary w-100 mt-2">Salvar valor e vencimento</button></form>
    {% if e.id!=principal_id %}<div class="border rounded p-2 mb-2 bg-light"><div class="small fw-bold mb-2">🧪 Ferramentas de teste</div><div class="acoes-grid"><form method="post"><input type="hidden" name="acao" value="gerar_funcionarios_teste"><input type="hidden" name="empresa_id" value="{{e.id}}"><button class="btn btn-outline-primary w-100">Gerar funcionários</button></form><form method="post"><input type="hidden" name="acao" value="simular_vencimento"><input type="hidden" name="empresa_id" value="{{e.id}}"><button class="btn btn-outline-warning w-100">Simular vencimento</button></form><form method="post" class="full" onsubmit="return confirm('Excluir esta empresa e TODOS os dados dela?');"><input type="hidden" name="acao" value="excluir_empresa_teste"><input type="hidden" name="empresa_id" value="{{e.id}}"><button class="btn btn-outline-danger w-100">🗑️ Excluir empresa de teste</button></form></div></div>{% endif %}
    {% if e.id==principal_id %}<div class="alert alert-secondary py-2 mb-0 text-center">Empresa principal protegida contra suspensão.</div>{% elif st=='SUSPENSA' %}<form method="post"><input type="hidden" name="acao" value="reativar_empresa"><input type="hidden" name="empresa_id" value="{{e.id}}"><button class="btn btn-success w-100">Reativar empresa</button></form>{% else %}<form method="post"><input type="hidden" name="acao" value="suspender_empresa"><input type="hidden" name="empresa_id" value="{{e.id}}"><button class="btn btn-outline-danger w-100">Suspender empresa</button></form>{% endif %}</div></div>{% else %}<div class="alert alert-secondary">Nenhuma empresa cadastrada.</div>{% endfor %}</div></div>


<script>
(function () {
    const precosNovaEmpresa = {
        Basico: '49.90',
        Pro: '89.90',
        Premium: '149.90'
    };

    function atualizarMensalidadeNovaEmpresa() {
        const plano = document.getElementById('novoPlano');
        const valor = document.getElementById('novoValor');
        if (!plano || !valor) return;
        const preco = precosNovaEmpresa[plano.value];
        if (preco !== undefined) valor.value = preco;
    }

    document.addEventListener('DOMContentLoaded', function () {
        const plano = document.getElementById('novoPlano');
        if (!plano) return;
        plano.addEventListener('change', atualizarMensalidadeNovaEmpresa);
        plano.addEventListener('input', atualizarMensalidadeNovaEmpresa);
        atualizarMensalidadeNovaEmpresa();
    });
})();
</script>
</body></html>"""
    return render_template_string(html, empresas=empresas, erro=erro, sucesso=sucesso, status_empresa=status_empresa, principal_id=principal_id, total_empresas=total_empresas, total_ativas=total_ativas, total_vencidas=total_vencidas, total_suspensas=total_suspensas, receita_prevista=receita_prevista)

@app.route('/gestao-glppark/sair')
def sair_gestao_glppark():
    session.pop('gestor_glppark', None)
    return redirect(url_for('gestao_glppark'))

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))
    conn = obter_conexao()
    emp = conn.execute("SELECT * FROM empresas WHERE id=?", (session['empresa_id'],)).fetchone()
    conn.close()
    if not acesso_empresa_liberado(emp):
        session.clear()
        situacao = status_empresa(emp)
        mensagem = 'Assinatura vencida. Entre em contato com a administração do GLPPARK.' if situacao == 'VENCIDA' else 'Empresa suspensa. Entre em contato com a administração do GLPPARK.'
        return f"<h3>{mensagem}</h3><a href='/'>Voltar ao login</a>", 403
    session['plano'] = emp['plano'] or 'Basico'
    session['status_assinatura'] = status_empresa(emp)
    cfg, anuncios, ativos, concluidos, talao_atual = get_dados()
    empresa_vencimento = emp['vencimento'] or ''
    aviso_vencimento = ''
    if empresa_vencimento:
        try:
            venc = datetime.strptime(empresa_vencimento, '%Y-%m-%d').date()
            dias = (venc - agora_brasilia().date()).days
            if 0 <= dias <= 5:
                aviso_vencimento = f'Atenção: a assinatura vence em {dias} dia(s), em {empresa_vencimento}.'
        except ValueError:
            pass
    return render_template_string(
        HTML_DASHBOARD, cfg=cfg, anuncios=anuncios, ativos=ativos, concluidos=concluidos,
        talao_atual=talao_atual, qr_entrada=None, saida_recente=None,
        recurso_liberado=recurso_liberado, empresa_vencimento=empresa_vencimento,
        aviso_vencimento=aviso_vencimento
    )

@app.route('/logo')
def logo_empresa():
    if 'empresa_id' not in session:
        return '', 404
    conn = obter_conexao()
    cfg = conn.execute("SELECT logo FROM configuracoes WHERE empresa_id=?", (session['empresa_id'],)).fetchone()
    conn.close()
    logo = cfg['logo'] if cfg else ''
    if not logo or not logo.startswith('data:') or ';base64,' not in logo:
        return '', 404
    try:
        cabecalho, conteudo = logo.split(',', 1)
        mimetype = cabecalho[5:].split(';', 1)[0]
        resposta = app.response_class(base64.b64decode(conteudo), mimetype=mimetype)
        resposta.headers['Cache-Control'] = 'private, max-age=3600'
        return resposta
    except Exception:
        return '', 404

@app.route('/entrada', methods=['GET', 'POST'])
def entrada():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    cfg, anuncios, ativos, concluidos, talao_atual = get_dados()
    
    if request.method == 'POST':
        placa = request.form.get('placa', '').upper().strip()
        modelo = request.form.get('modelo', '')
        cor = request.form.get('cor', '')
        tipo_tarifa = request.form.get('tipo_tarifa', 'diaria')
        valores = {
            'diaria': float(cfg['valor_diaria']),
            'van': float(cfg['valor_van']),
            'pernoite': float(cfg['valor_pernoite']),
            'hora': float(cfg['valor_hora']), 'mensalista': 0.0
        }
        if tipo_tarifa not in valores:
            tipo_tarifa = 'diaria'
        valor = valores[tipo_tarifa]
        hora = agora_banco()
        
        conn = obter_conexao()
        mensalista = conn.execute("SELECT id FROM mensalistas WHERE empresa_id=? AND UPPER(placa)=? AND ativo=1", (session['empresa_id'], placa)).fetchone()
        if mensalista:
            tipo_tarifa, valor = 'mensalista', 0.0
        ja_ativo = conn.execute(
    """SELECT id, placa, modelo, cor, numero_talao, hora_entrada
       FROM veiculos
       WHERE empresa_id=? AND UPPER(TRIM(placa))=? AND status='ATIVO'
       LIMIT 1""",
    (session['empresa_id'], placa)
).fetchone()

if ja_ativo:
    conn.close()
    return f"""
    <div style="font-family:Arial; padding:25px; text-align:center;">
        <h2 style="color:#dc3545;">⚠️ VEÍCULO JÁ ESTÁ NO PÁTIO</h2>

        <p><strong>Placa:</strong> {ja_ativo['placa']}</p>
        <p><strong>Modelo:</strong> {ja_ativo['modelo']}</p>
        <p><strong>Cor:</strong> {ja_ativo['cor']}</p>
        <p><strong>Talão:</strong> {ja_ativo['numero_talao']}</p>
        <p><strong>Entrada:</strong> {ja_ativo['hora_entrada']}</p>

        <p>Não é possível registrar outra entrada com esta placa
        enquanto o veículo estiver ativo no pátio.</p>

        <a href="/dashboard"
           style="display:inline-block;padding:12px 25px;
                  background:#0d6efd;color:white;
                  text-decoration:none;border-radius:8px;">
            Voltar
        </a>
    </div>
    """
    numero_talao = request.form.get('numero_talao', '').strip()
    talao_em_uso = conn.execute(
            "SELECT 1 FROM veiculos WHERE empresa_id=? AND numero_talao=?", (session['empresa_id'], numero_talao)
        ).fetchone() if numero_talao else True
    if talao_em_uso:
        numero_talao = gerar_numero_talao(conn)

        conn.execute(
            """INSERT INTO veiculos
               (empresa_id, placa, modelo, cor, valor, tipo_tarifa, numero_talao, hora_entrada, mensalista_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session['empresa_id'], placa, modelo, cor, valor, tipo_tarifa, numero_talao, hora, mensalista['id'] if mensalista else None)
        )
        registrar_auditoria(conn, 'ENTRADA', f'Placa {placa} - tarifa {tipo_tarifa}')
        conn.commit()
        conn.close()
        
        cfg, anuncios, ativos, concluidos, _ = get_dados()
        talao_atual = numero_talao
        qr_texto = f"PLACA:{placa}|TALAO:{numero_talao}|ENTRADA:{hora}"
        
        return render_template_string(HTML_DASHBOARD, cfg=cfg, anuncios=anuncios, ativos=ativos, concluidos=concluidos, talao_atual=talao_atual, qr_entrada=qr_texto, placa_recente=placa, modelo_recente=modelo, cor_recente=cor, valor_recente=valor, tipo_tarifa_recente=tipo_tarifa, saida_recente=None, recurso_liberado=recurso_liberado, empresa_vencimento='', aviso_vencimento='')
    
    return redirect(url_for('dashboard'))

@app.route('/reimprimir/<int:id>')
def reimprimir(id):
    if 'email' not in session:
        return redirect(url_for('login'))
    conn = obter_conexao()
    eid = session['empresa_id']
    v = conn.execute("SELECT * FROM veiculos WHERE id=? AND empresa_id=?", (id,eid)).fetchone()
    cfg = conn.execute("SELECT * FROM configuracoes WHERE empresa_id=?", (eid,)).fetchone()
    anuncios = conn.execute("SELECT * FROM anuncios WHERE empresa_id=?", (eid,)).fetchall()
    ativos = conn.execute("SELECT * FROM veiculos WHERE empresa_id=? AND status='ATIVO' ORDER BY id DESC", (eid,)).fetchall()
    concluidos = conn.execute("SELECT * FROM veiculos WHERE empresa_id=? AND status='FINALIZADO' ORDER BY id DESC", (eid,)).fetchall()
    talao_atual = v['numero_talao'] if v and v['numero_talao'] else gerar_numero_talao(conn)
    if v and not v['numero_talao']:
        conn.execute("UPDATE veiculos SET numero_talao=? WHERE id=? AND empresa_id=?", (talao_atual, id, eid))
        conn.commit()
    conn.close()

    if not v:
        return redirect(url_for('dashboard'))

    qr_texto = f"PLACA:{v['placa']}|TALAO:{talao_atual}|ENTRADA:{v['hora_entrada']}"
    return render_template_string(HTML_DASHBOARD, cfg=cfg, anuncios=anuncios, ativos=ativos, concluidos=concluidos, talao_atual=talao_atual, qr_entrada=qr_texto, placa_recente=v['placa'], modelo_recente=v['modelo'], cor_recente=v['cor'], valor_recente=v['valor'], tipo_tarifa_recente=v['tipo_tarifa'] or 'diaria', saida_recente=None, recurso_liberado=recurso_liberado, empresa_vencimento='', aviso_vencimento='')

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
    eid = session['empresa_id']
    v = conn.execute("SELECT * FROM veiculos WHERE empresa_id=? AND placa=? AND status='ATIVO'", (eid, placa)).fetchone()
    
    if not v:
        conn.close()
        return f"<h3>Veículo com placa '{placa}' não encontrado no pátio ativo.</h3><a href='/dashboard'>Voltar</a>"

    fmt = "%Y-%m-%d %H:%M:%S"
    entrada = datetime.strptime(v['hora_entrada'], fmt)
    saida = agora_brasilia().replace(tzinfo=None)
    tempo_total = saida - entrada
    minutos = max(0, tempo_total.total_seconds() / 60)
    cfg = conn.execute("SELECT * FROM configuracoes WHERE empresa_id=?", (eid,)).fetchone()
    forma_pagamento = request.form.get('forma_pagamento', 'Dinheiro')
    talao_perdido = request.form.get('talao_perdido') == '1'
    desconto = float(request.form.get('desconto', 0) or 0) if session.get('perfil') == 'admin' else 0.0
    valor_final = calcular_cobranca(v, cfg, minutos, talao_perdido, desconto)
    hora_saida_str = saida.strftime(fmt)
    
    conn.execute("UPDATE veiculos SET status='FINALIZADO', hora_saida=?, valor_total=?, forma_pagamento=?, desconto=?, talao_perdido=? WHERE id=? AND empresa_id=?", (hora_saida_str, valor_final, forma_pagamento, desconto, 1 if talao_perdido else 0, v['id'], eid))
    caixa = obter_caixa_aberto(conn)
    if valor_final > 0:
        conn.execute("INSERT INTO movimentos_caixa(empresa_id,caixa_id,usuario_id,veiculo_id,tipo,descricao,valor,forma_pagamento,criado_em) VALUES(?,?,?,?,?,?,?,?,?)", (eid, caixa['id'] if caixa else None, session.get('usuario_id'), v['id'], 'RECEITA', 'Saída '+v['placa'], valor_final, forma_pagamento, hora_saida_str))
    registrar_auditoria(conn, 'SAIDA', f"Placa {v['placa']} - R$ {valor_final:.2f} - {forma_pagamento}")
    conn.commit()
    
    anuncios = conn.execute("SELECT * FROM anuncios WHERE empresa_id=?", (eid,)).fetchall()
    ativos = conn.execute("SELECT * FROM veiculos WHERE empresa_id=? AND status='ATIVO' ORDER BY id DESC", (eid,)).fetchall()
    concluidos = conn.execute("SELECT * FROM veiculos WHERE empresa_id=? AND status='FINALIZADO' ORDER BY id DESC", (eid,)).fetchall()
    talao_atual = v['numero_talao'] or gerar_numero_talao(conn)
    
    v_atualizado = conn.execute("SELECT * FROM veiculos WHERE id=? AND empresa_id=?", (v['id'], eid)).fetchone()
    conn.close()
    
    return render_template_string(HTML_DASHBOARD, cfg=cfg, anuncios=anuncios, ativos=ativos, concluidos=concluidos, talao_atual=talao_atual, saida_recente=v_atualizado, qr_entrada=None, recurso_liberado=recurso_liberado, empresa_vencimento='', aviso_vencimento='')

@app.route('/editar/<int:id>', methods=['POST'])
def editar(id):
    if 'email' not in session or session.get('perfil') != 'admin':
        return redirect(url_for('login'))
    conn = obter_conexao()
    conn.execute("UPDATE veiculos SET placa=?, modelo=? WHERE id=? AND empresa_id=?", (request.form['placa'].upper().strip(), request.form['modelo'], id, session['empresa_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/excluir/<int:id>')
def excluir(id):
    if 'email' not in session or session.get('perfil') != 'admin':
        return redirect(url_for('login'))
    conn = obter_conexao()
    conn.execute("DELETE FROM veiculos WHERE id=? AND empresa_id=?", (id, session['empresa_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/salvar_config', methods=['POST'])
def salvar_config():
    if 'email' not in session or session.get('perfil') != 'admin':
        return redirect(url_for('login'))
    try:
        conn = obter_conexao()
        cfg_atual = conn.execute("SELECT logo FROM configuracoes WHERE empresa_id=?", (session['empresa_id'],)).fetchone()
        logo = cfg_atual['logo'] if cfg_atual else ''

        if request.form.get('remover_logo') == '1':
            logo = ''

        arquivo_logo = request.files.get('logo_arquivo')
        if arquivo_logo and arquivo_logo.filename:
            tipos_permitidos = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'}
            if arquivo_logo.mimetype not in tipos_permitidos:
                conn.close()
                return "Formato de logo inválido. Use PNG, JPG, WEBP ou GIF. <a href='/dashboard'>Voltar</a>"
            dados_logo = arquivo_logo.read()
            if len(dados_logo) > 2 * 1024 * 1024:
                conn.close()
                return "A logo deve ter no máximo 2 MB. <a href='/dashboard'>Voltar</a>"
            logo = f"data:{arquivo_logo.mimetype};base64,{base64.b64encode(dados_logo).decode('ascii')}"

        nome = request.form.get('nome', '').strip() or 'GLPPARK'
        conn.execute("UPDATE configuracoes SET nome=?, cnpj=?, endereco=?, telefone=?, horario=?, mensagem=?, impressora_status=?, valor_diaria=?, valor_van=?, valor_pernoite=?, valor_hora=?, valor_fracao=?, minutos_fracao=?, taxa_talao=?, total_vagas=?, logo=? WHERE empresa_id=?",
                     (
                         nome,
                         request.form.get('cnpj', ''),
                         request.form.get('endereco', ''),
                         request.form.get('telefone', ''),
                         request.form.get('horario', ''),
                         request.form.get('mensagem', ''),
                         request.form.get('imp', ''),
                         float(request.form.get('valor_diaria', 50.0)),
                         float(request.form.get('valor_van', 30.0)),
                         float(request.form.get('valor_pernoite', 40.0)),
                         float(request.form.get('valor_hora', 10)), float(request.form.get('valor_fracao', 5)),
                         max(1, int(request.form.get('minutos_fracao', 30))), float(request.form.get('taxa_talao', 30)),
                         max(1, int(request.form.get('total_vagas', 50))), logo, session['empresa_id']
                     ))
        conn.commit()
        conn.close()
    except Exception as e:
        return f"Erro ao salvar configurações: {e}. <a href='/dashboard'>Voltar</a>"
    return redirect(url_for('dashboard'))

@app.route('/add_anuncio', methods=['POST'])
def add_anuncio():
    if 'email' not in session or session.get('perfil') != 'admin':
        return redirect(url_for('login'))
    bloqueio = exigir_recurso('anuncios')
    if bloqueio: return bloqueio
    conn = obter_conexao()
    conn.execute("INSERT INTO anuncios (empresa_id,texto) VALUES (?,?)", (session['empresa_id'], request.form['texto']))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/del_anuncio/<int:id>')
def del_anuncio(id):
    if 'email' not in session or session.get('perfil') != 'admin':
        return redirect(url_for('login'))
    bloqueio = exigir_recurso('anuncios')
    if bloqueio: return bloqueio
    conn = obter_conexao()
    conn.execute("DELETE FROM anuncios WHERE id=? AND empresa_id=?", (id, session['empresa_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/funcionarios', methods=['GET', 'POST'])
def funcionarios():
    if 'email' not in session or session.get('perfil') != 'admin':
        return redirect(url_for('dashboard'))
    conn = obter_conexao()
    erro = ''
    if request.method == 'POST':
        try:
            emp = conn.execute("SELECT * FROM empresas WHERE id=?", (session['empresa_id'],)).fetchone()
            total_func = conn.execute("SELECT COUNT(*) AS total FROM usuarios WHERE empresa_id=? AND perfil='funcionario'", (session['empresa_id'],)).fetchone()
            total_atual = total_func['total'] if hasattr(total_func, 'keys') else total_func[0]
            limite = int(emp['limite_funcionarios'] or 3) if emp else 3
            if total_atual >= limite:
                erro = f'Limite de {limite} funcionário(s) atingido para o plano {emp["plano"] if emp else "Basico"}.'
            else:
                conn.execute("INSERT INTO usuarios (empresa_id,nome,email,senha,perfil) VALUES (?,?,?,?,?)", (session['empresa_id'], request.form.get('nome','').strip(), request.form.get('email','').lower().strip(), generate_password_hash(request.form.get('senha','')), 'funcionario'))
                conn.commit()
        except Exception:
            conn.rollback(); erro = 'Não foi possível cadastrar. O e-mail pode já estar em uso.'
    lista = conn.execute("SELECT id,nome,email,perfil FROM usuarios WHERE empresa_id=? ORDER BY nome", (session['empresa_id'],)).fetchall()
    emp_info = conn.execute("SELECT plano,limite_funcionarios FROM empresas WHERE id=?", (session['empresa_id'],)).fetchone()
    total_funcionarios = sum(1 for u in lista if u['perfil'] == 'funcionario')
    conn.close()
    html = '''<!doctype html><html lang="pt-BR"><head><meta name="viewport" content="width=device-width,initial-scale=1"><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light"><div class="container py-3" style="max-width:650px"><div class="card p-3 shadow"><h3>Funcionários</h3><div class="alert alert-info py-2"><b>Plano:</b> {{emp_info.plano if emp_info else 'Basico'}} — <b>Funcionários:</b> {{total_funcionarios}} / {% if emp_info and emp_info.plano=='Premium' %}Ilimitado{% else %}{{emp_info.limite_funcionarios if emp_info else 3}}{% endif %}</div>{% if erro %}<div class="alert alert-danger">{{ erro }}</div>{% endif %}<form method="post"><input name="nome" class="form-control mb-2" placeholder="Nome" required><input name="email" type="email" class="form-control mb-2" placeholder="E-mail" required><input name="senha" type="password" class="form-control mb-2" placeholder="Senha inicial" minlength="6" required><button class="btn btn-primary w-100">Cadastrar funcionário</button></form><hr>{% for u in lista %}<div class="border rounded p-2 mb-2"><b>{{u.nome}}</b><br><small>{{u.email}} — {{u.perfil}}</small>{% if u.perfil != 'admin' %}<a class="btn btn-sm btn-outline-danger float-end" href="/excluir_funcionario/{{u.id}}">Excluir</a>{% endif %}</div>{% endfor %}<a href="/dashboard" class="btn btn-secondary">Voltar</a></div></div></body></html>'''
    return render_template_string(html, lista=lista, erro=erro, emp_info=emp_info, total_funcionarios=total_funcionarios)

@app.route('/excluir_funcionario/<int:id>')
def excluir_funcionario(id):
    if 'email' in session and session.get('perfil') == 'admin':
        conn = obter_conexao(); conn.execute("DELETE FROM usuarios WHERE id=? AND empresa_id=? AND perfil!='admin'", (id, session['empresa_id'])); conn.commit(); conn.close()
    return redirect(url_for('funcionarios'))

BASE_PRO = '''<!doctype html><html lang="pt-BR"><head><meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8"><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"><title>GLPPARK — {{titulo}}</title></head><body class="bg-light"><nav class="navbar navbar-dark bg-dark px-3"><span class="navbar-brand">GLPPARK — {{titulo}}</span><a href="/dashboard" class="btn btn-outline-light btn-sm">Painel</a></nav><main class="container py-3" style="max-width:900px">{{conteudo|safe}}</main></body></html>'''

def somente_admin(): return 'email' in session and session.get('perfil') == 'admin'

@app.route('/mensalistas', methods=['GET','POST'])
def mensalistas():
    if not somente_admin(): return redirect(url_for('dashboard'))
    bloqueio = exigir_recurso('mensalistas')
    if bloqueio: return bloqueio
    conn=obter_conexao(); eid=session['empresa_id']
    if request.method=='POST':
        conn.execute("INSERT INTO mensalistas(empresa_id,nome,documento,telefone,placa,modelo,valor_mensal,dia_vencimento,ativo) VALUES(?,?,?,?,?,?,?,?,1)",(eid,request.form['nome'],request.form.get('documento',''),request.form.get('telefone',''),request.form['placa'].upper().strip(),request.form.get('modelo',''),float(request.form.get('valor_mensal',0)),int(request.form.get('dia_vencimento',10))))
        registrar_auditoria(conn,'CADASTRO_MENSALISTA',request.form['placa'].upper().strip());conn.commit()
    lista=conn.execute("SELECT * FROM mensalistas WHERE empresa_id=? ORDER BY ativo DESC,nome",(eid,)).fetchall();conn.close()
    linhas=''.join(f'''<tr><td>{m['nome']}</td><td>{m['placa']}</td><td>R$ {float(m['valor_mensal']):.2f}</td><td>Dia {m['dia_vencimento']}</td><td>{'Ativo' if m['ativo'] else 'Inativo'}</td><td><a class="btn btn-sm btn-outline-danger" href="/mensalista_status/{m['id']}">Ativar/Inativar</a></td></tr>''' for m in lista)
    conteudo=f'''<div class="card p-3 shadow-sm mb-3"><h4>Novo mensalista</h4><form method="post"><div class="row g-2"><div class="col-md-6"><input class="form-control" name="nome" placeholder="Nome completo" required></div><div class="col-md-3"><input class="form-control" name="documento" placeholder="CPF/CNPJ"></div><div class="col-md-3"><input class="form-control" name="telefone" placeholder="Telefone"></div><div class="col-md-4"><input class="form-control text-uppercase" name="placa" placeholder="Placa" required></div><div class="col-md-4"><input class="form-control" name="modelo" placeholder="Modelo"></div><div class="col-md-2"><input class="form-control" type="number" step=".01" name="valor_mensal" placeholder="Valor"></div><div class="col-md-2"><input class="form-control" type="number" min="1" max="31" name="dia_vencimento" value="10"></div></div><button class="btn btn-success w-100 mt-2">Cadastrar</button></form></div><div class="card p-3"><div class="table-responsive"><table class="table table-sm"><thead><tr><th>Nome</th><th>Placa</th><th>Mensalidade</th><th>Vencimento</th><th>Status</th><th>Ação</th></tr></thead><tbody>{linhas or '<tr><td colspan="6">Nenhum mensalista.</td></tr>'}</tbody></table></div></div>'''
    return render_template_string(BASE_PRO,titulo='Mensalistas',conteudo=conteudo)

@app.route('/mensalista_status/<int:id>')
def mensalista_status(id):
    if somente_admin():
        conn=obter_conexao();conn.execute("UPDATE mensalistas SET ativo=CASE WHEN ativo=1 THEN 0 ELSE 1 END WHERE id=? AND empresa_id=?",(id,session['empresa_id']));registrar_auditoria(conn,'STATUS_MENSALISTA',str(id));conn.commit();conn.close()
    return redirect(url_for('mensalistas'))

@app.route('/financeiro', methods=['GET','POST'])
def financeiro():
    if not somente_admin(): return redirect(url_for('dashboard'))
    bloqueio = exigir_recurso('financeiro')
    if bloqueio: return bloqueio
    conn=obter_conexao();eid=session['empresa_id'];caixa=obter_caixa_aberto(conn)
    if request.method=='POST':
        acao=request.form.get('acao');agora=agora_banco()
        if acao=='abrir' and not caixa:
            conn.execute("INSERT INTO caixas(empresa_id,usuario_id,aberto_em,saldo_inicial,status) VALUES(?,?,?,?,?)",(eid,session['usuario_id'],agora,float(request.form.get('saldo_inicial',0)),'ABERTO'));registrar_auditoria(conn,'ABERTURA_CAIXA',request.form.get('saldo_inicial','0'))
        elif acao in ('DESPESA','RETIRADA') and caixa:
            conn.execute("INSERT INTO movimentos_caixa(empresa_id,caixa_id,usuario_id,tipo,descricao,valor,forma_pagamento,criado_em) VALUES(?,?,?,?,?,?,?,?)",(eid,caixa['id'],session['usuario_id'],acao,request.form.get('descricao',''),float(request.form.get('valor',0)),'Dinheiro',agora));registrar_auditoria(conn,acao,request.form.get('descricao',''))
        elif acao=='fechar' and caixa:
            movs=conn.execute("SELECT tipo,valor FROM movimentos_caixa WHERE caixa_id=?",(caixa['id'],)).fetchall();saldo=float(caixa['saldo_inicial'])+sum(float(x['valor']) if x['tipo']=='RECEITA' else -float(x['valor']) for x in movs);conn.execute("UPDATE caixas SET status='FECHADO',fechado_em=?,saldo_final=? WHERE id=? AND empresa_id=?",(agora,saldo,caixa['id'],eid));registrar_auditoria(conn,'FECHAMENTO_CAIXA',f'R$ {saldo:.2f}')
        conn.commit();caixa=obter_caixa_aberto(conn)
    movimentos=conn.execute("SELECT * FROM movimentos_caixa WHERE empresa_id=? ORDER BY id DESC LIMIT 100",(eid,)).fetchall();totais=conn.execute("SELECT forma_pagamento,SUM(valor) AS total FROM movimentos_caixa WHERE empresa_id=? AND tipo='RECEITA' GROUP BY forma_pagamento",(eid,)).fetchall();conn.close()
    resumo=' '.join(f'<span class="badge bg-success me-1">{x["forma_pagamento"]}: R$ {float(x["total"]):.2f}</span>' for x in totais)
    linhas=''.join(f'''<tr><td>{x['criado_em']}</td><td>{x['tipo']}</td><td>{x['descricao'] or ''}</td><td>{x['forma_pagamento'] or '-'}</td><td>R$ {float(x['valor']):.2f}</td></tr>''' for x in movimentos)
    if caixa: topo=f'''<div class="alert alert-success">Caixa aberto desde {caixa['aberto_em']} — Inicial R$ {float(caixa['saldo_inicial']):.2f}</div><form method="post" class="row g-2 mb-3"><div class="col-md-3"><select class="form-select" name="acao"><option>DESPESA</option><option>RETIRADA</option></select></div><div class="col-md-4"><input class="form-control" name="descricao" placeholder="Descrição" required></div><div class="col-md-3"><input class="form-control" type="number" step=".01" name="valor" placeholder="Valor" required></div><div class="col-md-2"><button class="btn btn-warning w-100">Lançar</button></div></form><form method="post"><input type="hidden" name="acao" value="fechar"><button class="btn btn-danger w-100 mb-3">Fechar caixa</button></form>'''
    else: topo='''<div class="alert alert-secondary">Nenhum caixa aberto.</div><form method="post" class="input-group mb-3"><input type="hidden" name="acao" value="abrir"><input class="form-control" type="number" step=".01" name="saldo_inicial" value="0"><button class="btn btn-success">Abrir caixa</button></form>'''
    conteudo=topo+f'''<div class="mb-3">{resumo}</div><div class="card p-3"><div class="table-responsive"><table class="table table-sm"><thead><tr><th>Data</th><th>Tipo</th><th>Descrição</th><th>Pagamento</th><th>Valor</th></tr></thead><tbody>{linhas or '<tr><td colspan="5">Sem movimentos.</td></tr>'}</tbody></table></div></div>'''
    return render_template_string(BASE_PRO,titulo='Financeiro',conteudo=conteudo)

@app.route('/relatorios')
def relatorios():
    if not somente_admin(): return redirect(url_for('dashboard'))
    bloqueio = exigir_recurso('relatorios')
    if bloqueio: return bloqueio
    inicio=request.args.get('inicio',agora_brasilia().strftime('%Y-%m-01'));fim=request.args.get('fim',agora_brasilia().strftime('%Y-%m-%d'));conn=obter_conexao();eid=session['empresa_id'];regs=conn.execute("SELECT * FROM veiculos WHERE empresa_id=? AND substr(hora_entrada,1,10)>=? AND substr(hora_entrada,1,10)<=? ORDER BY id DESC",(eid,inicio,fim)).fetchall();aud=conn.execute("SELECT * FROM auditoria WHERE empresa_id=? ORDER BY id DESC LIMIT 50",(eid,)).fetchall();conn.close();receita=sum(float(x['valor_total'] or 0) for x in regs if x['status']=='FINALIZADO');cancelados=sum(1 for x in regs if x['cancelado']);linhas=''.join(f'''<tr><td>{x['placa']}</td><td>{x['hora_entrada']}</td><td>{x['hora_saida'] or '-'}</td><td>{x['forma_pagamento'] or '-'}</td><td>R$ {float(x['valor_total'] or 0):.2f}</td><td>{x['status']}</td><td>{f'<a href="/cancelar_registro/{x["id"]}" class="btn btn-sm btn-outline-danger">Cancelar</a>' if not x['cancelado'] else 'Cancelado'}</td></tr>''' for x in regs);logs=''.join(f'''<li class="list-group-item"><small>{x['criado_em']} — {x['acao']} — {x['detalhes'] or ''}</small></li>''' for x in aud)
    conteudo=f'''<form class="row g-2 mb-3"><div class="col"><input class="form-control" type="date" name="inicio" value="{inicio}"></div><div class="col"><input class="form-control" type="date" name="fim" value="{fim}"></div><div class="col"><button class="btn btn-primary w-100">Filtrar</button></div></form><div class="row g-2 mb-3"><div class="col"><div class="card p-3"><b>Registros</b><span>{len(regs)}</span></div></div><div class="col"><div class="card p-3"><b>Receita</b><span>R$ {receita:.2f}</span></div></div><div class="col"><div class="card p-3"><b>Cancelados</b><span>{cancelados}</span></div></div></div><a class="btn btn-success mb-3" href="/exportar_csv?inicio={inicio}&fim={fim}">Exportar CSV</a><div class="card p-2 table-responsive"><table class="table table-sm"><thead><tr><th>Placa</th><th>Entrada</th><th>Saída</th><th>Pagamento</th><th>Total</th><th>Status</th><th>Ação</th></tr></thead><tbody>{linhas}</tbody></table></div><h5 class="mt-3">Auditoria</h5><ul class="list-group">{logs}</ul>'''
    return render_template_string(BASE_PRO,titulo='Relatórios',conteudo=conteudo)

@app.route('/cancelar_registro/<int:id>')
def cancelar_registro(id):
    if somente_admin():
        conn=obter_conexao();v=conn.execute("SELECT * FROM veiculos WHERE id=? AND empresa_id=?",(id,session['empresa_id'])).fetchone()
        if v and not v['cancelado']:
            conn.execute("UPDATE veiculos SET cancelado=1,status='CANCELADO' WHERE id=? AND empresa_id=?",(id,session['empresa_id']));conn.execute("INSERT INTO movimentos_caixa(empresa_id,usuario_id,veiculo_id,tipo,descricao,valor,forma_pagamento,criado_em) VALUES(?,?,?,?,?,?,?,?)",(session['empresa_id'],session['usuario_id'],id,'ESTORNO','Cancelamento '+v['placa'],float(v['valor_total'] or 0),v['forma_pagamento'],agora_banco()));registrar_auditoria(conn,'CANCELAMENTO',f"Placa {v['placa']}");conn.commit()
        conn.close()
    return redirect(url_for('relatorios'))

@app.route('/exportar_csv')
def exportar_csv():
    if not somente_admin(): return redirect(url_for('dashboard'))
    inicio=request.args.get('inicio','0000-01-01');fim=request.args.get('fim','9999-12-31');conn=obter_conexao();regs=conn.execute("SELECT placa,modelo,cor,tipo_tarifa,hora_entrada,hora_saida,forma_pagamento,valor_total,status FROM veiculos WHERE empresa_id=? AND substr(hora_entrada,1,10)>=? AND substr(hora_entrada,1,10)<=? ORDER BY id",(session['empresa_id'],inicio,fim)).fetchall();conn.close();saida=io.StringIO();w=csv.writer(saida,delimiter=';');w.writerow(['Placa','Modelo','Cor','Tarifa','Entrada','Saída','Pagamento','Valor','Status']);[w.writerow([r[k] for k in ('placa','modelo','cor','tipo_tarifa','hora_entrada','hora_saida','forma_pagamento','valor_total','status')]) for r in regs];return app.response_class('\ufeff'+saida.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=relatorio_novapark.csv'})

@app.route('/manifest.json')
def manifest():
    return app.response_class(json.dumps({
        'name':'GLPPARK','short_name':'GLPPARK','start_url':'/dashboard',
        'display':'standalone','background_color':'#f4f5f7','theme_color':'#d35400'
    }), mimetype='application/manifest+json')

@app.route('/sw.js')
def service_worker():
    js = """
const C='novapark-pwa-v3';
self.addEventListener('install',e=>e.waitUntil(caches.open(C).then(c=>c.addAll(['/offline','/manifest.json'])).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{if(e.request.method==='GET')e.respondWith(fetch(e.request).catch(()=>caches.match(e.request).then(r=>r||caches.match('/offline'))));});
"""
    return app.response_class(js, mimetype='application/javascript', headers={'Service-Worker-Allowed':'/'})

HTML_OFFLINE = r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GLPPARK Offline</title><link rel="manifest" href="/manifest.json"><meta name="theme-color" content="#d35400"><style>
*{box-sizing:border-box}body{margin:0;background:#f3f4f6;font:15px Arial;color:#222}.top{background:#d35400;color:#fff;padding:11px;text-align:center;font-weight:bold;position:sticky;top:0;z-index:2}.rede{padding:7px;text-align:center;background:#6c757d;color:white;font-size:12px}.wrap{max-width:720px;margin:auto;padding:12px}.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:12px}.btn{border:0;border-radius:7px;padding:12px 7px;color:#fff;font-weight:bold;background:#34495e}.green{background:#198754}.red{background:#dc3545}.orange{background:#e67e22}.card{display:none;background:white;border-radius:10px;padding:14px;margin-bottom:12px;box-shadow:0 2px 7px #0002}.card.on{display:block}label{display:block;margin-top:9px;font-weight:bold}input,select{width:100%;padding:11px;border:1px solid #ccc;border-radius:7px;margin-top:4px;font-size:16px}.full{width:100%;margin-top:11px}.item{border:1px solid #ddd;border-radius:7px;padding:10px;margin:8px 0}.muted{color:#666;font-size:12px}.logo{max-height:48px;max-width:140px;vertical-align:middle}.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}@media print{body *{visibility:hidden}#recibo,#recibo *{visibility:visible}#recibo{display:block;position:absolute;left:0;top:0;width:100%;font-family:monospace;box-shadow:none}.no-print{display:none!important}}
</style></head><body><div class="top"><img id="topLogo" class="logo" hidden> <span id="topNome">GLPPARK</span></div><div id="rede" class="rede">Modo offline</div><div class="wrap"><div class="tabs"><button class="btn green" onclick="aba('entrada')">ENTRADA</button><button class="btn red" onclick="aba('patio')">PÁTIO/SAÍDA</button><button id="configBtn" class="btn" onclick="aba('config')">CONFIG</button></div>
<section id="entrada" class="card on"><h3>Entrada de veículo</h3><label>Placa</label><input id="placa" maxlength="8" autocomplete="off"><label>Modelo</label><input id="modelo"><label>Cor</label><input id="cor"><label>Forma de cobrança</label><select id="tipo"><option value="diaria">Diária</option><option value="van">Van/Caminhão</option><option value="pernoite">Pernoite</option><option value="hora">Hora e fração</option><option value="mensalista">Mensalista</option></select><button class="btn green full" onclick="registrarEntrada()">Registrar e imprimir</button></section>
<section id="patio" class="card"><h3>Veículos no pátio</h3><div id="lista"></div></section>
<section id="config" class="card"><h3>Configurações</h3><label>Nome</label><input id="cNome"><label>CNPJ</label><input id="cCnpj"><label>Endereço</label><input id="cEndereco"><label>Telefone</label><input id="cTelefone"><label>Horário</label><input id="cHorario"><div class="grid"><div><label>Diária</label><input id="cDiaria" type="number" step=".01"></div><div><label>Van/Caminhão</label><input id="cVan" type="number" step=".01"></div></div><label>Pernoite</label><input id="cPernoite" type="number" step=".01"><label>Mensagem</label><input id="cMensagem"><label>Impressora</label><input id="cImpressora"><label>Logo</label><input id="cLogo" type="file" accept="image/*"><button class="btn full" onclick="salvarConfig()">Salvar configurações</button></section>
<section id="recibo" class="card"><div id="reciboTexto"></div><button class="btn full no-print" style="background:#111" onclick="print()">Imprimir comprovante</button><button class="btn full no-print" onclick="aba('patio')">Fechar</button></section></div><script>
const empresa=localStorage.getItem('novapark_empresa_atual')||'sem_empresa',KD='novapark_dados_'+empresa,KF='novapark_fila_'+empresa,KC='novapark_config_'+empresa;let veiculos=JSON.parse(localStorage.getItem(KD)||'[]'),fila=JSON.parse(localStorage.getItem(KF)||'[]'),cfg=JSON.parse(localStorage.getItem(KC)||'{"nome":"GLPPARK","diaria":50,"van":30,"pernoite":40}');const $=id=>document.getElementById(id);function persistir(){localStorage.setItem(KD,JSON.stringify(veiculos));localStorage.setItem(KF,JSON.stringify(fila))}function uid(){return Date.now().toString(36)+Math.random().toString(36).slice(2)}function data(s){let d=new Date(s);return isNaN(d)?s:d.toLocaleString('pt-BR')}function moeda(n){return Number(n||0).toFixed(2).replace('.',',')}function aba(id){document.querySelectorAll('.card').forEach(x=>x.classList.remove('on'));$(id).classList.add('on');if(id==='patio')listar()}
function aplicar(){['Nome','Cnpj','Endereco','Telefone','Horario','Mensagem','Impressora'].forEach(x=>$('c'+x).value=cfg[x.toLowerCase()]||'');$('cDiaria').value=cfg.diaria||0;$('cVan').value=cfg.van||0;$('cPernoite').value=cfg.pernoite||0;$('topNome').textContent=cfg.nome||'GLPPARK';if(cfg.logo){$('topLogo').src=cfg.logo;$('topLogo').hidden=false}if(cfg.perfil!=='admin'){$('configBtn').remove();$('config').remove();document.querySelector('.tabs').style.gridTemplateColumns='1fr 1fr'}}
function registrarEntrada(){let p=$('placa').value.trim().toUpperCase();if(!p)return alert('Digite a placa.');if(veiculos.some(v=>v.placa===p&&v.status==='ATIVO'))return alert('Essa placa já está no pátio.');let t=(cfg.placas_mensalistas||[]).includes(p)?'mensalista':$('tipo').value,v={offline_id:uid(),placa:p,modelo:$('modelo').value.trim(),cor:$('cor').value.trim(),tipo_tarifa:t,valor:t==='mensalista'?0:Number(cfg[t]||0),numero_talao:String(Math.floor(10000+Math.random()*90000)),hora_entrada:new Date().toISOString(),status:'ATIVO'};veiculos.push(v);fila.push({acao:'entrada',dados:v});persistir();comprovante(v,'ENTRADA');$('placa').value=$('modelo').value=$('cor').value=''}
function listar(){let a=veiculos.filter(v=>v.status==='ATIVO');$('lista').innerHTML=a.length?a.map(v=>`<div class="item"><b>${v.placa}</b> — ${v.modelo||'Modelo não informado'}<div class="muted">Entrada: ${data(v.hora_entrada)} | Talão: ${v.numero_talao||'-'}</div><button class="btn red full" onclick="darSaida('${v.offline_id}')">Dar saída</button><button class="btn orange full" onclick="comprovantePorId('${v.offline_id}')">Reimprimir</button></div>`).join(''):'<p class="muted">Nenhum veículo no pátio.</p>'}
function darSaida(id){let v=veiculos.find(x=>x.offline_id===id);if(!v)return;let agora=new Date(),mins=(agora-new Date(v.hora_entrada))/60000,bruto=0;if(mins>15&&v.tipo_tarifa!=='mensalista'){if(v.tipo_tarifa==='hora'){bruto=Number(cfg.hora||10);if(mins>60)bruto+=Math.ceil((mins-60)/Number(cfg.minutos_fracao||30))*Number(cfg.fracao||5)}else bruto=Number(v.valor)}let perdido=confirm('O talão foi perdido?');if(perdido)bruto+=Number(cfg.taxa_talao||0);let desconto=cfg.perfil==='admin'?Number(prompt('Desconto autorizado em R$ (0 para nenhum):','0')||0):0,pagamento=prompt('Pagamento: Dinheiro, Pix, Cartão de débito ou Cartão de crédito','Dinheiro')||'Dinheiro';v.hora_saida=agora.toISOString();v.valor_total=Math.max(0,bruto-desconto);v.forma_pagamento=pagamento;v.desconto=desconto;v.talao_perdido=perdido?1:0;v.status='FINALIZADO';fila.push({acao:'saida',dados:{offline_id:id,hora_saida:v.hora_saida,valor_total:v.valor_total,forma_pagamento:pagamento,desconto:desconto,talao_perdido:v.talao_perdido}});persistir();comprovante(v,'SAÍDA')}
function comprovantePorId(id){let v=veiculos.find(x=>x.offline_id===id);if(v)comprovante(v,v.status==='ATIVO'?'ENTRADA':'SAÍDA')}function comprovante(v,t){$('reciboTexto').innerHTML=`<div style="text-align:center">${cfg.logo?`<img class="logo" src="${cfg.logo}"><br>`:''}<b>${cfg.nome||'GLPPARK'}</b><br><small>${cfg.cnpj||''}<br>${cfg.endereco||''}<br>${cfg.telefone||''}</small></div><hr><b>COMPROVANTE DE ${t}</b><p>Placa: <b>${v.placa}</b><br>Modelo: ${v.modelo||'-'}<br>Cor: ${v.cor||'-'}<br>Talão: ${v.numero_talao||'-'}<br>Entrada: ${data(v.hora_entrada)}${t==='SAÍDA'?`<br>Saída: ${data(v.hora_saida)}<br><b>Total: R$ ${moeda(v.valor_total)}</b>`:''}</p><hr><div style="text-align:center">${cfg.mensagem||''}</div>`;aba('recibo');setTimeout(()=>print(),300)}
function salvarConfig(){if(cfg.perfil!=='admin')return;let n={perfil:'admin',nome:$('cNome').value.trim()||'GLPPARK',cnpj:$('cCnpj').value,endereco:$('cEndereco').value,telefone:$('cTelefone').value,horario:$('cHorario').value,diaria:Number($('cDiaria').value),van:Number($('cVan').value),pernoite:Number($('cPernoite').value),mensagem:$('cMensagem').value,impressora:$('cImpressora').value,logo:cfg.logo||''},f=$('cLogo').files[0],fim=()=>{cfg=n;localStorage.setItem(KC,JSON.stringify(cfg));fila.push({acao:'config',dados:cfg});persistir();aplicar();alert('Configurações salvas no celular.')};if(f){if(f.size>2097152)return alert('A logo deve ter no máximo 2 MB.');let r=new FileReader();r.onload=()=>{n.logo=r.result;fim()};r.readAsDataURL(f)}else fim()}
async function sincronizar(){if(!navigator.onLine||!fila.length)return;try{let r=await fetch('/api/sincronizar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({empresa_chave:empresa,operacoes:fila})});if(r.ok){fila=[];persistir();$('rede').textContent='Sincronização concluída';setTimeout(()=>location.href='/dashboard',1000)}else $('rede').textContent='Entre novamente para sincronizar'}catch(e){$('rede').textContent='Sem internet — dados seguros no celular'}}function rede(){$('rede').textContent=navigator.onLine?'Online — sincronizando...':'Modo offline — dados seguros no celular';if(navigator.onLine)sincronizar()}window.addEventListener('online',rede);window.addEventListener('offline',rede);aplicar();listar();rede();if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js');
</script></body></html>'''

@app.route('/offline')
def offline(): return HTML_OFFLINE

def iso_para_banco(valor):
    """Converte uma data ISO do celular para o horário oficial de Brasília."""
    try:
        data = datetime.fromisoformat(valor.replace('Z', '+00:00'))
        if data.tzinfo is not None:
            data = data.astimezone(FUSO_BRASIL)
        return data.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, AttributeError):
        return agora_banco()

@app.route('/api/offline_snapshot')
def offline_snapshot():
    if 'empresa_id' not in session: return {'ok':False}, 401
    eid=session['empresa_id']; conn=obter_conexao()
    emp=conn.execute('SELECT codigo FROM empresas WHERE id=?',(eid,)).fetchone(); cfg=conn.execute('SELECT * FROM configuracoes WHERE empresa_id=?',(eid,)).fetchone(); ativos=conn.execute("SELECT * FROM veiculos WHERE empresa_id=? AND status='ATIVO' ORDER BY id DESC",(eid,)).fetchall(); mensais=conn.execute("SELECT placa FROM mensalistas WHERE empresa_id=? AND ativo=1",(eid,)).fetchall()
    vs=[{'offline_id':v['offline_id'] or 'servidor-'+str(v['id']),'placa':v['placa'],'modelo':v['modelo'] or '','cor':v['cor'] or '','valor':v['valor'] or 0,'tipo_tarifa':v['tipo_tarifa'] or 'diaria','numero_talao':v['numero_talao'] or '','hora_entrada':v['hora_entrada'],'status':'ATIVO'} for v in ativos]
    conf={'perfil':session.get('perfil','funcionario'),'nome':cfg['nome'],'cnpj':cfg['cnpj'] or '','endereco':cfg['endereco'] or '','telefone':cfg['telefone'] or '','horario':cfg['horario'] or '','mensagem':cfg['mensagem'] or '','impressora':cfg['impressora_status'] or '','diaria':cfg['valor_diaria'],'van':cfg['valor_van'],'pernoite':cfg['valor_pernoite'],'hora':cfg['valor_hora'],'fracao':cfg['valor_fracao'],'minutos_fracao':cfg['minutos_fracao'],'taxa_talao':cfg['taxa_talao'],'placas_mensalistas':[m['placa'].upper() for m in mensais],'logo':cfg['logo'] or ''}
    conn.close(); return {'empresa_chave':emp['codigo'],'veiculos':vs,'config':conf}

@app.route('/api/sincronizar',methods=['POST'])
def sincronizar_offline():
    if 'empresa_id' not in session:return {'ok':False,'erro':'login'},401
    corpo=request.get_json(silent=True) or {}; eid=session['empresa_id']; conn=obter_conexao(); emp=conn.execute('SELECT codigo FROM empresas WHERE id=?',(eid,)).fetchone()
    if not emp or corpo.get('empresa_chave')!=emp['codigo']:conn.close();return {'ok':False,'erro':'empresa'},403
    try:
        for op in corpo.get('operacoes',[]):
            a,d=op.get('acao'),op.get('dados',{})
            if a=='entrada' and d.get('offline_id'):
                conn.execute('''INSERT INTO veiculos(empresa_id,offline_id,placa,modelo,cor,valor,tipo_tarifa,numero_talao,hora_entrada,status) SELECT ?,?,?,?,?,?,?,?,?,? WHERE NOT EXISTS(SELECT 1 FROM veiculos WHERE empresa_id=? AND offline_id=?)''',(eid,d['offline_id'],d.get('placa','').upper(),d.get('modelo',''),d.get('cor',''),float(d.get('valor',0)),d.get('tipo_tarifa','diaria'),d.get('numero_talao',''),iso_para_banco(d.get('hora_entrada','')),'ATIVO',eid,d['offline_id']))
            elif a=='saida' and d.get('offline_id'):
                oid=d['offline_id']; hs=iso_para_banco(d.get('hora_saida','')); total=float(d.get('valor_total',0));pag=d.get('forma_pagamento','Dinheiro');desc=float(d.get('desconto',0));perdido=int(d.get('talao_perdido',0));vid=None
                if oid.startswith('servidor-') and oid[9:].isdigit():vid=int(oid[9:]);conn.execute("UPDATE veiculos SET status='FINALIZADO',hora_saida=?,valor_total=?,forma_pagamento=?,desconto=?,talao_perdido=? WHERE id=? AND empresa_id=?",(hs,total,pag,desc,perdido,vid,eid))
                else:
                    row=conn.execute("SELECT id FROM veiculos WHERE offline_id=? AND empresa_id=?",(oid,eid)).fetchone();vid=row['id'] if row else None;conn.execute("UPDATE veiculos SET status='FINALIZADO',hora_saida=?,valor_total=?,forma_pagamento=?,desconto=?,talao_perdido=? WHERE offline_id=? AND empresa_id=?",(hs,total,pag,desc,perdido,oid,eid))
                if vid and total>0 and not conn.execute("SELECT 1 FROM movimentos_caixa WHERE empresa_id=? AND veiculo_id=? AND tipo='RECEITA'",(eid,vid)).fetchone():
                    caixa=obter_caixa_aberto(conn);conn.execute("INSERT INTO movimentos_caixa(empresa_id,caixa_id,usuario_id,veiculo_id,tipo,descricao,valor,forma_pagamento,criado_em) VALUES(?,?,?,?,?,?,?,?,?)",(eid,caixa['id'] if caixa else None,session.get('usuario_id'),vid,'RECEITA','Saída offline',total,pag,hs))
            elif a=='config' and session.get('perfil')=='admin':
                conn.execute('''UPDATE configuracoes SET nome=?,cnpj=?,endereco=?,telefone=?,horario=?,mensagem=?,impressora_status=?,valor_diaria=?,valor_van=?,valor_pernoite=?,logo=? WHERE empresa_id=?''',(d.get('nome','GLPPARK'),d.get('cnpj',''),d.get('endereco',''),d.get('telefone',''),d.get('horario',''),d.get('mensagem',''),d.get('impressora',''),float(d.get('diaria',50)),float(d.get('van',30)),float(d.get('pernoite',40)),d.get('logo',''),eid))
        conn.commit()
    except Exception as e:conn.rollback();conn.close();return {'ok':False,'erro':str(e)},400
    conn.close();return {'ok':True,'sincronizadas':len(corpo.get('operacoes',[]))}

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

inicializar_banco()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import urllib.request, json, os, secrets
from pathlib import Path
from database import (init_db, criar_usuario, verificar_login,
                      criar_token, verificar_token, listar_usuarios, desativar_usuario)

SAAS_DIR = Path(__file__).parent
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HOTMART_SECRET = os.environ.get("HOTMART_SECRET", "reactify2024")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "fabio@reactify.com")
ADMIN_SENHA = os.environ.get("ADMIN_SENHA", "admin123")

app = Flask(__name__, static_folder=str(SAAS_DIR), static_url_path="")
CORS(app, origins="*")

# CRITICO: init roda aqui para funcionar com Gunicorn E python direto
with app.app_context():
    init_db()
    criar_usuario("Fabio Mendes", ADMIN_EMAIL, ADMIN_SENHA, "admin")

def auth_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization","").replace("Bearer ","")
        user = verificar_token(token)
        if not user:
            return jsonify({"erro":"Sessao expirada. Faca login novamente."}), 401
        return f(user, *args, **kwargs)
    return decorated

@app.route("/api/ping")
def ping():
    return jsonify({"ok": True, "msg": "Reactify online!"})

@app.route("/api/login", methods=["POST"])
def login():
    try:
        d = request.json or {}
        user = verificar_login(d.get("email",""), d.get("senha",""))
        if not user:
            return jsonify({"erro":"Email ou senha incorretos"}), 401
        return jsonify({"token": criar_token(user["id"]),
                        "nome": user["nome"], "plano": user["plano"]})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route("/api/cadastro", methods=["POST"])
def cadastro():
    try:
        d = request.json or {}
        nome  = d.get("nome","").strip()
        email = d.get("email","").strip().lower()
        senha = d.get("senha","")
        if not nome or not email or len(senha) < 6:
            return jsonify({"erro":"Preencha todos os campos (min 6 caracteres)"}), 400
        if not criar_usuario(nome, email, senha):
            return jsonify({"erro":"Email ja cadastrado"}), 409
        user = verificar_login(email, senha)
        return jsonify({"token": criar_token(user["id"]),
                        "nome": user["nome"], "plano": user["plano"]})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route("/api/me")
@auth_required
def me(user):
    return jsonify({"nome": user["nome"], "email": user["email"], "plano": user["plano"]})

@app.route("/api/gerar-roteiro", methods=["POST"])
@auth_required
def gerar_roteiro(user):
    try:
        d = request.json or {}
        desc = d.get("descricao","").strip()
        if not desc:
            return jsonify({"erro":"Descreva o video"}), 400
        tons = {
            "empolgado":"MUITO EMPOLGADO: gesticula, abre olhos, fala rapido",
            "surpresa":"SURPRESA TOTAL: boca aberta, nao acredito!",
            "indigcao":"INDIGNAÇAO: que absurdo, como ninguem contou antes!",
            "inspirador":"INSPIRADOR: epico, faz querer agir agora",
            "curioso":"CURIOSO: tom de descoberta intrigante",
            "humor":"HUMOR e leveza: brincadeiras, auto-ironia"
        }
        tom = tons.get(d.get("tom","empolgado"), "empolgado")
        linhas = [
            "Voce e AGENTE DE COPY PROFISSIONAL para roteiros virais de Reels.",
            "FRAMEWORK AIDA: A(0-3s) Hook, I(3-20s) Interesse, D(20-45s) Desejo, A(45-60s) CTA.",
            f"TOM: {tom}", f"VIDEO: {desc}",
        ]
        if d.get("reacao"): linhas.append(f"REACAO: {d['reacao']}")
        if d.get("publico"): linhas.append(f"PUBLICO: {d['publico']}")
        linhas.append("ENTREGUE: 3 HOOKS, ROTEIRO COMPLETO, LEGENDA, DICA CAPCUT")
        body = json.dumps({"model":"claude-sonnet-4-20250514","max_tokens":2500,
                           "messages":[{"role":"user","content":"\n".join(linhas)}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
            headers={"Content-Type":"application/json","x-api-key":ANTHROPIC_KEY,
                     "anthropic-version":"2023-06-01"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            return jsonify({"roteiro": json.loads(r.read())["content"][0]["text"]})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route("/webhook/hotmart", methods=["POST"])
def webhook_hotmart():
    hottok = request.headers.get("X-Hotmart-Hottok","")
    if hottok != HOTMART_SECRET:
        return jsonify({"erro":"Token invalido"}), 401
    data = request.json or {}
    evento = data.get("event","")
    comprador = data.get("data",{}).get("buyer",{})
    nome = comprador.get("name","")
    email = comprador.get("email","").lower()
    if not email:
        return jsonify({"ok":False}), 400
    if evento in ["PURCHASE_APPROVED","PURCHASE_COMPLETE"]:
        senha_temp = secrets.token_urlsafe(8)
        criar_usuario(nome, email, senha_temp)
    elif evento in ["PURCHASE_REFUNDED","PURCHASE_CHARGEBACK","PURCHASE_CANCELLED"]:
        desativar_usuario(email)
    return jsonify({"ok": True})

@app.route("/api/admin/usuarios")
@auth_required
def admin_usuarios(user):
    if user["plano"] != "admin":
        return jsonify({"erro":"Sem permissao"}), 403
    return jsonify(listar_usuarios())

@app.route("/api/admin/criar-usuario", methods=["POST"])
@auth_required
def admin_criar(user):
    if user["plano"] != "admin":
        return jsonify({"erro":"Sem permissao"}), 403
    d = request.json or {}
    ok = criar_usuario(d["nome"], d["email"], d["senha"], d.get("plano","mensal"))
    return jsonify({"ok": ok})

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    return send_from_directory(str(SAAS_DIR), "index.html")

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT, debug=False)

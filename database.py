import sqlite3, hashlib, os, time, secrets, tempfile
from pathlib import Path

# Funciona tanto na Railway (/tmp) quanto localmente
_default_db = str(Path(tempfile.gettempdir()) / "reactify.db")
DB_PATH = os.environ.get("DB_PATH", _default_db)
DB = Path(DB_PATH)
DB.parent.mkdir(parents=True, exist_ok=True)

def get_db():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            plano TEXT DEFAULT 'mensal',
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now')),
            ultimo_acesso TEXT
        );
        CREATE TABLE IF NOT EXISTS sessoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            token TEXT UNIQUE,
            expira_em TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()

def hash_senha(s):
    return hashlib.sha256(s.encode()).hexdigest()

def criar_usuario(nome, email, senha, plano='mensal'):
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (nome,email,senha_hash,plano) VALUES (?,?,?,?)",
                     (nome, email, hash_senha(senha), plano))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verificar_login(email, senha):
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE email=? AND senha_hash=? AND ativo=1",
                     (email, hash_senha(senha))).fetchone()
    conn.close()
    return dict(u) if u else None

def criar_token(user_id):
    token = secrets.token_urlsafe(32)
    expira = time.strftime('%Y-%m-%d %H:%M:%S',
                           time.localtime(time.time() + 30*24*3600))
    conn = get_db()
    conn.execute("INSERT INTO sessoes (user_id,token,expira_em) VALUES (?,?,?)",
                 (user_id, token, expira))
    conn.execute("UPDATE users SET ultimo_acesso=datetime('now') WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return token

def verificar_token(token):
    if not token: return None
    conn = get_db()
    u = conn.execute("""
        SELECT u.* FROM sessoes s JOIN users u ON u.id=s.user_id
        WHERE s.token=? AND s.expira_em>datetime('now') AND u.ativo=1
    """, (token,)).fetchone()
    conn.close()
    return dict(u) if u else None

def listar_usuarios():
    conn = get_db()
    us = conn.execute("SELECT id,nome,email,plano,ativo,criado_em,ultimo_acesso FROM users ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(u) for u in us]

def desativar_usuario(email):
    conn = get_db()
    conn.execute("UPDATE users SET ativo=0 WHERE email=?", (email,))
    conn.commit()
    conn.close()

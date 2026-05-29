"""
Database — SQLite persistente via SQLAlchemy
Dados salvos em /data/corretorpro.db (volume persistente no Render)
"""
import os
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import sqlite3

# Diretório de dados — usa /data no Render (volume persistente) ou ./data local
DATA_DIR = Path(os.getenv("DATA_DIR", "/data" if os.path.exists("/data") else "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "corretorpro.db"


def _conn():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def _init_db():
    """Criar tabelas se não existirem."""
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS imoveis (
                id TEXT PRIMARY KEY,
                titulo TEXT,
                cidade TEXT,
                bairro TEXT,
                cep TEXT,
                tipo TEXT,
                quartos INTEGER,
                area TEXT,
                aluguel REAL,
                condominio REAL,
                iptu REAL,
                anunciante TEXT,
                contato TEXT,
                portal TEXT,
                no_quintoandar INTEGER DEFAULT 0,
                link TEXT UNIQUE,
                descricao TEXT,
                indicadores TEXT,
                status TEXT DEFAULT 'novo',
                data_captura TEXT,
                data_atualizacao TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS preferencias (
                chave TEXT PRIMARY KEY,
                valor TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS logs_varredura (
                id TEXT PRIMARY KEY,
                dados TEXT,
                criado_em TEXT
            )
        """)
        con.commit()


_init_db()


def _row_to_dict(row) -> Dict:
    d = dict(row)
    if d.get("indicadores"):
        try:
            d["indicadores"] = json.loads(d["indicadores"])
        except Exception:
            d["indicadores"] = []
    d["no_quintoandar"] = bool(d.get("no_quintoandar", 0))
    return d


# ── IMÓVEIS ──────────────────────────────────────────────────────────────────

def listar_imoveis(status: Optional[str] = None, cidade: Optional[str] = None) -> List[Dict]:
    sql = "SELECT * FROM imoveis WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if cidade:
        sql += " AND LOWER(cidade) = LOWER(?)"
        params.append(cidade)
    sql += " ORDER BY data_captura DESC"
    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def buscar_imovel(id: str) -> Optional[Dict]:
    with _conn() as con:
        row = con.execute("SELECT * FROM imoveis WHERE id = ?", (id,)).fetchone()
    return _row_to_dict(row) if row else None


def imovel_existe(link: str) -> bool:
    with _conn() as con:
        row = con.execute("SELECT id FROM imoveis WHERE link = ?", (link,)).fetchone()
    return row is not None


def salvar_imovel(imovel: Dict) -> Dict:
    ind = imovel.get("indicadores", [])
    ind_str = json.dumps(ind, ensure_ascii=False) if isinstance(ind, list) else str(ind)
    now = datetime.now().isoformat()

    with _conn() as con:
        # Verificar se já existe pelo link
        existing = con.execute("SELECT id FROM imoveis WHERE link = ?", (imovel.get("link", ""),)).fetchone()
        if existing:
            con.execute("""
                UPDATE imoveis SET titulo=?,cidade=?,bairro=?,tipo=?,quartos=?,area=?,
                aluguel=?,anunciante=?,contato=?,portal=?,indicadores=?,data_atualizacao=?
                WHERE link=?
            """, (
                imovel.get("titulo"), imovel.get("cidade"), imovel.get("bairro"),
                imovel.get("tipo"), imovel.get("quartos"), imovel.get("area"),
                imovel.get("aluguel"), imovel.get("anunciante"), imovel.get("contato"),
                imovel.get("portal"), ind_str, now, imovel.get("link")
            ))
        else:
            con.execute("""
                INSERT OR IGNORE INTO imoveis
                (id,titulo,cidade,bairro,tipo,quartos,area,aluguel,anunciante,contato,
                portal,no_quintoandar,link,descricao,indicadores,status,data_captura)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                imovel.get("id"), imovel.get("titulo"), imovel.get("cidade"),
                imovel.get("bairro"), imovel.get("tipo"), imovel.get("quartos"),
                imovel.get("area"), imovel.get("aluguel"), imovel.get("anunciante"),
                imovel.get("contato"), imovel.get("portal"),
                1 if imovel.get("no_quintoandar") else 0,
                imovel.get("link"), imovel.get("descricao"), ind_str,
                imovel.get("status", "novo"),
                imovel.get("data_captura", now)
            ))
        con.commit()
    return imovel


def atualizar_imovel(id: str, updates: Dict) -> Optional[Dict]:
    now = datetime.now().isoformat()
    sets, params = [], []
    for k, v in updates.items():
        if k not in ("id",):
            sets.append(f"{k} = ?")
            params.append(v)
    sets.append("data_atualizacao = ?")
    params.append(now)
    params.append(id)
    with _conn() as con:
        con.execute(f"UPDATE imoveis SET {', '.join(sets)} WHERE id = ?", params)
        con.commit()
    return buscar_imovel(id)


def deletar_imovel(id: str) -> bool:
    with _conn() as con:
        c = con.execute("DELETE FROM imoveis WHERE id = ?", (id,))
        con.commit()
    return c.rowcount > 0


# ── PREFERÊNCIAS ──────────────────────────────────────────────────────────────

PREFS_DEFAULT = {
    "cidades": ["Taubaté", "Ferraz de Vasconcelos", "Indaiatuba", "Votorantim"],
    "bairros": [], "ceps": [],
    "tipo_imovel": "todos", "min_quartos": 1,
    "aluguel_min": 500, "aluguel_max": 10000,
    "apenas_particulares": True, "filtrar_republica": True,
    "filtrar_comercial": True, "cruzar_qa": True,
    "portais": ["OLX", "Viva Real", "ZAP Imóveis", "Facebook Marketplace", "QuintoAndar (cruzamento)"],
    "frequencia": "diaria", "horario": "07:00",
    "alerta_whatsapp": False, "whatsapp_numero": "",
    "modelo_mensagem": (
        "Olá, {anunciante}! 👋\n\nVi seu anúncio em *{bairro}, {cidade}* e fiquei muito interessado.\n\n"
        "Sou corretor parceiro do QuintoAndar e acredito que seu imóvel tem ótimo perfil para a plataforma.\n\n"
        "Posso explicar melhor? Não há custo para o proprietário. 🏠✨\n\nAguardo seu retorno!"
    ),
}


def carregar_prefs() -> Dict:
    with _conn() as con:
        row = con.execute("SELECT valor FROM preferencias WHERE chave = 'config'").fetchone()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            pass
    return PREFS_DEFAULT.copy()


def salvar_prefs(prefs: Dict) -> Dict:
    valor = json.dumps(prefs, ensure_ascii=False)
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO preferencias (chave, valor) VALUES (?, ?)",
            ("config", valor)
        )
        con.commit()
    return prefs


# ── LOGS ──────────────────────────────────────────────────────────────────────

def salvar_log(log: Dict):
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO logs_varredura (id, dados, criado_em) VALUES (?, ?, ?)",
            (log.get("id", ""), json.dumps(log, ensure_ascii=False), datetime.now().isoformat())
        )
        # Manter só os 50 mais recentes
        con.execute("""
            DELETE FROM logs_varredura WHERE id NOT IN (
                SELECT id FROM logs_varredura ORDER BY criado_em DESC LIMIT 50
            )
        """)
        con.commit()


def listar_logs() -> List[Dict]:
    with _conn() as con:
        rows = con.execute("SELECT dados FROM logs_varredura ORDER BY criado_em DESC LIMIT 50").fetchall()
    result = []
    for row in rows:
        try:
            result.append(json.loads(row[0]))
        except Exception:
            pass
    return result


# ── ESTATÍSTICAS ──────────────────────────────────────────────────────────────

def estatisticas() -> Dict:
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM imoveis").fetchone()[0]
        novos = con.execute("SELECT COUNT(*) FROM imoveis WHERE status='novo'").fetchone()[0]
        contatados = con.execute("SELECT COUNT(*) FROM imoveis WHERE status='contatado'").fetchone()[0]
        convertidos = con.execute("SELECT COUNT(*) FROM imoveis WHERE status='convertido'").fetchone()[0]
        logs = con.execute("SELECT criado_em FROM logs_varredura ORDER BY criado_em DESC LIMIT 1").fetchone()
        total_logs = con.execute("SELECT COUNT(*) FROM logs_varredura").fetchone()[0]

        por_cidade = {}
        for row in con.execute("SELECT cidade, COUNT(*) as n FROM imoveis GROUP BY cidade").fetchall():
            por_cidade[row[0]] = row[1]

        por_portal = {}
        for row in con.execute("SELECT portal, COUNT(*) as n FROM imoveis GROUP BY portal").fetchall():
            por_portal[row[0]] = row[1]

    return {
        "total": total, "novos": novos,
        "contatados": contatados, "convertidos": convertidos,
        "por_cidade": por_cidade, "por_portal": por_portal,
        "ultima_varredura": logs[0] if logs else None,
        "total_varreduras": total_logs,
    }


def _agrupar(lista, campo):
    resultado = {}
    for item in lista:
        val = item.get(campo, "Desconhecido")
        resultado[val] = resultado.get(val, 0) + 1
    return resultado

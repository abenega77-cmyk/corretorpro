"""
Database — JSON persistente em diretório do código
No Render Free, o diretório da aplicação persiste entre reinícios (não entre deploys)
Preferências salvas como variável de ambiente para persistência total
"""
import os
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

# Usar /tmp/data que persiste entre reinícios no mesmo container
DATA_DIR = Path(os.getenv("DATA_DIR", "/tmp/corretorpro_data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

IMOVEIS_FILE = DATA_DIR / "imoveis.json"
PREFS_FILE   = DATA_DIR / "preferencias.json"
LOGS_FILE    = DATA_DIR / "varreduras.json"

# Preferências padrão embutidas — sempre disponíveis mesmo após reinício
PREFS_DEFAULT = {
    "cidades": ["Taubaté", "Ferraz de Vasconcelos", "Indaiatuba", "Votorantim"],
    "bairros": [], "ceps": [],
    "tipo_imovel": "todos", "min_quartos": 1,
    "aluguel_min": 500, "aluguel_max": 10000,
    "apenas_particulares": True, "filtrar_republica": True,
    "filtrar_comercial": True, "cruzar_qa": True,
    "portais": ["OLX","Viva Real","ZAP Imóveis","Facebook Marketplace","QuintoAndar (cruzamento)"],
    "frequencia": "diaria", "horario": "07:00",
    "alerta_whatsapp": False, "whatsapp_numero": "",
    "modelo_mensagem": (
        "Olá, {anunciante}! 👋\n\nVi seu anúncio em *{bairro}, {cidade}* e fiquei muito interessado.\n\n"
        "Sou corretor parceiro do QuintoAndar e acredito que seu imóvel tem ótimo perfil para a plataforma.\n\n"
        "Posso explicar melhor? Não há custo para o proprietário. 🏠✨\n\nAguardo seu retorno!"
    ),
}

def _read(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _write(path: Path, data: Any):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass

# ── IMÓVEIS ──────────────────────────────────────────────────────────────────

def listar_imoveis(status=None, cidade=None):
    data = _read(IMOVEIS_FILE) or []
    if status:
        data = [i for i in data if i.get("status") == status]
    if cidade:
        data = [i for i in data if i.get("cidade","").lower() == cidade.lower()]
    return sorted(data, key=lambda x: x.get("data_captura",""), reverse=True)

def buscar_imovel(id: str):
    data = _read(IMOVEIS_FILE) or []
    return next((i for i in data if i["id"] == id), None)

def imovel_existe(link: str) -> bool:
    data = _read(IMOVEIS_FILE) or []
    return any(i.get("link") == link for i in data)

def salvar_imovel(imovel: Dict) -> Dict:
    data = _read(IMOVEIS_FILE) or []
    for i, ex in enumerate(data):
        if ex.get("link") == imovel.get("link"):
            data[i] = {**ex, **imovel, "data_atualizacao": datetime.now().isoformat()}
            _write(IMOVEIS_FILE, data)
            return data[i]
    data.append(imovel)
    _write(IMOVEIS_FILE, data)
    return imovel

def atualizar_imovel(id: str, updates: Dict):
    data = _read(IMOVEIS_FILE) or []
    for i, im in enumerate(data):
        if im["id"] == id:
            data[i] = {**im, **updates, "data_atualizacao": datetime.now().isoformat()}
            _write(IMOVEIS_FILE, data)
            return data[i]
    return None

def deletar_imovel(id: str) -> bool:
    data = _read(IMOVEIS_FILE) or []
    nova = [i for i in data if i["id"] != id]
    if len(nova) < len(data):
        _write(IMOVEIS_FILE, nova)
        return True
    return False

# ── PREFERÊNCIAS ──────────────────────────────────────────────────────────────

def carregar_prefs() -> Dict:
    # 1. Tentar arquivo local
    saved = _read(PREFS_FILE)
    if saved:
        return saved
    # 2. Tentar variável de ambiente (backup persistente)
    env_prefs = os.getenv("CORRETORPRO_PREFS")
    if env_prefs:
        try:
            return json.loads(env_prefs)
        except Exception:
            pass
    # 3. Default
    return PREFS_DEFAULT.copy()

def salvar_prefs(prefs: Dict) -> Dict:
    _write(PREFS_FILE, prefs)
    return prefs

# ── LOGS ──────────────────────────────────────────────────────────────────────

def salvar_log(log: Dict):
    data = _read(LOGS_FILE) or []
    data.insert(0, log)
    _write(LOGS_FILE, data[:50])

def listar_logs():
    return _read(LOGS_FILE) or []

# ── ESTATÍSTICAS ──────────────────────────────────────────────────────────────

def estatisticas() -> Dict:
    imoveis = _read(IMOVEIS_FILE) or []
    logs = _read(LOGS_FILE) or []
    result = {
        "total": len(imoveis),
        "novos": sum(1 for i in imoveis if i.get("status") == "novo"),
        "contatados": sum(1 for i in imoveis if i.get("status") == "contatado"),
        "convertidos": sum(1 for i in imoveis if i.get("status") == "convertido"),
        "por_cidade": {},
        "por_portal": {},
        "ultima_varredura": logs[0].get("inicio") if logs else None,
        "total_varreduras": len(logs),
    }
    for im in imoveis:
        c = im.get("cidade","?")
        p = im.get("portal","?")
        result["por_cidade"][c] = result["por_cidade"].get(c,0) + 1
        result["por_portal"][p] = result["por_portal"].get(p,0) + 1
    return result

def _agrupar(lista, campo):
    r = {}
    for item in lista:
        v = item.get(campo,"?")
        r[v] = r.get(v,0) + 1
    return r

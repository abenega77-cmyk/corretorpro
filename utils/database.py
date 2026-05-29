import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(exist_ok=True)

IMOVEIS_FILE = DATA_DIR / "imoveis.json"
PREFS_FILE   = DATA_DIR / "preferencias.json"
LOGS_FILE    = DATA_DIR / "varreduras.json"


def _read(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(path: Path, data: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


# ── IMÓVEIS ──────────────────────────────────────────────────────────────────

def listar_imoveis(status: Optional[str] = None, cidade: Optional[str] = None) -> List[Dict]:
    data = _read(IMOVEIS_FILE) or []
    if status:
        data = [i for i in data if i.get("status") == status]
    if cidade:
        data = [i for i in data if i.get("cidade", "").lower() == cidade.lower()]
    return sorted(data, key=lambda x: x.get("data_captura", ""), reverse=True)


def buscar_imovel(id: str) -> Optional[Dict]:
    data = _read(IMOVEIS_FILE) or []
    return next((i for i in data if i["id"] == id), None)


def imovel_existe(link: str) -> bool:
    data = _read(IMOVEIS_FILE) or []
    return any(i.get("link") == link for i in data)


def salvar_imovel(imovel: Dict) -> Dict:
    data = _read(IMOVEIS_FILE) or []
    # Verificar duplicata por link
    for i, existing in enumerate(data):
        if existing.get("link") == imovel.get("link"):
            data[i] = {**existing, **imovel, "data_atualizacao": datetime.now().isoformat()}
            _write(IMOVEIS_FILE, data)
            return data[i]
    data.append(imovel)
    _write(IMOVEIS_FILE, data)
    return imovel


def atualizar_imovel(id: str, updates: Dict) -> Optional[Dict]:
    data = _read(IMOVEIS_FILE) or []
    for i, imovel in enumerate(data):
        if imovel["id"] == id:
            data[i] = {**imovel, **updates, "data_atualizacao": datetime.now().isoformat()}
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
    return _read(PREFS_FILE) or {
        "cidades": ["Taubaté", "Ferraz de Vasconcelos", "Indaiatuba", "Votorantim"],
        "bairros": [],
        "ceps": [],
        "tipo_imovel": "todos",
        "min_quartos": 1,
        "aluguel_min": 500,
        "aluguel_max": 10000,
        "apenas_particulares": True,
        "filtrar_republica": True,
        "filtrar_comercial": True,
        "cruzar_qa": True,
        "portais": ["OLX", "Viva Real", "ZAP Imóveis", "Facebook Marketplace"],
        "frequencia": "diaria",
        "horario": "07:00",
        "alerta_whatsapp": True,
        "modelo_mensagem": (
            "Olá, {anunciante}! 👋\n\nVi seu anúncio do imóvel em *{bairro}, {cidade}* "
            "e fiquei muito interessado.\n\nSou corretor parceiro do QuintoAndar e acredito "
            "que seu imóvel tem um ótimo perfil para ser anunciado na plataforma.\n\n"
            "Posso te explicar melhor? Não há custo para o proprietário. 🏠✨\n\nAguardo seu retorno!"
        ),
    }


def salvar_prefs(prefs: Dict) -> Dict:
    _write(PREFS_FILE, prefs)
    return prefs


# ── LOGS DE VARREDURA ─────────────────────────────────────────────────────────

def salvar_log(log: Dict):
    data = _read(LOGS_FILE) or []
    data.insert(0, log)
    data = data[:50]  # Manter apenas os 50 últimos
    _write(LOGS_FILE, data)


def listar_logs() -> List[Dict]:
    return _read(LOGS_FILE) or []


# ── ESTATÍSTICAS ──────────────────────────────────────────────────────────────

def estatisticas() -> Dict:
    imoveis = _read(IMOVEIS_FILE) or []
    logs = _read(LOGS_FILE) or []
    return {
        "total": len(imoveis),
        "novos": sum(1 for i in imoveis if i.get("status") == "novo"),
        "contatados": sum(1 for i in imoveis if i.get("status") == "contatado"),
        "convertidos": sum(1 for i in imoveis if i.get("status") == "convertido"),
        "descartados": sum(1 for i in imoveis if i.get("status") == "descartado"),
        "por_cidade": _agrupar(imoveis, "cidade"),
        "por_portal": _agrupar(imoveis, "portal"),
        "ultima_varredura": logs[0].get("inicio") if logs else None,
        "total_varreduras": len(logs),
    }


def _agrupar(lista: List[Dict], campo: str) -> Dict:
    resultado = {}
    for item in lista:
        val = item.get(campo, "Desconhecido")
        resultado[val] = resultado.get(val, 0) + 1
    return resultado

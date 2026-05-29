"""
Scraper Chaves na Mão — busca imóveis de proprietário direto
Este portal funciona em servidores em nuvem (OLX bloqueia com 403)
"""
import httpx
import hashlib
import re
import asyncio
from bs4 import BeautifulSoup
from typing import List, Dict
from datetime import datetime

BASE_URL = "https://www.chavesnamao.com.br"

CIDADE_SLUG = {
    "Taubaté":               "taubate",
    "Ferraz de Vasconcelos": "ferraz-de-vasconcelos",
    "Indaiatuba":            "indaiatuba",
    "Valinhos":              "valinhos",
    "Vinhedo":               "vinhedo",
    "Hortolândia":           "hortolandia",
    "Votorantim":            "votorantim",
    "Praia Grande":          "praia-grande",
    "Suzano":                "suzano",
    "Sumaré":                "sumare",
    "Jacareí":               "jacarei",
    "Ribeirão Pires":        "ribeirao-pires",
    "Embu das Artes":        "embu-das-artes",
    "Poá":                   "poa",
    "Sorocaba":              "sorocaba",
    "São José dos Campos":   "sao-jose-dos-campos",
    "Campinas":              "campinas",
    "Guarulhos":             "guarulhos",
    "Ribeirão Preto":        "ribeirao-preto",
    "São Paulo":             "sao-paulo",
    "Mogi das Cruzes":       "mogi-das-cruzes",
    "Osasco":                "osasco",
    "Barueri":               "barueri",
    "Jundiaí":               "jundiai",
    "Santo André":           "santo-andre",
    "São Bernardo do Campo": "sao-bernardo-do-campo",
    "Santos":                "santos",
    "Americana":             "americana",
    "Sumaré":                "sumare",
    "Itaquaquecetuba":       "itaquaquecetuba",
    "Jacareí":               "jacarei",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

PALAVRAS_PROFISSIONAL = [
    "creci", "imóveis ltda", "imobiliária", "administradora",
    "gestão de imóveis", "corretor de imóveis", "real estate",
    "grupo imobiliário", "já tenho corretor", "tenho corretor",
]
PALAVRAS_REPUBLICA = [
    "república", "quarto compartilhado", "quarto em", "aluga quarto",
    "pensão", "vaga em casa", "casa compartilhada",
]
PALAVRAS_COMERCIAL = [
    "comercial", "galpao", "galpão", "ponto-comercial", "predio",
    "loja", "sala-comercial", "escritorio", "clinica",
]


def _gerar_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


async def buscar_chavesnamao(cidade: str, prefs: Dict) -> List[Dict]:
    slug = CIDADE_SLUG.get(cidade)
    if not slug:
        return []

    url = f"{BASE_URL}/imoveis-para-alugar-direto-com-o-proprietario/sp-{slug}/"
    resultados = []

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=20) as client:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            links = soup.select("a[href*='/imovel/']")

            for link in links:
                href = link.get("href", "")
                if not href or "imovel" not in href:
                    continue

                full_url = f"{BASE_URL}{href}" if href.startswith("/") else href
                texto = link.get_text(strip=True)
                txt_lower = (texto + href).lower()

                # Filtrar profissionais
                if prefs.get("apenas_particulares", True):
                    if any(p in txt_lower for p in PALAVRAS_PROFISSIONAL):
                        continue

                # Filtrar república
                if prefs.get("filtrar_republica", True):
                    if any(p in txt_lower for p in PALAVRAS_REPUBLICA):
                        continue

                # Filtrar comercial
                if prefs.get("filtrar_comercial", True):
                    if any(w in href.lower() for w in PALAVRAS_COMERCIAL):
                        continue

                # Extrair dados do href
                preco_m = re.search(r"RS(\d+)", href)
                quartos_m = re.search(r"(\d+)-quarto", href)
                area_m = re.search(r"(\d+)m2", href)
                tipo_m = re.search(r"/(casa|apartamento|kitnet|sobrado|studio|flat)", href)
                bairro_m = re.search(rf"sp-{slug}-([a-z-]+?)(?:/id-|\Z)", href)

                aluguel = float(preco_m.group(1)) if preco_m else None
                quartos = int(quartos_m.group(1)) if quartos_m else None
                area = f"{area_m.group(1)}m²" if area_m else None
                tipo = preco_m and tipo_m and tipo_m.group(1).title() or (tipo_m.group(1).title() if tipo_m else "Imóvel")
                bairro = bairro_m.group(1).replace("-", " ").title() if bairro_m else ""

                # Filtrar por aluguel
                if aluguel:
                    if aluguel < prefs.get("aluguel_min", 0):
                        continue
                    if aluguel > prefs.get("aluguel_max", 99999):
                        continue

                # Filtrar por quartos
                if quartos and quartos < int(prefs.get("min_quartos", 1)):
                    continue

                resultados.append({
                    "id": _gerar_id(full_url),
                    "titulo": texto[:120] if texto else f"{tipo} em {cidade}",
                    "cidade": cidade,
                    "bairro": bairro,
                    "tipo": tipo,
                    "quartos": quartos,
                    "area": area,
                    "aluguel": aluguel,
                    "anunciante": "Proprietário Direto",
                    "portal": "Chaves na Mão",
                    "link": full_url,
                    "indicadores": ["Portal dedicado a proprietários diretos", "Sem imobiliária"],
                    "no_quintoandar": False,
                    "status": "novo",
                    "data_captura": datetime.now().isoformat(),
                })

        except Exception:
            pass

    return resultados


async def buscar_chavesnamao_multiplas(cidades: List[str], prefs: Dict) -> List[Dict]:
    todos = []
    for cidade in cidades:
        resultado = await buscar_chavesnamao(cidade, prefs)
        todos.extend(resultado)
        await asyncio.sleep(1.5)
    return todos

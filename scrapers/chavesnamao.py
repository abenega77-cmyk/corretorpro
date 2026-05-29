"""
Scraper Chaves na Mão com verificação individual de cada anúncio.
Acessa a página do anúncio para confirmar se é proprietário direto
e extrair o telefone/WhatsApp quando disponível.
"""
import httpx
import hashlib
import re
import asyncio
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime

BASE_URL = "https://www.chavesnamao.com.br"

CIDADE_SLUG = {
    "Taubaté": "taubate", "Ferraz de Vasconcelos": "ferraz-de-vasconcelos",
    "Indaiatuba": "indaiatuba", "Valinhos": "valinhos", "Vinhedo": "vinhedo",
    "Hortolândia": "hortolandia", "Votorantim": "votorantim",
    "Praia Grande": "praia-grande", "Suzano": "suzano", "Sumaré": "sumare",
    "Jacareí": "jacarei", "Ribeirão Pires": "ribeirao-pires",
    "Embu das Artes": "embu-das-artes", "Poá": "poa", "Sorocaba": "sorocaba",
    "São José dos Campos": "sao-jose-dos-campos", "Campinas": "campinas",
    "Guarulhos": "guarulhos", "Ribeirão Preto": "ribeirao-preto",
    "São Paulo": "sao-paulo", "Mogi das Cruzes": "mogi-das-cruzes",
    "Osasco": "osasco", "Barueri": "barueri", "Jundiaí": "jundiai",
    "Santo André": "santo-andre", "São Bernardo do Campo": "sao-bernardo-do-campo",
    "Santos": "santos", "Americana": "americana", "Itaquaquecetuba": "itaquaquecetuba",
}

HEADERS_HTTP = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# Keywords que confirmam profissional/imobiliária
IMOB_KEYWORDS = [
    "creci", "imóveis ltda", "imobiliária", "administradora",
    "gestão de imóveis", "corretor de imóveis", "real estate",
    "incorporadora", "imóvel anunciado por", "anunciado por",
    "leads4sales", "plataforma leads", "código do imóvel: cm",
    "s/a", "s.a.", "ltda", "eireli", "grupo imobiliário",
]

# Keywords que indicam comercial
COMERCIAL_KEYWORDS = [
    "comercial", "galpao", "galpão", "ponto-comercial",
    "predio", "loja", "sala-comercial", "escritorio", "clinica",
]

# Keywords de república/compartilhado
REPUBLICA_KEYWORDS = [
    "república", "quarto compartilhado", "quarto em",
    "aluga quarto", "pensão", "vaga em casa",
]


def _gerar_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


async def _verificar_anuncio(client: httpx.AsyncClient, url: str) -> Dict:
    """
    Acessa a página individual do anúncio e retorna:
    - eh_profissional: True se for imobiliária/corretor
    - contato: telefone/WhatsApp se encontrado
    - nome_anunciante: nome do anunciante se identificado
    """
    try:
        r = await client.get(url, timeout=12)
        if r.status_code != 200:
            return {"eh_profissional": False, "contato": None, "nome_anunciante": None}

        html = r.text

        # Extrair chunks Next.js (fonte mais confiável)
        chunks = re.findall(r'self\.__next_f\.push\(\[1,"([^"]{10,})"\]\)', html)
        texto_chunks = " ".join(chunks).lower()

        # Texto geral
        soup = BeautifulSoup(html, "html.parser")
        texto_pagina = soup.get_text(" ", strip=True).lower()
        texto_completo = texto_chunks + " " + texto_pagina

        # 1. Verificar se é profissional
        eh_profissional = any(k in texto_completo for k in IMOB_KEYWORDS)

        # 2. Extrair nome do anunciante
        nome_match = re.search(
            r'anunciado por\s+([^-<\n]{5,60}?)(?:\s*-\s*creci|\s*<|\s*,|\s*\.|através)',
            texto_completo, re.IGNORECASE
        )
        nome_anunciante = nome_match.group(1).strip().title() if nome_match else None

        # 3. Extrair telefone/WhatsApp
        contato = None

        # Buscar link wa.me direto
        wpp_links = soup.select("a[href*='wa.me/']")
        for wl in wpp_links:
            num = re.search(r'wa\.me/(\d{10,13})', wl.get("href", ""))
            if num:
                contato = num.group(1)
                break

        # Buscar link tel:
        if not contato:
            tel_links = soup.select("a[href^='tel:']")
            for tl in tel_links:
                num = re.sub(r'\D', '', tl.get("href", "").replace("tel:", ""))
                if len(num) >= 10:
                    contato = num
                    break

        # Buscar telefone no texto dos chunks (mais confiável que texto geral)
        if not contato:
            # Padrão: (XX) XXXXX-XXXX ou (XX) XXXX-XXXX no conteúdo do anúncio
            # Filtrar apenas DDD válidos do Brasil (11-99)
            fones_raw = re.findall(r'\((\d{2})\)\s*(\d{4,5})[-\s]?(\d{4})', texto_chunks)
            for ddd, parte1, parte2 in fones_raw:
                if 11 <= int(ddd) <= 99:
                    contato = f"{ddd}{parte1}{parte2}"
                    break

        return {
            "eh_profissional": eh_profissional,
            "contato": contato,
            "nome_anunciante": nome_anunciante,
        }

    except Exception:
        return {"eh_profissional": False, "contato": None, "nome_anunciante": None}


async def buscar_chavesnamao(cidade: str, prefs: Dict) -> List[Dict]:
    slug = CIDADE_SLUG.get(cidade)
    if not slug:
        return []

    url_listagem = f"{BASE_URL}/imoveis-para-alugar-direto-com-o-proprietario/sp-{slug}/"
    resultados = []

    async with httpx.AsyncClient(headers=HEADERS_HTTP, follow_redirects=True, timeout=20) as client:
        # 1. Buscar listagem
        try:
            resp = await client.get(url_listagem)
            if resp.status_code != 200:
                return []
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        links_raw = soup.select("a[href*='/imovel/']")

        # Filtrar comercial pela URL antes de verificar individualmente
        candidatos = []
        for link in links_raw:
            href = link.get("href", "")
            if not href or "imovel" not in href:
                continue
            href_lower = href.lower()
            # Filtrar comercial pela URL
            if prefs.get("filtrar_comercial", True):
                if any(w in href_lower for w in COMERCIAL_KEYWORDS):
                    continue
            # Filtrar república pela URL
            if prefs.get("filtrar_republica", True):
                texto = link.get_text(strip=True).lower()
                if any(w in texto for w in REPUBLICA_KEYWORDS):
                    continue

            full_url = f"{BASE_URL}{href}" if href.startswith("/") else href

            # Extrair dados básicos da URL
            preco_m = re.search(r"RS(\d+)", href)
            quartos_m = re.search(r"(\d+)-quarto", href)
            area_m = re.search(r"(\d+)m2", href)
            tipo_m = re.search(r"/(casa|apartamento|kitnet|sobrado|studio|flat)", href)
            bairro_m = re.search(rf"sp-{slug}-([a-z-]+?)(?:/id-|\Z)", href)

            aluguel = float(preco_m.group(1)) if preco_m else None
            quartos = int(quartos_m.group(1)) if quartos_m else None

            # Filtrar faixa de aluguel
            if aluguel:
                if aluguel < prefs.get("aluguel_min", 0): continue
                if aluguel > prefs.get("aluguel_max", 99999): continue
            if quartos and quartos < int(prefs.get("min_quartos", 1)):
                continue

            candidatos.append({
                "url": full_url,
                "aluguel": aluguel,
                "quartos": quartos,
                "area": f"{area_m.group(1)}m²" if area_m else None,
                "tipo": tipo_m.group(1).title() if tipo_m else "Imóvel",
                "bairro": bairro_m.group(1).replace("-", " ").title() if bairro_m else "",
                "titulo": link.get_text(strip=True)[:120] or f"Imóvel em {cidade}",
            })

        # 2. Verificar cada anúncio individualmente (com limite de concorrência)
        semaphore = asyncio.Semaphore(3)  # máx 3 requisições simultâneas

        async def verificar_com_semaphore(candidato):
            async with semaphore:
                verificacao = await _verificar_anuncio(client, candidato["url"])
                await asyncio.sleep(0.5)  # delay gentil
                return {**candidato, **verificacao}

        tarefas = [verificar_com_semaphore(c) for c in candidatos]
        verificados = await asyncio.gather(*tarefas, return_exceptions=True)

        # 3. Filtrar apenas proprietários diretos confirmados
        for v in verificados:
            if isinstance(v, Exception):
                continue
            # Descartar se confirmado como profissional
            if v.get("eh_profissional") and prefs.get("apenas_particulares", True):
                continue

            nome = v.get("nome_anunciante") or "Proprietário Direto"

            indicadores = ["Portal 'Direto c/ Proprietário'"]
            if not v.get("eh_profissional"):
                indicadores.append("✅ Verificado: sem CRECI na descrição")
            if v.get("contato"):
                indicadores.append("📞 Telefone extraído automaticamente")

            resultados.append({
                "id": _gerar_id(v["url"]),
                "titulo": v["titulo"],
                "cidade": cidade,
                "bairro": v["bairro"],
                "tipo": v["tipo"],
                "quartos": v["quartos"],
                "area": v["area"],
                "aluguel": v["aluguel"],
                "anunciante": nome,
                "contato": v.get("contato"),
                "portal": "Chaves na Mão",
                "link": v["url"],
                "indicadores": indicadores,
                "no_quintoandar": False,
                "status": "novo",
                "data_captura": datetime.now().isoformat(),
            })

    return resultados


async def buscar_chavesnamao_multiplas(cidades: List[str], prefs: Dict) -> List[Dict]:
    todos = []
    for cidade in cidades:
        resultado = await buscar_chavesnamao(cidade, prefs)
        todos.extend(resultado)
        await asyncio.sleep(2)
    return todos

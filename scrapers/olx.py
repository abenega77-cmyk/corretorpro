"""
Scraper OLX — busca imóveis de aluguel por cidade/bairro
Estratégia: HTTP direto com headers realistas → parse HTML → filtro de particulares
"""
import httpx
import hashlib
import re
import asyncio
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime

# Mapeamento cidade → slug OLX
CIDADE_SLUG = {
    "Taubaté":                 ("vale-do-paraiba-e-litoral-norte", "taubate"),
    "Ferraz de Vasconcelos":   ("sao-paulo-e-regiao",              "ferraz-de-vasconcelos"),
    "Indaiatuba":              ("grande-campinas",                  "indaiatuba"),
    "Valinhos":                ("grande-campinas",                  "valinhos"),
    "Vinhedo":                 ("grande-campinas",                  "vinhedo"),
    "Hortolândia":             ("grande-campinas",                  "hortolandia"),
    "Votorantim":              ("regiao-de-sorocaba",               "votorantim"),
    "Praia Grande":            ("baixada-santista",                 "praia-grande"),
    "Suzano":                  ("sao-paulo-e-regiao",               "suzano"),
    "Sumaré":                  ("grande-campinas",                  "sumare"),
    "Jacareí":                 ("vale-do-paraiba-e-litoral-norte",  "jacarei"),
    "Ribeirão Pires":          ("grande-campinas",                  "ribeirao-pires"),
    "Embu das Artes":          ("sao-paulo-e-regiao",               "embu-das-artes"),
    "Poá":                     ("sao-paulo-e-regiao",               "poa"),
    "Mauá":                    ("sao-paulo-e-regiao",               "maua"),
    "Sorocaba":                ("regiao-de-sorocaba",               "sorocaba"),
    "São José dos Campos":     ("vale-do-paraiba-e-litoral-norte",  "sao-jose-dos-campos"),
    "Ribeirão Preto":          ("interior-sp",                      "ribeirao-preto"),
    "Campinas":                ("grande-campinas",                  "campinas"),
    "Guarulhos":               ("sao-paulo-e-regiao",               "guarulhos"),
    "Osasco":                  ("sao-paulo-e-regiao",               "osasco"),
    "Barueri":                 ("sao-paulo-e-regiao",               "barueri"),
    "Jundiaí":                 ("grande-campinas",                  "jundiai"),
    "Santo André":             ("sao-paulo-e-regiao",               "santo-andre"),
    "São Bernardo do Campo":   ("sao-paulo-e-regiao",               "sao-bernardo-do-campo"),
    "Santos":                  ("baixada-santista",                  "santos"),
    "São Paulo":               ("sao-paulo-e-regiao",               "sao-paulo"),
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "DNT": "1",
}

# Palavras que indicam anúncio de imobiliária/corretor
PALAVRAS_PROFISSIONAL = [
    "creci", "imóveis ltda", "imobiliária", "administradora",
    "gestão de imóveis", "corretor de imóveis", "imobiliário",
    "real estate", "assessoria imobiliária", "grupo imobiliário",
]

# Palavras que indicam república ou quarto compartilhado
PALAVRAS_REPUBLICA = [
    "república", "quarto compartilhado", "vaga em república",
    "quarto em apto", "aluga quarto", "aluga-se quarto",
    "quarto individual", "quarto em casa", "pensão",
    "casa compartilhada",
]

# Palavras que indicam proprietário direto
PALAVRAS_PROPRIETARIO = [
    "direto com o proprietário", "proprietário direto", "falo direto",
    "não aceito corretor", "não busco imobiliária", "sem imobiliária",
    "proprietário", "dono do imóvel", "aos corretores não",
    "apenas locatários",
]


def _gerar_id(link: str) -> str:
    return hashlib.md5(link.encode()).hexdigest()[:12]


def _extrair_preco(texto: str) -> Optional[float]:
    match = re.search(r"R\$\s*([\d.,]+)", texto)
    if match:
        valor = match.group(1).replace(".", "").replace(",", ".")
        try:
            return float(valor)
        except Exception:
            return None
    return None


def _extrair_quartos(texto: str) -> Optional[int]:
    match = re.search(r"(\d+)\s*[Qq]uart", texto)
    if match:
        return int(match.group(1))
    return None


def _extrair_area(texto: str) -> Optional[str]:
    match = re.search(r"(\d+)\s*m²", texto)
    return f"{match.group(1)}m²" if match else None


def _e_profissional(texto: str, nome_anunciante: str = "") -> bool:
    txt = (texto + " " + nome_anunciante).lower()
    return any(p in txt for p in PALAVRAS_PROFISSIONAL)


def _e_republica(titulo: str, descricao: str = "") -> bool:
    txt = (titulo + " " + descricao).lower()
    return any(p in txt for p in PALAVRAS_REPUBLICA)


def _indicadores_proprietario(texto: str) -> List[str]:
    txt = texto.lower()
    indicadores = []
    for p in PALAVRAS_PROPRIETARIO:
        if p in txt:
            indicadores.append(f"Menciona: '{p}'")
    if re.search(r"\b(11|12|13|14|15|16|17|18|19)\s?9?\d{4}[-\s]?\d{4}", txt):
        indicadores.append("Telefone/WhatsApp no anúncio")
    return indicadores


async def _parse_listagem(html: str, cidade: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    resultados = []

    # OLX renderiza cards em <li> com data-cy ou seções
    cards = soup.select("li[data-cy='l-card'], section[data-cy='l-card'], div[data-cy='l-card']")
    
    # Fallback: pegar todos os links de anúncios
    if not cards:
        links = soup.select("a[href*='/imoveis/']")
        seen = set()
        for a in links:
            href = a.get("href", "")
            if href and href not in seen and "olx.com.br" in href:
                seen.add(href)
                titulo = a.get_text(strip=True)[:120]
                if titulo and len(titulo) > 10:
                    resultados.append({
                        "id": _gerar_id(href),
                        "titulo": titulo,
                        "cidade": cidade,
                        "link": href,
                        "portal": "OLX",
                        "anunciante": "A confirmar",
                        "indicadores": [],
                        "status": "novo",
                        "data_captura": datetime.now().isoformat(),
                    })
        return resultados[:20]

    for card in cards:
        try:
            link_el = card.select_one("a[href*='/imoveis/']")
            if not link_el:
                continue
            href = link_el.get("href", "")
            if not href:
                continue

            titulo_el = card.select_one("h2, h3, [data-cy='ad-title']")
            titulo = titulo_el.get_text(strip=True) if titulo_el else link_el.get_text(strip=True)[:100]

            preco_el = card.select_one("[data-cy='ad-price'], .price")
            preco_txt = preco_el.get_text(strip=True) if preco_el else ""
            aluguel = _extrair_preco(preco_txt)

            local_el = card.select_one("[data-cy='ad-location'], .location")
            local_txt = local_el.get_text(strip=True) if local_el else ""

            desc_el = card.select_one("p, .description")
            desc = desc_el.get_text(strip=True)[:300] if desc_el else ""

            tag_profissional = card.select_one("[data-cy='ad-pro-label'], .professional")
            is_pro = bool(tag_profissional) or _e_profissional(desc + titulo)

            tag_direto = card.find(string=lambda t: t and "direto com o proprietário" in t.lower())
            
            texto_completo = f"{titulo} {desc} {local_txt}"
            indicadores = _indicadores_proprietario(texto_completo)
            if tag_direto:
                indicadores.insert(0, "Tag 'Direto com o proprietário'")

            resultados.append({
                "id": _gerar_id(href),
                "titulo": titulo[:120],
                "cidade": cidade,
                "bairro": local_txt.split(",")[0].strip() if "," in local_txt else local_txt,
                "tipo": "Casa" if "casa" in titulo.lower() or "sobrado" in titulo.lower() else "Apartamento",
                "quartos": _extrair_quartos(titulo + desc),
                "area": _extrair_area(titulo + desc),
                "aluguel": aluguel,
                "anunciante": "Particular" if not is_pro else "Profissional",
                "portal": "OLX",
                "link": href if href.startswith("http") else f"https://www.olx.com.br{href}",
                "descricao": desc,
                "indicadores": indicadores,
                "no_quintoandar": False,
                "status": "novo",
                "is_profissional": is_pro,
                "data_captura": datetime.now().isoformat(),
            })
        except Exception:
            continue

    return resultados


async def _buscar_via_google(cidade: str, prefs: Dict) -> List[Dict]:
    """
    Fallback: busca links da OLX via Google quando a OLX bloqueia requisições diretas.
    A OLX bloqueia IPs de servidor (403). IPs residenciais (extensão do browser) funcionam.
    """
    slug_info = CIDADE_SLUG.get(cidade)
    if not slug_info:
        return []
    regiao, slug_cidade = slug_info
    base = f"site:sp.olx.com.br/{regiao}/imoveis aluguel {cidade} -imobiliária -CRECI"
    google_url = f"https://www.google.com/search?q={base.replace(' ', '+')}&num=20"

    resultados = []
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=20) as client:
        try:
            resp = await client.get(google_url)
            if resp.status_code != 200:
                return []

            # Extrair links da OLX do HTML do Google
            links = re.findall(
                r'https://sp\.olx\.com\.br/[a-z-]+/imoveis/[a-z0-9-]+-\d+',
                resp.text
            )
            links = list(dict.fromkeys(links))[:15]  # Deduplicar, máximo 15

            for link in links:
                titulo = re.sub(r'-\d+$', '', link.split("/imoveis/")[-1]).replace("-", " ").title()
                resultados.append({
                    "id": _gerar_id(link),
                    "titulo": titulo[:100],
                    "cidade": cidade,
                    "tipo": "Casa" if "casa" in titulo.lower() or "sobrado" in titulo.lower() else "Apartamento",
                    "anunciante": "A verificar no anúncio",
                    "portal": "OLX",
                    "link": link,
                    "indicadores": [],
                    "no_quintoandar": False,
                    "status": "novo",
                    "data_captura": datetime.now().isoformat(),
                    "is_profissional": False,
                })
        except Exception:
            pass

    return resultados


async def buscar_olx(cidade: str, prefs: Dict) -> List[Dict]:
    """Busca imóveis na OLX para uma cidade específica."""
    if cidade not in CIDADE_SLUG:
        return []

    regiao, slug_cidade = CIDADE_SLUG[cidade]
    url = f"https://www.olx.com.br/imoveis/aluguel/estado-sp/{regiao}/{slug_cidade}"

    # Filtro de particulares
    if prefs.get("apenas_particulares"):
        url += "?sf=1"

    resultados = []
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        try:
            resp = await client.get(url)

            # OLX bloqueia IPs de servidor (403) — usar fallback via Google
            if resp.status_code == 403:
                return await _buscar_via_google(cidade, prefs)

            if resp.status_code != 200:
                return []

            imoveis = await _parse_listagem(resp.text, cidade)

            for im in imoveis:
                if prefs.get("filtrar_republica") and _e_republica(im.get("titulo", ""), im.get("descricao", "")):
                    continue
                if prefs.get("apenas_particulares") and im.get("is_profissional"):
                    continue
                aluguel = im.get("aluguel")
                if aluguel:
                    if aluguel < prefs.get("aluguel_min", 0):
                        continue
                    if aluguel > prefs.get("aluguel_max", 99999):
                        continue
                quartos = im.get("quartos")
                min_q = prefs.get("min_quartos", 1)
                if quartos and quartos < min_q:
                    continue
                im.pop("is_profissional", None)
                resultados.append(im)

            await asyncio.sleep(1.5)

        except httpx.TimeoutException:
            resultados = await _buscar_via_google(cidade, prefs)
        except Exception:
            pass

    return resultados


async def buscar_olx_multiplas_cidades(cidades: List[str], prefs: Dict) -> List[Dict]:
    """Busca em múltiplas cidades com delay entre requisições."""
    todos = []
    for cidade in cidades:
        resultado = await buscar_olx(cidade, prefs)
        todos.extend(resultado)
        await asyncio.sleep(2)
    return todos

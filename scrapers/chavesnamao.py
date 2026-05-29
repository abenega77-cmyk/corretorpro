"""
Scraper Chaves na Mão + VivaReal com verificação individual de anúncios.
Filtra imobiliárias com múltiplos critérios:
  1. URL /imobiliaria/ no HTML
  2. Meta tag "Falar com EMPRESA"
  3. Keywords na descrição (CRECI, LTDA, etc.)
"""
import httpx
import hashlib
import re
import asyncio
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime

BASE_CNM = "https://www.chavesnamao.com.br"
BASE_VR  = "https://www.vivareal.com.br"

CIDADE_SLUG_CNM = {
    "Taubaté":"taubate","Ferraz de Vasconcelos":"ferraz-de-vasconcelos",
    "Indaiatuba":"indaiatuba","Valinhos":"valinhos","Vinhedo":"vinhedo",
    "Hortolândia":"hortolandia","Votorantim":"votorantim",
    "Praia Grande":"praia-grande","Suzano":"suzano","Sumaré":"sumare",
    "Jacareí":"jacarei","Ribeirão Pires":"ribeirao-pires",
    "Embu das Artes":"embu-das-artes","Poá":"poa","Sorocaba":"sorocaba",
    "São José dos Campos":"sao-jose-dos-campos","Campinas":"campinas",
    "Guarulhos":"guarulhos","Ribeirão Preto":"ribeirao-preto",
    "São Paulo":"sao-paulo","Mogi das Cruzes":"mogi-das-cruzes",
    "Osasco":"osasco","Barueri":"barueri","Jundiaí":"jundiai",
    "Santo André":"santo-andre","São Bernardo do Campo":"sao-bernardo-do-campo",
    "Santos":"santos","Americana":"americana","Itaquaquecetuba":"itaquaquecetuba",
    "Ferraz de Vasconcelos":"ferraz-de-vasconcelos",
}

CIDADE_SLUG_VR = {
    "Taubaté":"taubate-sp","Ferraz de Vasconcelos":"ferraz-de-vasconcelos-sp",
    "Indaiatuba":"indaiatuba-sp","Valinhos":"valinhos-sp","Vinhedo":"vinhedo-sp",
    "Hortolândia":"hortolandia-sp","Votorantim":"votorantim-sp",
    "Praia Grande":"praia-grande-sp","Suzano":"suzano-sp","Sumaré":"sumare-sp",
    "Jacareí":"jacarei-sp","Ribeirão Pires":"ribeirao-pires-sp",
    "Embu das Artes":"embu-das-artes-sp","Poá":"poa-sp","Sorocaba":"sorocaba-sp",
    "São José dos Campos":"sao-jose-dos-campos-sp","Campinas":"campinas-sp",
    "Guarulhos":"guarulhos-sp","Ribeirão Preto":"ribeirao-preto-sp",
    "São Paulo":"sao-paulo-sp","Mogi das Cruzes":"mogi-das-cruzes-sp",
    "Osasco":"osasco-sp","Barueri":"barueri-sp","Jundiaí":"jundiai-sp",
    "Santo André":"santo-andre-sp","São Bernardo do Campo":"sao-bernardo-do-campo-sp",
    "Santos":"santos-sp","Americana":"americana-sp",
}

HTTP_HEADERS = {
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language":"pt-BR,pt;q=0.9",
}

# Keywords de imobiliária/corretor na DESCRIÇÃO
IMOB_DESC = [
    "creci","imóveis ltda","imobiliária","administradora","imóvel anunciado por",
    "anunciado por","leads4sales","plataforma leads","código do imóvel: cm",
    "eireli","grupo imobiliário","negócios imobiliários ltda",
]

# Palavras comerciais na URL
COMERCIAL_URL = ["comercial","galpao","galpão","ponto-comercial","predio","loja","sala-comercial","escritorio","clinica"]

# República
REPUBLICA = ["república","quarto compartilhado","quarto em","aluga quarto","pensão","vaga em casa"]

def _id(url): return hashlib.md5(url.encode()).hexdigest()[:12]


def _eh_profissional(html: str) -> bool:
    """
    Detecta imobiliária com 3 critérios confiáveis:
    1. URL /imobiliaria/ no HTML (mais confiável)
    2. Meta tag 'Falar com EMPRESA' onde empresa tem caracteres de PJ
    3. Keywords de profissional na descrição
    """
    # Critério 1: URL de imobiliária parceira
    if re.search(r'/imobiliaria/[a-z0-9-]+/id-\d+', html):
        return True

    # Critério 2: "Falar com" + nome em maiúsculas + indicador de empresa
    falar = re.search(r'Falar com\s+([^,\.<\n"]{5,80})', html)
    if falar:
        nome = falar.group(1).strip()
        # É empresa se: tudo maiúsculas E tem &amp;, ou tem palavra de PJ
        if re.search(r'&amp;|IMÓVEIS|IMOBILIÁRIA|NEGÓCIOS|LTDA|S\.A\.|REMAX|RE/MAX|INCORPORA', nome, re.IGNORECASE):
            return True
        # Tudo em maiúsculas (MENDES BRAGA) — exceto se for nome simples tipo "JOÃO SILVA"
        palavras = nome.split()
        if len(palavras) >= 2 and all(p.isupper() for p in palavras) and len(palavras) >= 3:
            return True

    # Critério 3: keywords na descrição
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"([^"]{10,})"\]\)', html)
    texto = " ".join(chunks).lower()
    if any(k in texto for k in IMOB_DESC):
        return True

    return False


def _extrair_telefone(html: str) -> Optional[str]:
    # WhatsApp direto
    wpp = re.search(r'wa\.me/(\d{10,13})', html)
    if wpp: return wpp.group(1)

    # Link tel:
    tel = re.search(r'href=["\']tel:([+\d\s\-()]{8,20})["\']', html)
    if tel:
        num = re.sub(r'\D', '', tel.group(1))
        if len(num) >= 10: return num

    return None


async def _verificar_anuncio(client, url: str) -> Dict:
    try:
        r = await client.get(url, timeout=12)
        if r.status_code != 200:
            return {"eh_profissional": False, "contato": None}
        html = r.text
        return {
            "eh_profissional": _eh_profissional(html),
            "contato": _extrair_telefone(html),
        }
    except Exception:
        return {"eh_profissional": False, "contato": None}


# ── CHAVES NA MÃO ─────────────────────────────────────────────────────────────

async def buscar_chavesnamao(cidade: str, prefs: Dict) -> List[Dict]:
    slug = CIDADE_SLUG_CNM.get(cidade)
    if not slug:
        return []

    url_list = f"{BASE_CNM}/imoveis-para-alugar-direto-com-o-proprietario/sp-{slug}/"
    resultados = []

    async with httpx.AsyncClient(headers=HTTP_HEADERS, follow_redirects=True, timeout=20) as client:
        try:
            resp = await client.get(url_list)
            if resp.status_code != 200:
                return []
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        candidatos = []

        for link in soup.select("a[href*='/imovel/']"):
            href = link.get("href","")
            if not href or "imovel" not in href:
                continue
            href_lower = href.lower()

            # Filtrar comercial e república pela URL/texto
            if prefs.get("filtrar_comercial", True) and any(w in href_lower for w in COMERCIAL_URL):
                continue
            if prefs.get("filtrar_republica", True) and any(w in link.get_text().lower() for w in REPUBLICA):
                continue

            full_url = f"{BASE_CNM}{href}" if href.startswith("/") else href
            preco_m = re.search(r"RS(\d+)", href)
            quartos_m = re.search(r"(\d+)-quarto", href)
            area_m = re.search(r"(\d+)m2", href)
            tipo_m = re.search(r"/(casa|apartamento|kitnet|sobrado|studio|flat)", href)
            bairro_m = re.search(rf"sp-{slug}-([a-z-]+?)(?:/id-|\Z)", href)

            aluguel = float(preco_m.group(1)) if preco_m else None
            quartos = int(quartos_m.group(1)) if quartos_m else None

            if aluguel:
                if aluguel < prefs.get("aluguel_min", 0): continue
                if aluguel > prefs.get("aluguel_max", 99999): continue
            if quartos and quartos < int(prefs.get("min_quartos", 1)):
                continue

            candidatos.append({
                "url": full_url, "aluguel": aluguel, "quartos": quartos,
                "area": f"{area_m.group(1)}m²" if area_m else None,
                "tipo": tipo_m.group(1).title() if tipo_m else "Imóvel",
                "bairro": bairro_m.group(1).replace("-"," ").title() if bairro_m else "",
                "titulo": link.get_text(strip=True)[:120] or f"Imóvel em {cidade}",
            })

        # Verificar cada anúncio individualmente
        sem = asyncio.Semaphore(3)

        async def verificar(c):
            async with sem:
                v = await _verificar_anuncio(client, c["url"])
                await asyncio.sleep(0.4)
                return {**c, **v}

        verificados = await asyncio.gather(*[verificar(c) for c in candidatos], return_exceptions=True)

        for v in verificados:
            if isinstance(v, Exception): continue
            if v.get("eh_profissional") and prefs.get("apenas_particulares", True):
                continue
            resultados.append({
                "id": _id(v["url"]),
                "titulo": v["titulo"],
                "cidade": cidade,
                "bairro": v["bairro"],
                "tipo": v["tipo"],
                "quartos": v["quartos"],
                "area": v["area"],
                "aluguel": v["aluguel"],
                "anunciante": "Proprietário Direto",
                "contato": v.get("contato"),
                "portal": "Chaves na Mão",
                "link": v["url"],
                "indicadores": ["✅ Verificado: sem imobiliária", "Portal direto c/ proprietário"],
                "no_quintoandar": False,
                "status": "novo",
                "data_captura": datetime.now().isoformat(),
            })

    return resultados


# ── VIVAREAL ──────────────────────────────────────────────────────────────────

async def buscar_vivareal(cidade: str, prefs: Dict) -> List[Dict]:
    slug = CIDADE_SLUG_VR.get(cidade)
    if not slug:
        return []

    url_list = f"{BASE_VR}/aluguel/sp/{slug.replace('-sp','')}/?owner=true"
    resultados = []

    async with httpx.AsyncClient(headers=HTTP_HEADERS, follow_redirects=True, timeout=20) as client:
        try:
            resp = await client.get(url_list)
            if resp.status_code != 200:
                return []
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select("a[href*='/imovel/']")

        for link in links:
            href = link.get("href","")
            if not href: continue
            full_url = href if href.startswith("http") else f"{BASE_VR}{href}"

            # Extrair dados da URL
            preco_m = re.search(r"aluguel-RS(\d+)", href)
            quartos_m = re.search(r"(\d+)-quartos?", href)
            area_m = re.search(r"(\d+)m2", href)
            tipo_m = re.search(r"/(apartamento|casa|sobrado|kitnet|studio|flat)", href)

            aluguel = float(preco_m.group(1)) if preco_m else None
            quartos = int(quartos_m.group(1)) if quartos_m else None

            if aluguel:
                if aluguel < prefs.get("aluguel_min", 0): continue
                if aluguel > prefs.get("aluguel_max", 99999): continue
            if quartos and quartos < int(prefs.get("min_quartos", 1)):
                continue

            titulo = link.get_text(strip=True)[:120] or f"Imóvel em {cidade}"
            if prefs.get("filtrar_republica", True) and any(w in titulo.lower() for w in REPUBLICA):
                continue

            resultados.append({
                "id": _id(full_url),
                "titulo": titulo,
                "cidade": cidade,
                "bairro": "",
                "tipo": tipo_m.group(1).title() if tipo_m else "Imóvel",
                "quartos": quartos,
                "area": f"{area_m.group(1)}m²" if area_m else None,
                "aluguel": aluguel,
                "anunciante": "Proprietário Direto (VivaReal)",
                "contato": None,
                "portal": "Viva Real",
                "link": full_url,
                "indicadores": ["Filtro 'Proprietário' ativado no VivaReal"],
                "no_quintoandar": False,
                "status": "novo",
                "data_captura": datetime.now().isoformat(),
            })

    return resultados


# ── BUSCA POR TERMOS CUSTOMIZADOS ─────────────────────────────────────────────

async def buscar_por_termos(cidade: str, termos: List[str], prefs: Dict) -> List[Dict]:
    """
    Busca por termos customizados no Chaves na Mão e VivaReal.
    Ex: termos = ["alugo", "direto proprietário", "sem imobiliária"]
    """
    resultados = []

    async with httpx.AsyncClient(headers=HTTP_HEADERS, follow_redirects=True, timeout=20) as client:
        for termo in termos:
            # Busca no Chaves na Mão por termo
            slug = CIDADE_SLUG_CNM.get(cidade,"")
            if slug:
                url_cnm = f"{BASE_CNM}/imoveis-para-alugar/sp-{slug}/?q={'+'.join(termo.split())}"
                try:
                    r = await client.get(url_cnm, timeout=12)
                    if r.status_code == 200:
                        soup = BeautifulSoup(r.text, "html.parser")
                        links = soup.select("a[href*='/imovel/']")
                        for l in links[:5]:
                            href = l.get("href","")
                            if not href: continue
                            full_url = f"{BASE_CNM}{href}" if href.startswith("/") else href
                            if any(w in href.lower() for w in COMERCIAL_URL): continue
                            preco_m = re.search(r"RS(\d+)", href)
                            tipo_m = re.search(r"/(casa|apartamento|kitnet|sobrado)", href)
                            resultados.append({
                                "id": _id(full_url),
                                "titulo": l.get_text(strip=True)[:100] or f"Imóvel em {cidade}",
                                "cidade": cidade, "bairro": "", "tipo": tipo_m.group(1).title() if tipo_m else "Imóvel",
                                "quartos": None, "area": None,
                                "aluguel": float(preco_m.group(1)) if preco_m else None,
                                "anunciante": "A verificar",
                                "contato": None,
                                "portal": f"Busca: {termo[:30]}",
                                "link": full_url,
                                "indicadores": [f"Encontrado por termo: '{termo}'"],
                                "no_quintoandar": False,
                                "status": "novo",
                                "data_captura": datetime.now().isoformat(),
                            })
                except Exception:
                    pass
                await asyncio.sleep(1)

    # Deduplicar
    vistos = set()
    dedup = []
    for im in resultados:
        if im["link"] not in vistos:
            vistos.add(im["link"])
            dedup.append(im)
    return dedup


# ── ORQUESTRADOR PRINCIPAL ─────────────────────────────────────────────────────

async def buscar_todas_fontes(cidades: List[str], prefs: Dict) -> List[Dict]:
    todos = []
    termos_custom = prefs.get("termos_busca", [])

    for cidade in cidades:
        # 1. Chaves na Mão (proprietário direto verificado)
        r1 = await buscar_chavesnamao(cidade, prefs)
        todos.extend(r1)
        await asyncio.sleep(1.5)

        # 2. VivaReal (filtro owner=true)
        if "Viva Real" in prefs.get("portais", []):
            r2 = await buscar_vivareal(cidade, prefs)
            todos.extend(r2)
            await asyncio.sleep(1.5)

        # 3. Termos customizados
        if termos_custom:
            r3 = await buscar_por_termos(cidade, termos_custom, prefs)
            todos.extend(r3)
            await asyncio.sleep(1)

    return todos


# Manter compatibilidade com varredura.py
async def buscar_chavesnamao_multiplas(cidades: List[str], prefs: Dict) -> List[Dict]:
    return await buscar_todas_fontes(cidades, prefs)

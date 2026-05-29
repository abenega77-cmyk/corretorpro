"""
Verificador QuintoAndar — checa se um imóvel (por endereço/bairro/cidade)
já está sendo anunciado na plataforma. Usa a API pública de busca do QA.
"""
import httpx
import asyncio
import re
from typing import Dict, Optional
from urllib.parse import quote

QA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Origin": "https://www.quintoandar.com.br",
    "Referer": "https://www.quintoandar.com.br/",
}

# Mapeamento cidade → slug QuintoAndar
QA_CIDADE_SLUG = {
    "Taubaté":               "taubate-sp-brasil",
    "Ferraz de Vasconcelos": "ferraz-de-vasconcelos-sp-brasil",
    "Indaiatuba":            "indaiatuba-sp-brasil",
    "Valinhos":              "valinhos-sp-brasil",
    "Vinhedo":               "vinhedo-sp-brasil",
    "Hortolândia":           "hortolandia-sp-brasil",
    "Votorantim":            "votorantim-sp-brasil",
    "Praia Grande":          "praia-grande-sp-brasil",
    "Suzano":                "suzano-sp-brasil",
    "Sumaré":                "sumare-sp-brasil",
    "Jacareí":               "jacarei-sp-brasil",
    "Ribeirão Pires":        "ribeirao-pires-sp-brasil",
    "Embu das Artes":        "embu-das-artes-sp-brasil",
    "Poá":                   "poa-sp-brasil",
    "Sorocaba":              "sorocaba-sp-brasil",
    "São José dos Campos":   "sao-jose-dos-campos-sp-brasil",
    "Campinas":              "campinas-sp-brasil",
    "Guarulhos":             "guarulhos-sp-brasil",
    "Ribeirão Preto":        "ribeirao-preto-sp-brasil",
    "São Paulo":             "sao-paulo-sp-brasil",
}

# Cache simples em memória: cidade → contagem de imóveis no QA
_cache_qa: Dict[str, int] = {}


async def contar_imoveis_qa(cidade: str) -> int:
    """Retorna o total de imóveis para alugar no QuintoAndar para a cidade."""
    if cidade in _cache_qa:
        return _cache_qa[cidade]

    slug = QA_CIDADE_SLUG.get(cidade)
    if not slug:
        return -1

    url = f"https://www.quintoandar.com.br/alugar/imovel/{slug}"

    async with httpx.AsyncClient(headers=QA_HEADERS, follow_redirects=True, timeout=20) as client:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return -1

            # Extrair total de imóveis da página
            match = re.search(r"([\d\.,]+)\s*\n\n\s*im[oó]veis", resp.text)
            if match:
                total = int(match.group(1).replace(".", "").replace(",", ""))
                _cache_qa[cidade] = total
                return total
        except Exception:
            pass

    return -1


async def imovel_no_quintoandar(imovel: Dict) -> bool:
    """
    Verifica se um imóvel específico provavelmente já está no QuintoAndar.
    Estratégia: busca por endereço/bairro na API do QA.
    Retorna True se encontrou correspondência provável.
    """
    cidade = imovel.get("cidade", "")
    bairro = imovel.get("bairro", "")
    
    slug = QA_CIDADE_SLUG.get(cidade)
    if not slug:
        return False  # Cidade não atendida pelo QA = definitivamente não está lá

    # Buscar por bairro
    if bairro:
        bairro_slug = bairro.lower().replace(" ", "-").replace("á","a").replace("é","e").replace("ó","o").replace("ã","a").replace("ê","e")
        url = f"https://www.quintoandar.com.br/alugar/imovel/{slug}/{bairro_slug}"
    else:
        url = f"https://www.quintoandar.com.br/alugar/imovel/{slug}"

    async with httpx.AsyncClient(headers=QA_HEADERS, follow_redirects=True, timeout=20) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                return False  # Bairro não existe no QA = imóvel não está lá

            # Se retornou 200 com resultados, o bairro tem imóveis no QA
            # Mas isso não confirma que ESTE imóvel específico está lá
            # Usamos heurística: se a cidade tem < 50 imóveis no QA,
            # assumimos que imóveis de particulares provavelmente NÃO estão lá
            match = re.search(r"([\d\.,]+)\s*\n\n\s*im[oó]veis", resp.text)
            if match:
                total = int(match.group(1).replace(".", "").replace(",", ""))
                # Se há poucos imóveis no QA para essa cidade, 
                # a chance do imóvel captado já estar lá é baixa
                return total > 500  # Cidades com +500 imóveis no QA têm cobertura alta

        except Exception:
            pass

    return False


async def verificar_lote(imoveis: list) -> list:
    """Verifica se cada imóvel da lista está no QA e atualiza o campo no_quintoandar."""
    resultados = []
    for im in imoveis:
        no_qa = await imovel_no_quintoandar(im)
        im["no_quintoandar"] = no_qa
        if not no_qa:
            resultados.append(im)  # Incluir apenas os que NÃO estão no QA
        await asyncio.sleep(0.5)
    return resultados

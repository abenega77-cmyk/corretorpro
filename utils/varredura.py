"""
Motor principal de varredura — orquestra todos os scrapers,
aplica filtros, cruza com QuintoAndar e salva resultados.
"""
import asyncio
import uuid
from datetime import datetime
from typing import Dict, List

from scrapers.olx import buscar_olx
from scrapers.quintoandar import verificar_lote, contar_imoveis_qa
from utils.database import (
    salvar_imovel, imovel_existe, carregar_prefs,
    listar_imoveis, salvar_log, estatisticas
)
from utils.whatsapp import whatsapp

# Estado da varredura em andamento (para polling do frontend)
_varredura_atual: Dict = {}


def get_status_varredura() -> Dict:
    return _varredura_atual.copy()


async def executar_varredura(prefs: Dict = None) -> Dict:
    """Executa ciclo completo de varredura e retorna o relatório."""
    global _varredura_atual

    if prefs is None:
        prefs = carregar_prefs()

    inicio = datetime.now()
    _varredura_atual = {
        "id": str(uuid.uuid4())[:8],
        "inicio": inicio.isoformat(),
        "status": "em_andamento",
        "etapa": "Iniciando varredura...",
        "progresso": 0,
        "novos": 0,
        "total_encontrados": 0,
        "erros": [],
    }

    todos_imoveis = []
    cidades = prefs.get("cidades", [])
    portais = prefs.get("portais", [])
    erros = []

    try:
        # ── ETAPA 1: OLX ──────────────────────────────────────────────────
        if "OLX" in portais:
            _atualizar_status("🔍 Varrendo OLX...", 10)
            for i, cidade in enumerate(cidades):
                _atualizar_status(f"🔍 OLX — {cidade} ({i+1}/{len(cidades)})", 10 + (i * 20 // len(cidades)))
                try:
                    resultado = await buscar_olx(cidade, prefs)
                    todos_imoveis.extend(resultado)
                    await asyncio.sleep(1.5)
                except Exception as e:
                    erros.append(f"OLX/{cidade}: {str(e)[:80]}")

        # ── ETAPA 2: Viva Real / ZAP ──────────────────────────────────────
        if "Viva Real" in portais or "ZAP Imóveis" in portais:
            _atualizar_status("🔍 Varrendo Viva Real + ZAP Imóveis...", 35)
            # Viva Real e ZAP usam a mesma infraestrutura (Grupo OLX)
            # Adicionar resultados via busca web para complementar
            await asyncio.sleep(1)

        # ── ETAPA 3: Facebook Marketplace ─────────────────────────────────
        if "Facebook Marketplace" in portais:
            _atualizar_status("🔍 Varrendo Facebook Marketplace...", 50)
            # Facebook exige sessão autenticada — placeholder para integração
            await asyncio.sleep(1)

        # ── ETAPA 4: Deduplicar ───────────────────────────────────────────
        _atualizar_status("🔄 Removendo duplicatas...", 60)
        vistos = set()
        unicos = []
        for im in todos_imoveis:
            chave = im.get("link", im.get("id", ""))
            if chave not in vistos:
                vistos.add(chave)
                unicos.append(im)

        _varredura_atual["total_encontrados"] = len(unicos)

        # ── ETAPA 5: Cruzar com QuintoAndar ───────────────────────────────
        if prefs.get("cruzar_qa", True):
            _atualizar_status(f"🔄 Cruzando {len(unicos)} imóveis com QuintoAndar...", 70)
            sem_qa = await verificar_lote(unicos)
        else:
            sem_qa = unicos

        # ── ETAPA 6: Salvar novos ─────────────────────────────────────────
        _atualizar_status("💾 Salvando novos imóveis...", 85)
        novos = 0
        for im in sem_qa:
            link = im.get("link", "")
            if link and not imovel_existe(link):
                im["id"] = im.get("id") or str(uuid.uuid4())[:12]
                salvar_imovel(im)
                novos += 1

        _varredura_atual["novos"] = novos

        # ── ETAPA 7: Alerta WhatsApp ──────────────────────────────────────
        if prefs.get("alerta_whatsapp") and novos > 0:
            _atualizar_status("📲 Enviando alerta WhatsApp...", 93)
            numero = prefs.get("whatsapp_numero", "")
            if numero:
                imoveis_novos = listar_imoveis(status="novo")[:novos]
                stats = estatisticas()
                await whatsapp.enviar_resumo_diario(numero, imoveis_novos, stats)

        # ── CONCLUÍDO ─────────────────────────────────────────────────────
        fim = datetime.now()
        duracao = (fim - inicio).seconds

        log = {
            "id": _varredura_atual["id"],
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
            "duracao_seg": duracao,
            "cidades": cidades,
            "total_encontrados": len(unicos),
            "novos": novos,
            "ja_existentes": len(unicos) - novos,
            "erros": erros,
            "status": "concluido",
        }
        salvar_log(log)

        _atualizar_status(
            f"✅ Concluído! {novos} novos imóveis captados em {duracao}s",
            100,
            status="concluido"
        )
        return log

    except Exception as e:
        erro_msg = str(e)
        erros.append(f"Erro geral: {erro_msg[:120]}")
        _atualizar_status(f"❌ Erro: {erro_msg[:80]}", _varredura_atual.get("progresso", 0), status="erro")
        return {
            "status": "erro",
            "erro": erro_msg,
            "erros": erros,
            "novos": _varredura_atual.get("novos", 0),
        }


def _atualizar_status(etapa: str, progresso: int, status: str = "em_andamento"):
    global _varredura_atual
    _varredura_atual.update({
        "etapa": etapa,
        "progresso": min(progresso, 100),
        "status": status,
    })

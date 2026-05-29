"""
Motor principal de varredura — usa Chaves na Mão como fonte principal
(OLX bloqueia servidores em nuvem com 403)
"""
import asyncio
import uuid
from datetime import datetime
from typing import Dict, List

from scrapers.chavesnamao import buscar_chavesnamao_multiplas
from scrapers.quintoandar import verificar_lote
from utils.database import (
    salvar_imovel, imovel_existe, carregar_prefs,
    listar_imoveis, salvar_log, estatisticas
)
from utils.whatsapp import whatsapp

_varredura_atual: Dict = {}

def get_status_varredura() -> Dict:
    return _varredura_atual.copy()

async def executar_varredura(prefs: Dict = None) -> Dict:
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
    erros = []

    try:
        # ── Chaves na Mão (proprietário direto, funciona em cloud) ────────────
        _atualizar_status(f"🔍 Varrendo Chaves na Mão — {len(cidades)} cidades...", 15)
        try:
            resultado = await asyncio.wait_for(
                buscar_chavesnamao_multiplas(cidades, prefs),
                timeout=60
            )
            todos_imoveis.extend(resultado)
            _atualizar_status(f"✅ Chaves na Mão: {len(resultado)} imóveis encontrados", 40)
        except asyncio.TimeoutError:
            erros.append("Chaves na Mão: timeout")
        except Exception as e:
            erros.append(f"Chaves na Mão: {str(e)[:80]}")

        # ── Facebook Marketplace (requer acesso manual) ────────────────────────
        _atualizar_status("⚠️ Facebook Marketplace: acesso manual necessário — pulando...", 50)
        await asyncio.sleep(0.3)

        # ── Deduplicar ─────────────────────────────────────────────────────────
        _atualizar_status("🔄 Removendo duplicatas...", 60)
        vistos = set()
        unicos = []
        for im in todos_imoveis:
            chave = im.get("link", im.get("id", ""))
            if chave and chave not in vistos:
                vistos.add(chave)
                unicos.append(im)

        _varredura_atual["total_encontrados"] = len(unicos)

        # ── Cruzar com QuintoAndar ─────────────────────────────────────────────
        if prefs.get("cruzar_qa", True) and unicos:
            _atualizar_status(f"🔄 Cruzando {len(unicos)} imóveis com QuintoAndar...", 70)
            try:
                sem_qa = await asyncio.wait_for(verificar_lote(unicos), timeout=30)
            except Exception:
                sem_qa = unicos
        else:
            sem_qa = unicos

        # ── Salvar novos ───────────────────────────────────────────────────────
        _atualizar_status("💾 Salvando novos imóveis...", 85)
        novos = 0
        for im in sem_qa:
            link = im.get("link", "")
            if link and not imovel_existe(link):
                im["id"] = im.get("id") or str(uuid.uuid4())[:12]
                salvar_imovel(im)
                novos += 1

        _varredura_atual["novos"] = novos

        # ── Alerta WhatsApp ────────────────────────────────────────────────────
        if prefs.get("alerta_whatsapp") and novos > 0:
            _atualizar_status("📲 Enviando alerta WhatsApp...", 93)
            numero = prefs.get("whatsapp_numero", "")
            if numero:
                try:
                    imoveis_novos = listar_imoveis(status="novo")[:novos]
                    stats = estatisticas()
                    await asyncio.wait_for(
                        whatsapp.enviar_resumo_diario(numero, imoveis_novos, stats),
                        timeout=10
                    )
                except Exception:
                    pass

        # ── Concluído ──────────────────────────────────────────────────────────
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
            "erros": erros,
            "status": "concluido",
        }
        salvar_log(log)
        _atualizar_status(f"✅ Concluído! {novos} novos em {duracao}s", 100, status="concluido")
        return log

    except Exception as e:
        erros.append(f"Erro geral: {str(e)[:120]}")
        _atualizar_status(f"❌ Erro: {str(e)[:80]}", _varredura_atual.get("progresso", 0), status="erro")
        return {"status": "erro", "erro": str(e), "erros": erros}


def _atualizar_status(etapa: str, progresso: int, status: str = "em_andamento"):
    global _varredura_atual
    _varredura_atual.update({"etapa": etapa, "progresso": min(progresso, 100), "status": status})

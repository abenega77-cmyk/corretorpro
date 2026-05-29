from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional, List
from utils.database import (
    listar_imoveis, buscar_imovel, salvar_imovel,
    atualizar_imovel, deletar_imovel, carregar_prefs,
    salvar_prefs, listar_logs, estatisticas
)
from utils.varredura import executar_varredura, get_status_varredura
from utils.whatsapp import whatsapp
from models.imovel import ImovelUpdate, Preferencias

router = APIRouter()


# ── IMÓVEIS ──────────────────────────────────────────────────────────────────

@router.get("/imoveis")
async def get_imoveis(
    status: Optional[str] = None,
    cidade: Optional[str] = None,
    limit: int = 100,
):
    imoveis = listar_imoveis(status=status, cidade=cidade)
    return {"total": len(imoveis), "imoveis": imoveis[:limit]}


@router.get("/imoveis/{id}")
async def get_imovel(id: str):
    im = buscar_imovel(id)
    if not im:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    return im


@router.patch("/imoveis/{id}")
async def update_imovel(id: str, body: ImovelUpdate):
    updates = body.model_dump(exclude_none=True)
    im = atualizar_imovel(id, updates)
    if not im:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    return im


@router.delete("/imoveis/{id}")
async def delete_imovel(id: str):
    ok = deletar_imovel(id)
    if not ok:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    return {"ok": True}


# ── VARREDURA ─────────────────────────────────────────────────────────────────

@router.post("/varredura/iniciar")
async def iniciar_varredura(background_tasks: BackgroundTasks):
    """Inicia varredura em background e retorna imediatamente."""
    status = get_status_varredura()
    if status.get("status") == "em_andamento":
        return {"ok": False, "msg": "Varredura já em andamento", "status": status}

    prefs = carregar_prefs()
    background_tasks.add_task(executar_varredura, prefs)
    return {"ok": True, "msg": "Varredura iniciada em background"}


@router.get("/varredura/status")
async def status_varredura():
    """Polling do status da varredura em andamento."""
    return get_status_varredura()


@router.get("/varredura/historico")
async def historico_varreduras():
    return {"logs": listar_logs()}


# ── PREFERÊNCIAS ──────────────────────────────────────────────────────────────

@router.get("/preferencias")
async def get_preferencias():
    return carregar_prefs()


@router.put("/preferencias")
async def put_preferencias(body: Preferencias):
    prefs = salvar_prefs(body.model_dump())
    return {"ok": True, "preferencias": prefs}


# ── WHATSAPP ──────────────────────────────────────────────────────────────────

@router.post("/whatsapp/enviar/{imovel_id}")
async def enviar_whatsapp(imovel_id: str, numero: Optional[str] = None):
    """Envia mensagem de abordagem para o proprietário de um imóvel."""
    im = buscar_imovel(imovel_id)
    if not im:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")

    prefs = carregar_prefs()
    template = prefs.get("modelo_mensagem", "")
    resultado = await whatsapp.enviar_para_proprietario(im, template, numero)

    if resultado.get("sucesso"):
        atualizar_imovel(imovel_id, {"status": "contatado"})

    return resultado


@router.post("/whatsapp/teste")
async def testar_whatsapp(numero: str, mensagem: str = "✅ CorretorPro conectado com sucesso!"):
    """Envia mensagem de teste para confirmar configuração do WhatsApp."""
    from utils.whatsapp import whatsapp as wa
    numero_fmt = wa._formatar_numero(numero)
    resultado = await wa._enviar_evolution(numero_fmt, mensagem) if wa.modo == "evolution" else await wa._enviar_meta(numero_fmt, mensagem)
    return resultado


# ── ESTATÍSTICAS ──────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats():
    return estatisticas()


# ── HEALTHCHECK ──────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok", "service": "CorretorPro API", "version": "1.0.0"}

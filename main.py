"""CorretorPro — API Backend"""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from routes.api import router
from utils.database import carregar_prefs, salvar_prefs, PREFS_DEFAULT
from utils.varredura import executar_varredura

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

def _agendar(prefs):
    for job in scheduler.get_jobs():
        scheduler.remove_job(job.id)
    freq = prefs.get("frequencia","diaria")
    hor  = prefs.get("horario","07:00")
    h, m = hor.split(":") if ":" in hor else ("7","0")
    if freq == "diaria":
        scheduler.add_job(executar_varredura, CronTrigger(hour=h, minute=m),
                          id="varredura", replace_existing=True)
    elif freq == "12h":
        scheduler.add_job(executar_varredura, "interval", hours=12,
                          id="varredura", replace_existing=True)
    elif freq == "6h":
        scheduler.add_job(executar_varredura, "interval", hours=6,
                          id="varredura", replace_existing=True)
    print(f"✅ Agendamento: {freq} às {hor}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 CorretorPro iniciando...")
    # Garantir preferências padrão sempre disponíveis
    prefs = carregar_prefs()
    if not prefs.get("cidades"):
        prefs = PREFS_DEFAULT.copy()
        salvar_prefs(prefs)
        print(f"✅ Preferências padrão carregadas: {prefs['cidades']}")
    else:
        print(f"✅ Preferências carregadas: {prefs['cidades']}")
    _agendar(prefs)
    scheduler.start()
    print(f"⏰ Scheduler ativo | Jobs: {len(scheduler.get_jobs())}")
    yield
    scheduler.shutdown()

app = FastAPI(title="CorretorPro API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {"service":"CorretorPro API","version":"1.0.0",
            "status":"online","timestamp":datetime.now().isoformat()}

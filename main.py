"""
CorretorPro — API Backend
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from routes.api import router
from utils.database import carregar_prefs
from utils.varredura import executar_varredura

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

def _agendar_varredura():
    prefs = carregar_prefs()
    frequencia = prefs.get("frequencia", "diaria")
    horario = prefs.get("horario", "07:00")
    for job in scheduler.get_jobs():
        scheduler.remove_job(job.id)
    hora, minuto = horario.split(":") if ":" in horario else ("7", "0")
    if frequencia == "diaria":
        scheduler.add_job(executar_varredura, CronTrigger(hour=hora, minute=minuto), id="varredura_diaria", replace_existing=True)
    elif frequencia == "12h":
        scheduler.add_job(executar_varredura, "interval", hours=12, id="varredura_12h", replace_existing=True)
    elif frequencia == "6h":
        scheduler.add_job(executar_varredura, "interval", hours=6, id="varredura_6h", replace_existing=True)
    print(f"✅ Agendamento configurado: {frequencia} às {horario}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 CorretorPro iniciando...")
    _agendar_varredura()
    scheduler.start()
    print(f"⏰ Scheduler ativo | Jobs: {len(scheduler.get_jobs())}")
    yield
    scheduler.shutdown()

app = FastAPI(title="CorretorPro API", version="1.0.0", lifespan=lifespan)

# CORS — liberar qualquer origem (necessário para Claude Artifacts e apps externos)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {"service": "CorretorPro API", "version": "1.0.0", "status": "online", "timestamp": datetime.now().isoformat()}

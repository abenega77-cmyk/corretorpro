"""
CorretorPro — API Backend
Executa com: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import os
import asyncio
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
    """Configura o agendamento baseado nas preferências salvas."""
    prefs = carregar_prefs()
    frequencia = prefs.get("frequencia", "diaria")
    horario = prefs.get("horario", "07:00")

    # Remover jobs existentes
    for job in scheduler.get_jobs():
        scheduler.remove_job(job.id)

    hora, minuto = horario.split(":") if ":" in horario else ("7", "0")

    if frequencia == "diaria":
        scheduler.add_job(
            executar_varredura, CronTrigger(hour=hora, minute=minuto),
            id="varredura_diaria", name="Varredura Diária CorretorPro",
            replace_existing=True,
        )
    elif frequencia == "12h":
        scheduler.add_job(
            executar_varredura, "interval", hours=12,
            id="varredura_12h", name="Varredura 12h",
            replace_existing=True,
        )
    elif frequencia == "6h":
        scheduler.add_job(
            executar_varredura, "interval", hours=6,
            id="varredura_6h", name="Varredura 6h",
            replace_existing=True,
        )

    print(f"✅ Agendamento configurado: {frequencia} às {horario}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown da aplicação."""
    print("🚀 CorretorPro iniciando...")
    _agendar_varredura()
    scheduler.start()
    print(f"⏰ Scheduler ativo | Jobs: {len(scheduler.get_jobs())}")
    yield
    scheduler.shutdown()
    print("👋 CorretorPro encerrado")


app = FastAPI(
    title="CorretorPro API",
    description="Prospecção automatizada de imóveis para corretores QuintoAndar",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — permitir frontend local e produção
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://*.railway.app",
        "https://*.render.com",
        os.getenv("FRONTEND_URL", "*"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    return {
        "service": "CorretorPro API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "online",
        "timestamp": datetime.now().isoformat(),
    }

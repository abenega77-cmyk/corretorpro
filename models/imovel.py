from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


class StatusImovel(str, Enum):
    novo = "novo"
    contatado = "contatado"
    convertido = "convertido"
    descartado = "descartado"


class TipoImovel(str, Enum):
    todos = "todos"
    casa = "Casa"
    apartamento = "Apartamento"
    sobrado = "Sobrado"
    kitnet = "Kitnet"


class Imovel(BaseModel):
    id: str
    titulo: str
    cidade: str
    bairro: Optional[str] = None
    cep: Optional[str] = None
    tipo: str
    quartos: Optional[int] = None
    area: Optional[str] = None
    aluguel: Optional[float] = None
    condominio: Optional[float] = None
    iptu: Optional[float] = None
    anunciante: str
    contato: Optional[str] = None
    portal: str
    no_quintoandar: bool = False
    link: str
    descricao: Optional[str] = None
    indicadores: List[str] = []
    status: StatusImovel = StatusImovel.novo
    data_captura: datetime = datetime.now()
    data_atualizacao: Optional[datetime] = None


class ImovelUpdate(BaseModel):
    status: Optional[StatusImovel] = None
    contato: Optional[str] = None
    descricao: Optional[str] = None


class Preferencias(BaseModel):
    cidades: List[str] = []
    bairros: List[str] = []
    ceps: List[str] = []
    tipo_imovel: TipoImovel = TipoImovel.todos
    min_quartos: int = 1
    aluguel_min: float = 500
    aluguel_max: float = 10000
    apenas_particulares: bool = True
    filtrar_republica: bool = True
    filtrar_comercial: bool = True
    cruzar_qa: bool = True
    portais: List[str] = ["OLX", "Viva Real", "ZAP Imóveis"]
    frequencia: str = "diaria"
    horario: str = "07:00"
    alerta_whatsapp: bool = True
    whatsapp_numero: Optional[str] = None
    whatsapp_token: Optional[str] = None
    termos_busca: List[str] = []
    modelo_mensagem: str = (
        "Olá, {anunciante}! 👋\n\nVi seu anúncio do imóvel em *{bairro}, {cidade}* e fiquei muito interessado.\n\n"
        "Sou corretor parceiro do QuintoAndar e acredito que seu imóvel tem ótimo perfil para a plataforma.\n\n"
        "Posso explicar melhor? Não há custo para o proprietário. 🏠✨\n\nAguardo seu retorno!"
    )


class ResultadoVarredura(BaseModel):
    inicio: datetime
    fim: Optional[datetime] = None
    total_encontrados: int = 0
    novos: int = 0
    ja_existentes: int = 0
    descartados: int = 0
    erros: List[str] = []
    status: str = "em_andamento"

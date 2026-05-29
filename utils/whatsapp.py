"""
WhatsApp Business API — disparos automáticos para proprietários.

Suporta dois modos:
  1. WhatsApp Business API oficial (Meta) — para produção
  2. Evolution API / WPPConnect (open source) — para testes sem custo
"""
import httpx
import os
from typing import Dict, Optional
from datetime import datetime


class WhatsAppService:
    def __init__(self):
        # Configuração via variáveis de ambiente
        self.modo = os.getenv("WHATSAPP_MODO", "evolution")  # "meta" ou "evolution"

        # Meta Business API
        self.meta_token = os.getenv("WHATSAPP_META_TOKEN", "")
        self.meta_phone_id = os.getenv("WHATSAPP_META_PHONE_ID", "")

        # Evolution API (self-hosted)
        self.evo_url = os.getenv("WHATSAPP_EVO_URL", "http://localhost:8080")
        self.evo_key = os.getenv("WHATSAPP_EVO_KEY", "")
        self.evo_instance = os.getenv("WHATSAPP_EVO_INSTANCE", "corretorpro")

    def _formatar_numero(self, numero: str) -> str:
        """Normaliza número para formato internacional."""
        limpo = "".join(c for c in numero if c.isdigit())
        if limpo.startswith("0"):
            limpo = limpo[1:]
        if not limpo.startswith("55"):
            limpo = "55" + limpo
        return limpo

    def _montar_mensagem(self, template: str, imovel: Dict) -> str:
        """Substitui variáveis no template da mensagem."""
        return (
            template
            .replace("{anunciante}", imovel.get("anunciante", "Proprietário"))
            .replace("{bairro}", imovel.get("bairro", imovel.get("cidade", "")))
            .replace("{cidade}", imovel.get("cidade", ""))
            .replace("{tipo}", imovel.get("tipo", "imóvel"))
            .replace("{aluguel}", f"R$ {imovel.get('aluguel', 0):,.0f}".replace(",", "."))
            .replace("{quartos}", str(imovel.get("quartos", "")))
        )

    async def enviar_para_proprietario(
        self,
        imovel: Dict,
        template_mensagem: str,
        numero_destino: Optional[str] = None,
    ) -> Dict:
        """
        Envia mensagem de abordagem para o proprietário do imóvel.
        Retorna dict com status e detalhes.
        """
        numero = numero_destino or imovel.get("contato", "")
        if not numero or not any(c.isdigit() for c in numero):
            return {"sucesso": False, "erro": "Número de contato não disponível"}

        numero_fmt = self._formatar_numero(numero)
        mensagem = self._montar_mensagem(template_mensagem, imovel)

        if self.modo == "meta":
            return await self._enviar_meta(numero_fmt, mensagem)
        else:
            return await self._enviar_evolution(numero_fmt, mensagem)

    async def enviar_resumo_diario(
        self,
        numero_corretor: str,
        imoveis_novos: list,
        stats: Dict,
    ) -> Dict:
        """Envia resumo diário de novos imóveis para o corretor."""
        if not imoveis_novos:
            mensagem = (
                "📊 *CorretorPro — Resumo Diário*\n\n"
                f"🗓 {datetime.now().strftime('%d/%m/%Y às %H:%M')}\n\n"
                "Nenhum imóvel novo encontrado hoje.\n"
                f"Total captado: {stats.get('total', 0)} imóveis\n"
                f"Convertidos: {stats.get('convertidos', 0)}"
            )
        else:
            linhas = [
                "📊 *CorretorPro — Resumo Diário*\n",
                f"🗓 {datetime.now().strftime('%d/%m/%Y às %H:%M')}\n",
                f"🆕 *{len(imoveis_novos)} novos imóveis* sem anúncio no QuintoAndar!\n",
            ]
            for im in imoveis_novos[:5]:  # Máximo 5 no resumo
                linhas.append(
                    f"\n🏠 *{im.get('titulo', 'Imóvel')}*\n"
                    f"📍 {im.get('cidade')} — {im.get('bairro', '')}\n"
                    f"💰 R$ {im.get('aluguel', 0):,.0f}/mês\n"
                    f"👤 {im.get('anunciante', '')}\n"
                    f"🔗 {im.get('link', '')}\n"
                )
            if len(imoveis_novos) > 5:
                linhas.append(f"\n_... e mais {len(imoveis_novos) - 5} imóveis. Acesse o dashboard!_")

            linhas.append(f"\n📈 Total captado: {stats.get('total', 0)} | Convertidos: {stats.get('convertidos', 0)}")
            mensagem = "".join(linhas)

        numero_fmt = self._formatar_numero(numero_corretor)
        if self.modo == "meta":
            return await self._enviar_meta(numero_fmt, mensagem)
        else:
            return await self._enviar_evolution(numero_fmt, mensagem)

    async def _enviar_meta(self, numero: str, mensagem: str) -> Dict:
        """Envia via Meta Cloud API (oficial)."""
        if not self.meta_token or not self.meta_phone_id:
            return {"sucesso": False, "erro": "Credenciais Meta não configuradas"}

        url = f"https://graph.facebook.com/v18.0/{self.meta_phone_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": numero,
            "type": "text",
            "text": {"preview_url": False, "body": mensagem},
        }
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.meta_token}", "Content-Type": "application/json"},
                )
                data = resp.json()
                if resp.status_code == 200:
                    return {"sucesso": True, "message_id": data.get("messages", [{}])[0].get("id")}
                return {"sucesso": False, "erro": str(data)}
            except Exception as e:
                return {"sucesso": False, "erro": str(e)}

    async def _enviar_evolution(self, numero: str, mensagem: str) -> Dict:
        """Envia via Evolution API (open source, self-hosted)."""
        if not self.evo_url:
            return {"sucesso": False, "erro": "Evolution API não configurada"}

        url = f"{self.evo_url}/message/sendText/{self.evo_instance}"
        payload = {"number": numero, "text": mensagem, "delay": 1200}

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"apikey": self.evo_key, "Content-Type": "application/json"},
                )
                if resp.status_code in (200, 201):
                    return {"sucesso": True, "data": resp.json()}
                return {"sucesso": False, "erro": resp.text}
            except Exception as e:
                return {"sucesso": False, "erro": str(e)}


# Instância global
whatsapp = WhatsAppService()

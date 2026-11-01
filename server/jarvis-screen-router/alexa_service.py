import os
import json
import asyncio
import logging
from typing import Dict, Any, List, Optional
from alexapy import AlexaLogin, AlexaProxy, AlexaAPI

DATA_DIR = "/app/alexa_data"
OAUTH_FILE = os.path.join(DATA_DIR, "oauth_data.json")

class AlexaDeviceWrapper:
    """Wrapper para compatibilidade entre dict de dispositivo do alexapy e o construtor AlexaAPI."""
    def __init__(self, raw_device: dict):
        self.raw = raw_device
        self.device_serial_number = raw_device.get("serialNumber")
        self._device_type = raw_device.get("deviceType")
        self._device_family = raw_device.get("deviceFamily", "")
        self._cluster_members = raw_device.get("clusterMembers", [])
        self.account_name = raw_device.get("accountName", "")
        self._locale = raw_device.get("locale", "pt-BR")


class AlexaBridge:
    def __init__(self, domain: str = "amazon.com", base_proxy_url: str = "http://45.167.187.80:8092"):
        self.domain = domain
        self.base_proxy_url = base_proxy_url
        self.outputpath = lambda x: os.path.join(DATA_DIR, x)
        self.login: Optional[AlexaLogin] = None
        self.proxy: Optional[AlexaProxy] = None
        self.devices: List[Dict[str, Any]] = []
        self.is_authenticated = False
        self._init_lock = asyncio.Lock()
        self._flow_task: Optional[asyncio.Task] = None

    def _load_oauth_file(self) -> Optional[Dict[str, Any]]:
        try:
            if os.path.exists(OAUTH_FILE):
                with open(OAUTH_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("refresh_token"):
                        return data
        except Exception as e:
            logging.warning(f"[ALEXA-BRIDGE] Erro ao ler {OAUTH_FILE}: {e}")
        return None

    def _save_oauth_file(self):
        try:
            if self.login and getattr(self.login, "refresh_token", None):
                os.makedirs(DATA_DIR, exist_ok=True)
                data = {
                    "refresh_token": self.login.refresh_token,
                    "access_token": getattr(self.login, "access_token", None),
                    "deviceid": getattr(self.login, "deviceid", None),
                    "customer_id": getattr(self.login, "customer_id", None),
                }
                with open(OAUTH_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                logging.info(f"[ALEXA-BRIDGE] Sessão OAuth persistida permanentemente em {OAUTH_FILE}")
        except Exception as e:
            logging.error(f"[ALEXA-BRIDGE] Erro ao salvar {OAUTH_FILE}: {e}")

    async def initialize(self) -> bool:
        async with self._init_lock:
            try:
                os.makedirs(os.path.join(DATA_DIR, ".storage"), exist_ok=True)
                oauth_data = self._load_oauth_file()

                kwargs = {
                    "url": self.domain,
                    "email": "",
                    "password": "",
                    "outputpath": self.outputpath
                }
                if oauth_data:
                    logging.info("[ALEXA-BRIDGE] Carregando credenciais persistidas de oauth_data.json...")
                    kwargs["oauth"] = oauth_data

                self.login = AlexaLogin(**kwargs)
                await self.login.login()

                if getattr(self.login, "refresh_token", None) or getattr(self.login, "access_token", None):
                    self.is_authenticated = True
                    logging.info("[ALEXA-BRIDGE] ✅ Sessão persistida da Amazon carregada e validada com sucesso!")
                    self._save_oauth_file()
                    await self.refresh_devices()
                    return True
                else:
                    self.is_authenticated = False
                    logging.info("[ALEXA-BRIDGE] Nenhuma sessão ativa da Amazon encontrada. Pareamento necessário.")
                    return False
            except Exception as e:
                logging.warning(f"[ALEXA-BRIDGE] Erro ao inicializar sessão Alexa: {e}")
                self.is_authenticated = False
                return False

    async def refresh_devices(self) -> List[Dict[str, Any]]:
        if not self.login or not self.is_authenticated:
            return []
        try:
            # 1. Tenta via get_devices padrão
            devs = await AlexaAPI.get_devices(self.login)
            if not devs:
                # 2. Fallback via GraphQL nexus
                devs = await AlexaAPI.get_devices_gql(self.login)
            if devs:
                self.devices = devs
                AlexaAPI.devices[self.login.email] = devs
                names = [d.get("accountName", d.get("friendlyName", "Sem Nome")) for d in self.devices]
                logging.info(f"[ALEXA-BRIDGE] Dispositivos Alexa encontrados ({len(devs)}): {', '.join(names)}")
            return self.devices
        except Exception as e:
            logging.error(f"[ALEXA-BRIDGE] Erro ao buscar dispositivos: {e}")
            return []

    async def complete_login_flow(self) -> bool:
        """Executa a troca imediata do authorization_code por tokens OAuth permanentes e salva a sessão."""
        if not self.login:
            logging.error("[ALEXA-BRIDGE] complete_login_flow chamado sem login ativo.")
            return False

        has_auth_code = bool(getattr(self.login, "authorization_code", None))
        has_access_token = bool(getattr(self.login, "access_token", None))

        if not has_auth_code and not has_access_token:
            logging.warning("[ALEXA-BRIDGE] Nenhum authorization_code ou access_token disponível para troca.")
            return False

        logging.info("[ALEXA-BRIDGE] 🚀 Iniciando troca de tokens e registro com Amazon...")
        try:
            reg_ok = await self.login.get_tokens()
            logging.info(f"[ALEXA-BRIDGE] login.get_tokens() -> {reg_ok}")
            if reg_ok:
                try:
                    await self.login.register_capabilities()
                    logging.info("[ALEXA-BRIDGE] register_capabilities() -> OK")
                except Exception as e:
                    logging.debug(f"[ALEXA-BRIDGE] register_capabilities: {e}")
                try:
                    await self.login.exchange_token_for_cookies()
                    logging.info("[ALEXA-BRIDGE] exchange_token_for_cookies() -> OK")
                except Exception as e:
                    logging.debug(f"[ALEXA-BRIDGE] exchange_token_for_cookies: {e}")
                try:
                    await self.login.get_csrf()
                    logging.info("[ALEXA-BRIDGE] get_csrf() -> OK")
                except Exception as e:
                    logging.debug(f"[ALEXA-BRIDGE] get_csrf: {e}")

                await self.login.finalize_login()
                self.is_authenticated = True
                self._save_oauth_file()

                logging.info(f"[ALEXA-BRIDGE] ✅ PAREAMENTO CONCLUÍDO COM SUCESSO! Customer ID: {self.login.customer_id}")

                if self.proxy and self.proxy.active:
                    try:
                        await self.proxy.stop_proxy()
                        logging.info("[ALEXA-BRIDGE] Proxy de pareamento encerrado com sucesso.")
                    except Exception as e:
                        logging.debug(f"[ALEXA-BRIDGE] Erro ao fechar proxy: {e}")

                # Descobre os aparelhos Echo da conta
                await self.refresh_devices()

                # Dispara saudação de sucesso na Echo Dot
                if self.devices:
                    asyncio.create_task(self.speak("Sistema J.A.R.V.I.S. conectado à Echo Dot com sucesso, senhor Werik."))
                return True
            else:
                logging.error("[ALEXA-BRIDGE] get_tokens() retornou False ao registrar dispositivo.")
                return False
        except Exception as e:
            logging.error(f"[ALEXA-BRIDGE] Exceção em complete_login_flow: {e}", exc_info=True)
            return False

    async def start_pairing_proxy(self) -> str:
        """Inicia o proxy web para o usuário autenticar na Amazon via navegador."""
        os.makedirs(os.path.join(DATA_DIR, ".storage"), exist_ok=True)
        if not self.login:
            oauth_data = self._load_oauth_file()
            kwargs = {
                "url": self.domain,
                "email": "",
                "password": "",
                "outputpath": self.outputpath
            }
            if oauth_data:
                kwargs["oauth"] = oauth_data
            self.login = AlexaLogin(**kwargs)

        if self.proxy and self.proxy.active:
            return self.base_proxy_url

        self.proxy = AlexaProxy(self.login, base_url=self.base_proxy_url)
        self.proxy._port = 8092

        # Patch dinâmico em test_amazon_url para troca em tempo real de zero latência
        original_test = self.proxy.test_amazon_url

        async def _instant_test_amazon_url(resp, data, query):
            res = await original_test(resp, data, query)
            has_code = bool(getattr(self.login, "authorization_code", None))
            has_tok = bool(getattr(self.login, "access_token", None))
            if has_code or has_tok:
                logging.info("[ALEXA-BRIDGE] 🎯 Código de autorização recebido pelo Proxy! Disparando troca imediata...")
                asyncio.create_task(self.complete_login_flow())
            return res

        self.proxy.tests["test_amazon_url"] = _instant_test_amazon_url

        await self.proxy.start_proxy(host="0.0.0.0")
        logging.info(f"[ALEXA-BRIDGE] Proxy de autenticação iniciado em {self.base_proxy_url}")

        if self._flow_task and not self._flow_task.done():
            self._flow_task.cancel()
        self._flow_task = asyncio.create_task(self._monitor_pairing())
        return self.base_proxy_url

    async def _monitor_pairing(self):
        logging.info("[ALEXA-BRIDGE] Monitor de pareamento aguardando autenticação (tempo limite: 20 min)...")
        for _ in range(300):
            await asyncio.sleep(4)
            if not self.login:
                continue

            if self.is_authenticated:
                break

            has_auth_code = bool(getattr(self.login, "authorization_code", None))
            has_access_token = bool(getattr(self.login, "access_token", None))

            if has_auth_code or has_access_token:
                logging.info("[ALEXA-BRIDGE] Monitor detectou credenciais capturadas. Executando complete_login_flow...")
                success = await self.complete_login_flow()
                if success:
                    break

    async def speak(self, text: str, device_name_or_serial: str = None) -> Dict[str, Any]:
        """Faz a Echo Dot falar o texto informado via Amazon TTS."""
        if not self.is_authenticated:
            return {"status": "error", "message": "Alexa não pareada. Acesse a rota de pareamento primeiro."}

        target_device = None
        if device_name_or_serial:
            dev_low = device_name_or_serial.lower().strip()
            for d in self.devices:
                name = str(d.get("accountName", d.get("friendlyName", ""))).lower()
                serial = str(d.get("serialNumber", "")).lower()
                family = str(d.get("deviceFamily", "")).lower()
                if dev_low in name or dev_low == serial or dev_low in family:
                    target_device = d
                    break

        if not target_device:
            for d in self.devices:
                family = str(d.get("deviceFamily", "")).upper()
                if "ECHO" in family or "KNIGHT" in family or "ROOK" in family:
                    target_device = d
                    break

        if not target_device and self.devices:
            target_device = self.devices[0]

        if not target_device:
            return {"status": "error", "message": "Nenhum dispositivo Echo compatível encontrado."}

        target_name = target_device.get("accountName", target_device.get("friendlyName", "Echo"))
        logging.info(f"[ALEXA-SPEAK] Enviando fala para '{target_name}': '{text[:60]}'...")
        try:
            AlexaAPI.devices[self.login.email] = self.devices
            wrapper = AlexaDeviceWrapper(target_device)
            api = AlexaAPI(wrapper, self.login)

            # Tenta send_announcement (método moderno e compatível com Echo Dot)
            try:
                await api.send_announcement(text, method="speak")
            except Exception as e_ann:
                logging.warning(f"[ALEXA-SPEAK] Fallback para send_tts: {e_ann}")
                await api.send_tts(text)

            return {
                "status": "success",
                "device": target_name,
                "serial": target_device.get("serialNumber"),
                "text": text
            }
        except Exception as e:
            logging.error(f"[ALEXA-SPEAK] Erro ao disparar TTS: {e}")
            return {"status": "error", "message": str(e)}

alexa_bridge = AlexaBridge()

"""
J.A.R.V.I.S. Puppeteer / Playwright Web Automation Bridge
Permite ao JARVIS controlar um navegador Chromium headless ou visível nativamente no Windows:
- Navegar em sites com JS dinâmico e extrair texto / imagens
- Capturar screenshots de página inteira (Full Page Screenshot)
- Preencher formulários e clicar em elementos (click / type)
- Executar scripts JavaScript no contexto da página (evaluate)
"""

import os
import sys
import time
import json
import base64
import asyncio
import threading
from typing import Dict, Any, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENSHOT_DIR = os.path.join(ROOT_DIR, "logs", "puppeteer_shots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

class PuppeteerBridge:
    def __init__(self):
        self._loop = None
        self._thread = None
        self._ensure_loop()

    def _ensure_loop(self):
        if self._loop is None or not self._loop.is_running():
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="PuppeteerLoop")
            self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_async(self, coro, timeout=45):
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # =========================================================================
    # 1. NAVEGAR E EXTRAIR CONTEÚDO DISSOLVIDO
    # =========================================================================
    def navigate(self, url: str, headless: bool = True, wait_until: str = "domcontentloaded") -> Dict[str, Any]:
        """Navega para uma URL via Puppeteer/Playwright e extrai título, texto limpo e screenshot."""
        async def _async_nav():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless)
                context = await browser.new_context(viewport={"width": 1440, "height": 900})
                page = await context.new_page()
                
                target_url = url if url.startswith("http") else f"https://{url}"
                response = await page.goto(target_url, wait_until=wait_until, timeout=30000)
                
                title = await page.title()
                text_content = await page.evaluate("document.body.innerText")
                
                shot_filename = f"shot_{int(time.time())}.png"
                shot_path = os.path.join(SCREENSHOT_DIR, shot_filename)
                await page.screenshot(path=shot_path, full_page=False)
                
                with open(shot_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                
                await browser.close()
                return {
                    "status": "ok",
                    "action": "puppeteer_navigate",
                    "url": target_url,
                    "title": title,
                    "http_status": response.status if response else 200,
                    "text_snippet": (text_content or "").strip()[:1500],
                    "screenshot_path": shot_path,
                    "image_b64": "data:image/png;base64," + b64
                }

        try:
            return self._run_async(_async_nav())
        except Exception as e:
            return {"status": "error", "action": "puppeteer_navigate", "url": url, "message": str(e)}

    # =========================================================================
    # 2. CAPTURA DE TELA DE PÁGINA INTEIRA (FULL PAGE SCREENSHOT)
    # =========================================================================
    def full_page_screenshot(self, url: str) -> Dict[str, Any]:
        """Gera screenshot de página inteira (Full-Page) de qualquer site."""
        async def _async_shot():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                
                target_url = url if url.startswith("http") else f"https://{url}"
                await page.goto(target_url, wait_until="networkidle", timeout=35000)
                
                shot_filename = f"fullshot_{int(time.time())}.png"
                shot_path = os.path.join(SCREENSHOT_DIR, shot_filename)
                await page.screenshot(path=shot_path, full_page=True)
                
                with open(shot_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                
                title = await page.title()
                await browser.close()
                return {
                    "status": "ok",
                    "action": "puppeteer_full_screenshot",
                    "url": target_url,
                    "title": title,
                    "screenshot_path": shot_path,
                    "image_b64": "data:image/png;base64," + b64
                }

        try:
            return self._run_async(_async_shot())
        except Exception as e:
            return {"status": "error", "action": "puppeteer_full_screenshot", "url": url, "message": str(e)}

    # =========================================================================
    # 3. INTERAÇÃO (CLIQUE / PREENCHIMENTO DE FORMULÁRIO / JS)
    # =========================================================================
    def interact(self, url: str, actions: list, headless: bool = True) -> Dict[str, Any]:
        """
        Executa uma sequência de ações Puppeteer no site:
        actions = [
          {"type": "click", "selector": "#login-btn"},
          {"type": "fill", "selector": "#email-input", "value": "user@example.com"},
          {"type": "evaluate", "script": "return document.title"}
        ]
        """
        async def _async_interact():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless)
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                
                target_url = url if url.startswith("http") else f"https://{url}"
                await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                
                results = []
                for act in actions:
                    act_type = act.get("type", "").lower()
                    sel = act.get("selector")
                    val = act.get("value", "")
                    
                    if act_type == "click" and sel:
                        await page.click(sel, timeout=10000)
                        results.append({"action": "click", "selector": sel, "ok": True})
                    elif act_type in ("fill", "type") and sel:
                        await page.fill(sel, str(val), timeout=10000)
                        results.append({"action": "fill", "selector": sel, "ok": True})
                    elif act_type == "evaluate" and act.get("script"):
                        res = await page.evaluate(act.get("script"))
                        results.append({"action": "evaluate", "result": res, "ok": True})
                    elif act_type == "wait":
                        ms = int(act.get("ms", 1000))
                        await page.wait_for_timeout(ms)
                        results.append({"action": "wait", "ms": ms, "ok": True})

                shot_filename = f"interact_{int(time.time())}.png"
                shot_path = os.path.join(SCREENSHOT_DIR, shot_filename)
                await page.screenshot(path=shot_path)
                
                title = await page.title()
                await browser.close()
                return {
                    "status": "ok",
                    "action": "puppeteer_interact",
                    "url": target_url,
                    "title": title,
                    "action_results": results,
                    "final_screenshot": shot_path
                }

        try:
            return self._run_async(_async_interact())
        except Exception as e:
            return {"status": "error", "action": "puppeteer_interact", "url": url, "message": str(e)}


puppeteer_engine = PuppeteerBridge()

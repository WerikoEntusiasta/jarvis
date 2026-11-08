"""
J.A.R.V.I.S. — Módulo de Automação Web via Playwright
=============================================================================
Padrão Permanente de Engenharia de Software Sênior & Alta Confiabilidade.
Permite ao J.A.R.V.I.S. navegar, extrair dados, tirar screenshots e interagir
com sites e aplicações web modernas de forma assíncrona e headless.
"""

import os
import sys
import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("WebAutomationPlaywright")
logger.setLevel(logging.INFO)

def is_playwright_available() -> bool:
    try:
        import playwright
        return True
    except ImportError:
        return False

def browse_and_extract(url: str, selector: Optional[str] = None, wait_sec: float = 2.0) -> Dict[str, Any]:
    """
    Navega até uma URL usando Chromium headless e extrai título, texto do body ou seletor específico.
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 JARVIS-Agent/2.0"
            )
            page.goto(url, timeout=25000, wait_until="domcontentloaded")
            time.sleep(wait_sec)

            title = page.title()
            
            extracted_text = ""
            if selector:
                elements = page.query_selector_all(selector)
                extracted_text = "\n---\n".join([el.inner_text().strip() for el in elements if el.inner_text()])
            else:
                body = page.query_selector("body")
                extracted_text = body.inner_text()[:4000] if body else ""

            browser.close()

            return {
                "ok": True,
                "url": url,
                "title": title,
                "content_preview": extracted_text[:1500],
                "total_chars": len(extracted_text)
            }
    except Exception as e:
        logger.error(f"[Playwright] Erro ao navegar em {url}: {e}")
        return {"ok": False, "error": str(e), "url": url}

def capture_web_screenshot(url: str, output_path: str, full_page: bool = False) -> Dict[str, Any]:
    """
    Renderiza uma página web e salva screenshot no caminho especificado.
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(url, timeout=25000, wait_until="networkidle")
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            page.screenshot(path=output_path, full_page=full_page)
            browser.close()

            return {
                "ok": True,
                "url": url,
                "output_path": output_path,
                "file_size": os.path.getsize(output_path)
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def execute_web_actions(url: str, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Executa sequência de ações interativas em uma página:
    - click: {"action": "click", "selector": "#btn"}
    - fill: {"action": "fill", "selector": "input#search", "value": "termo"}
    - press: {"action": "press", "selector": "input#search", "key": "Enter"}
    - wait: {"action": "wait", "seconds": 2}
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(url, timeout=25000, wait_until="domcontentloaded")

            results = []
            for act in actions:
                a_type = act.get("action")
                sel = act.get("selector")
                if a_type == "click" and sel:
                    page.click(sel, timeout=5000)
                    results.append(f"Clicked {sel}")
                elif a_type == "fill" and sel:
                    page.fill(sel, act.get("value", ""))
                    results.append(f"Filled {sel}")
                elif a_type == "press" and sel:
                    page.press(sel, act.get("key", "Enter"))
                    results.append(f"Pressed key on {sel}")
                elif a_type == "wait":
                    time.sleep(float(act.get("seconds", 1.0)))
                    results.append(f"Waited {act.get('seconds')}s")

            title = page.title()
            final_url = page.url
            browser.close()

            return {
                "ok": True,
                "initial_url": url,
                "final_url": final_url,
                "page_title": title,
                "actions_executed": results
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}

"""Persistent Playwright browser controller operated by A.D.A's primary model."""
from __future__ import annotations

import base64
import re
from urllib.parse import urlparse

from playwright.async_api import async_playwright


class WebAgent:
    def __init__(self, on_update=None):
        self.on_update = on_update
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        if self.browser and self.browser.is_connected() and self.page:
            return
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
        )
        self.page = await self.context.new_page()
        await self._publish("Browser ready")

    async def _require_page(self):
        await self.start()
        if not self.page:
            raise RuntimeError("Browser page could not be initialized.")
        return self.page

    async def _publish(self, message: str):
        if not self.page or not self.on_update:
            return
        screenshot = await self.page.screenshot(type="jpeg", quality=82)
        payload = {
            "image": base64.b64encode(screenshot).decode("ascii"),
            "log": message,
        }
        result = self.on_update(payload)
        if hasattr(result, "__await__"):
            await result

    @staticmethod
    def normalize_url(url: str) -> str:
        candidate = url.strip()
        parsed_input = urlparse(candidate)
        host_with_port = re.match(r"^[A-Za-z0-9.-]+:\d+(?:/|$)", candidate)
        if parsed_input.scheme and parsed_input.scheme not in {"http", "https"}:
            if host_with_port:
                candidate = "http://" + candidate
            else:
                raise ValueError("Only valid HTTP and HTTPS web addresses are supported.")
        elif not parsed_input.scheme:
            candidate = ("http://" if host_with_port else "https://") + candidate
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Only valid HTTP and HTTPS web addresses are supported.")
        return candidate

    async def navigate(self, url: str):
        candidate = self.normalize_url(url)
        page = await self._require_page()
        response = await page.goto(candidate, wait_until="domcontentloaded", timeout=45000)
        await self._publish(f"Opened {page.url}")
        return f"Opened {page.url} (HTTP {response.status if response else 'unknown'})."

    async def click(self, selector: str):
        page = await self._require_page()
        await page.locator(selector).first.click(timeout=15000)
        await self._publish(f"Clicked: {selector}")
        return f"Clicked element: {selector}"

    async def type_text(self, selector: str, text: str):
        page = await self._require_page()
        await page.locator(selector).first.fill(text, timeout=15000)
        await self._publish(f"Entered text into: {selector}")
        return f"Entered text into {selector}."

    async def press(self, key: str, selector: str = ""):
        page = await self._require_page()
        if selector:
            await page.locator(selector).first.press(key, timeout=15000)
        else:
            await page.keyboard.press(key)
        await self._publish(f"Pressed {key}")
        return f"Pressed {key}."

    async def read_page(self):
        page = await self._require_page()
        title = await page.title()
        text = await page.locator("body").inner_text(timeout=10000)
        links = await page.locator("a").evaluate_all(
            "(nodes) => nodes.slice(0, 80).map(a => ({text: (a.innerText || a.getAttribute('aria-label') || '').trim(), href: a.href})).filter(a => a.text || a.href)"
        )
        return (
            f"URL: {page.url}\nTitle: {title}\n\nPAGE TEXT:\n{text[:24000]}\n\n"
            f"LINKS:\n" + "\n".join(f"- {item.get('text', '')}: {item.get('href', '')}" for item in links)
        )

    async def screenshot(self):
        page = await self._require_page()
        await self._publish(f"Screenshot: {page.url}")
        return f"Screenshot of {page.url} sent to the A.D.A browser panel."

    async def wait(self, seconds: int = 2):
        page = await self._require_page()
        seconds = max(1, min(int(seconds), 15))
        await page.wait_for_timeout(seconds * 1000)
        await self._publish(f"Waited {seconds} seconds")
        return f"Waited {seconds} seconds."

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.browser = self.context = self.page = self.playwright = None
        return "Browser closed."

    async def run_task(self, prompt: str):
        """Compatibility shim for the legacy audio tool; primary model owns browser planning."""
        return (
            "Browser tasks are now controlled by the primary A.D.A model through browser tools. "
            "Send this task in the main chat: " + prompt
        )

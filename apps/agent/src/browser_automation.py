from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


@dataclass
class AutomationResult:
    ok: bool
    message: str
    steps: list[dict[str, Any]]


class BrowserAutomationService:
    def __init__(self, cdp_url: str = "", headless: bool = True) -> None:
        self.cdp_url = cdp_url.strip()
        self.headless = headless

    async def execute(self, steps: list[dict[str, Any]], start_url: str | None = None) -> AutomationResult:
        if not steps:
            return AutomationResult(ok=False, message="No steps provided.", steps=[])

        playwright = await async_playwright().start()
        browser: Browser | None = None
        context: BrowserContext | None = None
        page: Page | None = None
        executed: list[dict[str, Any]] = []
        try:
            if self.cdp_url:
                browser = await playwright.chromium.connect_over_cdp(self.cdp_url)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
            else:
                browser = await playwright.chromium.launch(headless=self.headless)
                context = await browser.new_context()

            page = context.pages[0] if context.pages else await context.new_page()
            if start_url:
                await page.goto(start_url, wait_until="domcontentloaded")

            for idx, step in enumerate(steps):
                res = await self._run_step(page, step)
                res["index"] = idx
                executed.append(res)

            return AutomationResult(ok=True, message="Action plan executed.", steps=executed)
        except Exception as exc:
            return AutomationResult(ok=False, message=f"Execution failed: {exc}", steps=executed)
        finally:
            if context and not self.cdp_url:
                await context.close()
            if browser:
                if not self.cdp_url:
                    await browser.close()
            await playwright.stop()

    async def _run_step(self, page: Page, step: dict[str, Any]) -> dict[str, Any]:
        step_type = str(step.get("type", "")).lower().strip()
        target = str(step.get("target", "")).strip()
        text = str(step.get("text", "")).strip()

        if step_type == "navigate":
            if not target:
                raise ValueError("navigate step requires target URL.")
            await page.goto(target, wait_until="domcontentloaded")
            return {"step_type": step_type, "status": "ok", "target": target}

        if step_type == "wait":
            wait_ms = int(step.get("delay_ms") or step.get("text") or 800)
            await page.wait_for_timeout(max(100, wait_ms))
            return {"step_type": step_type, "status": "ok", "wait_ms": wait_ms}

        if step_type == "scroll":
            amount = int(step.get("text") or 600)
            await page.evaluate("(y) => window.scrollBy({ top: y, behavior: 'smooth' })", amount)
            await page.wait_for_timeout(250)
            return {"step_type": step_type, "status": "ok", "amount": amount}

        if step_type == "click":
            if not target:
                raise ValueError("click step requires target.")
            if self._looks_like_selector(target):
                await page.locator(target).first.click(timeout=5000)
            else:
                await page.get_by_text(target, exact=False).first.click(timeout=5000)
            return {"step_type": step_type, "status": "ok", "target": target}

        if step_type == "type":
            if not target:
                raise ValueError("type step requires target.")
            if self._looks_like_selector(target):
                await page.locator(target).first.fill(text, timeout=5000)
            else:
                # Heuristic: try label first, then placeholder text.
                try:
                    await page.get_by_label(target, exact=False).first.fill(text, timeout=2500)
                except Exception:
                    await page.get_by_placeholder(target, exact=False).first.fill(text, timeout=2500)
            return {"step_type": step_type, "status": "ok", "target": target, "text_len": len(text)}

        return {"step_type": step_type or "unknown", "status": "skipped", "reason": "Unsupported step type"}

    def _looks_like_selector(self, target: str) -> bool:
        return target.startswith(("#", ".", "[", "input", "button", "textarea", "select", "a "))

#!/usr/bin/env python3
"""Single-iteration smoke runner for the Simplify apply-worker feedback loop.

Purpose:
    Drive one end-to-end (up to but NOT including submit) apply attempt against
    a real Greenhouse job URL using the user's cloned Chrome profile, so each
    iteration of the feedback loop has reproducible artifacts on disk.

Hard rule:
    This runner never produces a submit click. dry_run=True is hard-coded.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from playwright.async_api import Page, async_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOP_ROOT = REPO_ROOT / ".research" / "simplify-loop"
ITER_DIR = LOOP_ROOT / "iterations"
TARGETS_FILE = LOOP_ROOT / "targets.txt"
STATE_FILE = LOOP_ROOT / "state.json"
RUNLOG_FILE = LOOP_ROOT / "runlog.md"
PROFILE_DIR = REPO_ROOT / "data" / "chrome-profile-clone"
SIMPLIFY_EXT_DIR = REPO_ROOT / "data" / "simplify-unpacked"
RESUME_PDF = REPO_ROOT / "config" / "resume_base.pdf"
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Simplify's render is intermittent. ~33% of fresh page loads never render
# the side panel at all. We poll for up to 45s, and if missing, reload once.
SIMPLIFY_RENDER_WAIT_S = 45


def _read_targets() -> list[str]:
    """Read target URLs from disk, one per line, ignoring blanks/comments.

    Output:
        List of URLs in file order.
    """

    lines = TARGETS_FILE.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def _next_iter_num() -> int:
    """Return the next iteration directory number based on existing dirs.

    Output:
        Integer iteration index.
    """

    ITER_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(p.name for p in ITER_DIR.iterdir() if p.is_dir())
    if not existing:
        return 1
    last = max(int(name) for name in existing if name.isdigit())
    return last + 1


def _load_state() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return data


def _save_state(state: dict[str, Any]) -> None:
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_FILE)


def _append_runlog(entry: str) -> None:
    with RUNLOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write("\n---\n\n")
        fh.write(entry)
        if not entry.endswith("\n"):
            fh.write("\n")


def _ensure_simplify_dir_in_clone() -> None:
    """Restore the Simplify extension directory inside the clone if missing.

    Purpose:
        Empirically (2026-05-07 iteration 14+), Simplify's content script
        only renders the side panel reliably when the extension directory
        exists at clone's `Default/Extensions/<id>/`, regardless of whether
        we also pass `--load-extension`. Earlier rationale that we should
        DELETE this directory to avoid the `DidStartWorkerFail: 5` content
        verification failure was wrong — that error only occurs when the
        Secure Preferences file is inconsistent (which only happens if
        Chrome was running during the clone). With a clean clone (Chrome
        closed at copy time), keeping the cached extension AND also passing
        --load-extension works reliably.

        We re-copy the extension from the user's main profile if it's
        missing (Chrome can sometimes wipe it on launch when running with
        debug port). Safe to run every iteration.
    Output:
        None.
    """

    import shutil

    sim_id = "pbanhockgagggenencehbnadejlgchfc"
    target = PROFILE_DIR / "Default" / "Extensions" / sim_id
    if target.exists() and any(target.iterdir()):
        return
    source = (
        Path.home()
        / "Library"
        / "Application Support"
        / "Google"
        / "Chrome"
        / "Default"
        / "Extensions"
        / sim_id
    )
    if not source.exists():
        logger.warning(
            "Source Simplify dir not found at {}; cannot restore in clone",
            source,
        )
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    logger.info("Restored Simplify extension dir in clone from {}", source)


def _free_port() -> int:
    """Pick a free TCP port for Chrome's debugging server.

    Output:
        Available port number.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def _launch_chrome_with_profile(
    cdp_port: int, initial_url: str
) -> subprocess.Popen[bytes]:
    """Spawn real Chrome with the cloned profile + Simplify side-loaded.

    Verified launch strategy (see findings.md): Simplify must be loaded via
    --load-extension from a path OUTSIDE user-data-dir. The cloned profile's
    Default/Extensions/<id>/ entry plus Secure Preferences entry are stripped
    so Chrome doesn't try to load the cached/MAC-mismatched copy.

    The target URL is passed as Chrome's initial URL (rather than about:blank
    + later navigation) because Simplify's content script behaves differently
    on Playwright-driven tabs vs the natural initial tab — when Playwright
    attaches before navigation, Simplify often refuses to render the side
    panel. Loading the URL first lets Simplify activate before automation
    attaches.

    Args:
        cdp_port: TCP port to expose CDP on.
        initial_url: URL to open as Chrome's first tab.
    Output:
        Popen handle (caller is responsible for terminate).
    """

    if not SIMPLIFY_EXT_DIR.exists():
        raise RuntimeError(
            f"Simplify unpacked extension not found at {SIMPLIFY_EXT_DIR}. "
            "Run scripts/setup_simplify_loop.sh to stage it."
        )

    args = [
        CHROME_BIN,
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={PROFILE_DIR}",
        f"--load-extension={SIMPLIFY_EXT_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=ChromeWhatsNewUI,OptimizationHints",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-sync",
        initial_url,
    ]
    return subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ},
    )


async def _wait_for_cdp(cdp_port: int, timeout_s: float = 20.0) -> bool:
    """Poll Chrome's CDP /json/version endpoint until it responds.

    Args:
        cdp_port: TCP port Chrome was launched against.
        timeout_s: Max seconds to wait.
    Output:
        True if Chrome accepted CDP requests; False on timeout.
    """

    deadline = asyncio.get_event_loop().time() + timeout_s
    url = f"http://127.0.0.1:{cdp_port}/json/version"
    while asyncio.get_event_loop().time() < deadline:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, timeout=2.0)
                if r.status_code == 200:
                    return True
        except (httpx.HTTPError, OSError):
            pass
        await asyncio.sleep(0.3)
    return False


async def _bare_cdp_wait_for_simplify(
    cdp_port: int, timeout_s: float
) -> dict[str, Any]:
    """Poll Chrome's tab via raw CDP for the Simplify shadow roots.

    Purpose:
        Verify that Simplify has rendered its panel BEFORE Playwright
        attaches to the browser. Playwright's connect_over_cdp during
        Simplify's init phase appears to prevent the content script from
        completing render, so we use raw websocket CDP only.
    Args:
        cdp_port: TCP port Chrome was launched against.
        timeout_s: Max seconds to wait for the autofill button.
    Output:
        Dict describing the final state: {shadow_count, autofill_present, elapsed_s}.
    """

    import websockets

    js = """JSON.stringify({
        shadow_host_count: document.querySelectorAll('div.simplify-jobs-shadow-root').length,
        autofill_present: (() => {
            const hosts = document.querySelectorAll('div.simplify-jobs-shadow-root');
            for (const h of hosts) {
                if (!h.shadowRoot) continue;
                if (h.shadowRoot.querySelector('[aria-label="Autofill"]')) return true;
                if (h.shadowRoot.querySelector('[aria-label="Autofill all fields with AI"]')) return true;
            }
            return false;
        })(),
        ready_state: document.readyState,
        title: document.title,
    })"""

    deadline = asyncio.get_event_loop().time() + timeout_s
    last_state: dict[str, Any] = {"shadow_host_count": 0, "autofill_present": False}

    while asyncio.get_event_loop().time() < deadline:
        try:
            tabs = (
                await httpx.AsyncClient().get(
                    f"http://127.0.0.1:{cdp_port}/json/list", timeout=3.0
                )
            ).json()
            target = next(
                (
                    t
                    for t in tabs
                    if t.get("type") == "page"
                    and t.get("url", "").startswith("http")
                ),
                None,
            )
            if target is None:
                await asyncio.sleep(1.0)
                continue
            async with websockets.connect(
                target["webSocketDebuggerUrl"], max_size=10 * 1024 * 1024
            ) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "Runtime.evaluate",
                            "params": {"expression": js, "returnByValue": True},
                        }
                    )
                )
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == 1:
                        v = (
                            msg.get("result", {})
                            .get("result", {})
                            .get("value")
                        )
                        if v:
                            last_state = json.loads(v)
                        break
            if last_state.get("autofill_present"):
                last_state["elapsed_s"] = (
                    timeout_s
                    - (deadline - asyncio.get_event_loop().time())
                )
                return last_state
        except Exception as exc:  # noqa: BLE001
            last_state["last_error"] = repr(exc)
        await asyncio.sleep(2.0)

    last_state["timed_out"] = True
    return last_state


async def _bare_cdp_reload_page(cdp_port: int) -> bool:
    """Trigger a page reload via raw CDP to nudge Simplify if it didn't render.

    Args:
        cdp_port: Chrome CDP port.
    Output:
        True on success; False otherwise.
    """

    import websockets

    try:
        tabs = (
            await httpx.AsyncClient().get(
                f"http://127.0.0.1:{cdp_port}/json/list", timeout=3.0
            )
        ).json()
        target = next(
            (
                t
                for t in tabs
                if t.get("type") == "page" and t.get("url", "").startswith("http")
            ),
            None,
        )
        if target is None:
            return False
        async with websockets.connect(
            target["webSocketDebuggerUrl"], max_size=4 * 1024 * 1024
        ) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.reload"}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == 1:
                    return True
    except Exception:  # noqa: BLE001
        return False


async def _bare_cdp_capture_active_tab(
    cdp_port: int, save_dir: Path
) -> dict[str, Any]:
    """Walk Chrome's tabs via raw CDP and snapshot the most relevant http(s) tab.

    Purpose:
        After the apply flow runs, Playwright may have lost track of the page
        (TargetClosedError) because clicking Autofill can navigate or replace
        the tab. We re-discover whichever tab is still active and capture
        screenshots + DOM via raw CDP so the iteration always produces useful
        artifacts.
    Args:
        cdp_port: Chrome CDP port.
        save_dir: Directory to write artifacts into.
    Output:
        Dict with the captured tab's URL and per-shadow-root summary.
    """

    import base64
    import websockets

    out: dict[str, Any] = {"tabs_seen": [], "captured_url": None}
    try:
        tabs = (
            await httpx.AsyncClient().get(
                f"http://127.0.0.1:{cdp_port}/json/list", timeout=3.0
            )
        ).json()
    except Exception as exc:  # noqa: BLE001
        out["error"] = repr(exc)
        return out

    page_tabs = [
        t
        for t in tabs
        if t.get("type") == "page" and t.get("url", "").startswith("http")
    ]
    out["tabs_seen"] = [t.get("url") for t in page_tabs]

    if not page_tabs:
        return out

    # Prefer the most recent http(s) tab
    target = page_tabs[0]
    out["captured_url"] = target.get("url")

    try:
        async with websockets.connect(
            target["webSocketDebuggerUrl"], max_size=20 * 1024 * 1024
        ) as ws:
            async def call(
                method: str, params: dict[str, Any] | None = None
            ) -> dict[str, Any]:
                cid = getattr(call, "cid", 0) + 1
                call.cid = cid  # type: ignore[attr-defined]
                await ws.send(
                    json.dumps(
                        {"id": cid, "method": method, "params": params or {}}
                    )
                )
                while True:
                    msg: dict[str, Any] = json.loads(await ws.recv())
                    if msg.get("id") == cid:
                        return msg

            shot = await call("Page.captureScreenshot", {"format": "png"})
            data = shot.get("result", {}).get("data")
            if data:
                (save_dir / "screenshot_post_click.png").write_bytes(
                    base64.b64decode(data)
                )

            scan = await call(
                "Runtime.evaluate",
                {
                    "expression": (
                        "(() => {\n"
                        "  const hosts = document.querySelectorAll('div.simplify-jobs-shadow-root');\n"
                        "  const out = {\n"
                        "    url: location.href,\n"
                        "    title: document.title,\n"
                        "    shadow_host_count: hosts.length,\n"
                        "    shadow_summary: [],\n"
                        "    autofill_button_present: false,\n"
                        "    page_form_count: document.forms.length,\n"
                        "    page_input_count: document.querySelectorAll('input').length,\n"
                        "  };\n"
                        "  let i = 0;\n"
                        "  for (const h of hosts) {\n"
                        "    const r = h.shadowRoot;\n"
                        "    const labels = r ? Array.from(r.querySelectorAll('[aria-label]')).map(e => e.getAttribute('aria-label')) : [];\n"
                        "    out.shadow_summary.push({idx: i, size: r ? r.innerHTML.length : 0, labels});\n"
                        "    if (r && (r.querySelector('[aria-label=\"Autofill\"]') || r.querySelector('[aria-label=\"Continue filling\"]'))) {\n"
                        "      out.autofill_button_present = true;\n"
                        "    }\n"
                        "    i++;\n"
                        "  }\n"
                        "  return JSON.stringify(out);\n"
                        "})()"
                    ),
                    "returnByValue": True,
                },
            )
            v = scan.get("result", {}).get("result", {}).get("value")
            if v:
                out.update(json.loads(v))

            html = await call("Runtime.evaluate", {"expression": "document.documentElement.outerHTML", "returnByValue": True})
            html_str = html.get("result", {}).get("result", {}).get("value")
            if html_str:
                (save_dir / "dom_post_click.html").write_text(
                    html_str, encoding="utf-8"
                )
    except Exception as exc:  # noqa: BLE001
        out["capture_error"] = repr(exc)

    return out


async def _capture_shadow_dom(page: Page) -> str:
    """Extract concatenated innerHTML of every Simplify shadow root.

    Simplify v2.4.x creates multiple `simplify-jobs-shadow-root` divs. We
    return all of them with size markers so the caller can see which is the
    panel vs the inline banner.
    """

    js = """
    () => {
        const hosts = document.querySelectorAll('div.simplify-jobs-shadow-root');
        if (!hosts.length) return '__NO_SHADOW_HOST__';
        const parts = [];
        let i = 0;
        for (const host of hosts) {
            if (!host.shadowRoot) {
                parts.push('--- SHADOW#' + i + ' (NO ROOT) ---');
            } else {
                parts.push('--- SHADOW#' + i + ' (size=' + host.shadowRoot.innerHTML.length + ') ---');
                parts.push(host.shadowRoot.innerHTML);
            }
            i++;
        }
        return parts.join('\\n');
    }
    """
    try:
        result: str = await page.evaluate(js)
        return result
    except Exception as exc:  # noqa: BLE001
        return f"__EVAL_ERROR__:{exc}"


async def _scan_simplify_state(page: Page) -> dict[str, Any]:
    """Probe the page for Simplify activation across all shadow roots."""

    js = """
    () => {
        const out = {
            url: location.href,
            shadow_host_count: 0,
            shadow_roots: [],
            page_script_present: !!document.getElementById('simplify-jobs-page-script'),
            buttons: [],
            page_buttons_with_simplify: 0,
        };
        const hosts = document.querySelectorAll('div.simplify-jobs-shadow-root');
        out.shadow_host_count = hosts.length;
        let i = 0;
        for (const host of hosts) {
            const info = {
                idx: i,
                accessible: !!host.shadowRoot,
                inner_size: host.shadowRoot ? host.shadowRoot.innerHTML.length : 0,
                aria_labels: [],
            };
            if (host.shadowRoot) {
                const all = host.shadowRoot.querySelectorAll('[aria-label]');
                all.forEach(el => {
                    const label = el.getAttribute('aria-label');
                    info.aria_labels.push(label);
                    out.buttons.push({
                        host_idx: i,
                        tag: el.tagName.toLowerCase(),
                        aria_label: label,
                        text: (el.textContent || '').trim().slice(0, 80),
                        visible: !!el.offsetParent || el.getClientRects().length > 0,
                    });
                });
            }
            out.shadow_roots.push(info);
            i++;
        }
        // Top-level convenience flags
        out.shadow_host_present = out.shadow_host_count > 0;
        out.shadow_root_accessible = out.shadow_roots.some(s => s.accessible);
        out.autofill_button_present = out.buttons.some(b => b.aria_label === 'Autofill' || b.aria_label === 'Autofill all fields with AI');
        out.page_buttons_with_simplify = document.querySelectorAll('[class*="simplify" i], [id*="simplify" i]').length;
        return out;
    }
    """
    try:
        scan_result: dict[str, Any] = await page.evaluate(js)
        return scan_result
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


async def run_one(target_url: str, iter_num: int) -> dict[str, Any]:
    """Drive one apply attempt and dump artifacts.

    Args:
        target_url: Greenhouse application URL.
        iter_num: Iteration index for artifact naming.
    Output:
        Result dict (also written to result.json).
    """

    iter_dir = ITER_DIR / f"{iter_num:03d}"
    iter_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(tz=timezone.utc).isoformat()
    result: dict[str, Any] = {
        "iteration": iter_num,
        "target_url": target_url,
        "started_at": started_at,
        "stage_outcomes": {},
    }
    console_logs: list[str] = []

    # Probe import upfront so we get a clean diagnostic if browser.py is broken.
    try:
        import importlib

        importlib.import_module("src.agents.apply_worker.browser")
        result["apply_worker_import_ok"] = True
    except Exception as exc:  # noqa: BLE001
        result["apply_worker_import_ok"] = False
        result["apply_worker_import_error"] = repr(exc)
        (iter_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        return result

    # Self-heal: ensure Simplify's extension dir exists in the clone.
    # Required for the content script to render its side panel reliably.
    _ensure_simplify_dir_in_clone()

    cdp_port = _free_port()
    # Chrome is launched with the target URL as its initial page so Simplify
    # has a chance to activate naturally before Playwright attaches.
    chrome_proc = _launch_chrome_with_profile(cdp_port, target_url)
    result["chrome_pid"] = chrome_proc.pid
    result["cdp_port"] = cdp_port

    try:
        cdp_ready = await _wait_for_cdp(cdp_port)
        if not cdp_ready:
            result["stage_outcomes"]["chrome_launch"] = "FAIL: CDP never came up"
            (iter_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            return result
        result["stage_outcomes"]["chrome_launch"] = "OK"

        # CRITICAL: Wait for Simplify to fully render its panel via RAW CDP
        # before Playwright attaches. Empirically, Playwright's
        # connect_over_cdp during Simplify's content-script init prevents
        # the React side panel from finishing render. Once the panel is up
        # we can safely attach Playwright and the panel survives.
        simplify_pre_state = await _bare_cdp_wait_for_simplify(
            cdp_port, timeout_s=SIMPLIFY_RENDER_WAIT_S
        )
        result["simplify_pre_attach"] = simplify_pre_state
        # If still not rendered, try a single page reload — Simplify's
        # rendering is intermittent (~33% miss rate observed) and a reload
        # often succeeds where the first load did not.
        if not simplify_pre_state.get("autofill_present"):
            await _bare_cdp_reload_page(cdp_port)
            simplify_pre_state = await _bare_cdp_wait_for_simplify(
                cdp_port, timeout_s=SIMPLIFY_RENDER_WAIT_S
            )
            result["simplify_pre_attach_after_reload"] = simplify_pre_state
        result["stage_outcomes"]["simplify_pre_attach"] = (
            "OK" if simplify_pre_state.get("autofill_present") else "MISSING"
        )

        # Connect Playwright to the running Chrome.
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{cdp_port}",
                )
            except Exception as exc:  # noqa: BLE001
                result["stage_outcomes"]["cdp_connect"] = f"FAIL: {exc}"
                (iter_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
                return result
            result["stage_outcomes"]["cdp_connect"] = "OK"

            context = browser.contexts[0] if browser.contexts else None
            if context is None:
                result["stage_outcomes"]["cdp_connect"] = "FAIL: no contexts"
                (iter_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
                return result

            # Use Chrome's existing initial tab (already loaded with target URL)
            # rather than creating a new one. Simplify's content script
            # behaves better when activation isn't competing with Playwright
            # attachment.
            existing_pages = list(context.pages)
            page = None
            for candidate in existing_pages:
                if "greenhouse" in candidate.url or target_url in candidate.url:
                    page = candidate
                    break
            if page is None:
                logger.warning(
                    "No greenhouse tab found among {}; falling back to new_page",
                    [p.url for p in existing_pages],
                )
                page = await context.new_page()
                await page.goto(
                    target_url, timeout=45_000, wait_until="domcontentloaded"
                )
            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda exc: console_logs.append(f"[pageerror] {exc}"))

            try:
                # If page is still loading or wasn't navigated yet, ensure
                # it's at the target URL. Otherwise just confirm load state.
                if target_url not in page.url:
                    await page.goto(
                        target_url, timeout=45_000, wait_until="domcontentloaded"
                    )
                try:
                    await page.wait_for_load_state("networkidle", timeout=20_000)
                except Exception:
                    pass
                result["stage_outcomes"]["navigate"] = "OK"
                result["page_url"] = page.url
            except Exception as exc:  # noqa: BLE001
                result["stage_outcomes"]["navigate"] = f"FAIL: {exc}"
                try:
                    await page.screenshot(
                        path=str(iter_dir / "screenshot.png"), full_page=True
                    )
                except Exception:
                    pass
                (iter_dir / "console.log").write_text("\n".join(console_logs))
                (iter_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
                return result

            # Wait for Simplify to inject. Verified: full UI takes ~15s on
            # Greenhouse. We poll every 2s and stop early once the Autofill
            # button shows up in the shadow root.
            scan: dict[str, Any] = {}
            elapsed_ms = 0
            while elapsed_ms < SIMPLIFY_RENDER_WAIT_S * 1000:
                await page.wait_for_timeout(2_000)
                elapsed_ms += 2_000
                scan = await _scan_simplify_state(page)
                labels = {
                    b.get("aria_label") for b in scan.get("buttons", [])
                }
                if "Autofill" in labels or "Autofill all fields with AI" in labels:
                    scan["render_completion_ms"] = elapsed_ms
                    break
            result["simplify_scan"] = scan

            # Save shadow DOM and page DOM snapshots before apply_to_job runs.
            try:
                shadow_html = await _capture_shadow_dom(page)
                (iter_dir / "shadow_dom_pre.html").write_text(
                    shadow_html, encoding="utf-8"
                )
            except Exception as exc:  # noqa: BLE001
                result["shadow_capture_pre_error"] = repr(exc)

            try:
                (iter_dir / "dom_pre.html").write_text(
                    await page.content(), encoding="utf-8"
                )
            except Exception as exc:  # noqa: BLE001
                result["dom_capture_pre_error"] = repr(exc)

            try:
                await page.screenshot(
                    path=str(iter_dir / "screenshot_pre.png"), full_page=True
                )
            except Exception:
                pass

            # Drive the apply flow using the production code path.
            try:
                from src.agents.apply_worker.browser import _run_application_flow

                run_result = await _run_application_flow(
                    page=page,
                    source_url=target_url,
                    resume_pdf_path=RESUME_PDF,
                    job_hash=f"smoke-{iter_num:03d}",
                    screenshot_path=iter_dir / "screenshot.png",
                    dom_snapshot_path=iter_dir / "dom_post.html",
                    unresolved_path=iter_dir / "unresolved_fields.json",
                    dry_run=True,
                )
                result["stage_outcomes"]["apply_flow"] = (
                    "OK" if run_result.success else "FAIL"
                )
                result["apply_run_result"] = run_result.model_dump()
            except Exception as exc:  # noqa: BLE001
                logger.exception("apply flow blew up")
                result["stage_outcomes"]["apply_flow"] = f"EXC: {exc!r}"

            # Re-capture after the flow even if it raised. If the page got
            # closed/navigated by Autofill click, fall back to raw CDP.
            try:
                shadow_html_post = await _capture_shadow_dom(page)
                (iter_dir / "shadow_dom_post.html").write_text(
                    shadow_html_post, encoding="utf-8"
                )
            except Exception:
                pass
            try:
                await page.screenshot(
                    path=str(iter_dir / "screenshot_final.png"), full_page=True
                )
            except Exception:
                pass
            try:
                scan_post = await _scan_simplify_state(page)
                result["simplify_scan_post"] = scan_post
            except Exception as exc:  # noqa: BLE001
                result["simplify_scan_post"] = {"error": str(exc)}

            # Don't close page or browser before bare-CDP recovery —
            # closing the only tab can shut down Chrome entirely.

        # Bare-CDP recovery: capture whichever tab is still open (the apply
        # flow may have triggered a navigation that detached Playwright).
        try:
            recovery = await _bare_cdp_capture_active_tab(cdp_port, iter_dir)
            result["post_click_capture"] = recovery
        except Exception as exc:  # noqa: BLE001
            result["post_click_capture_error"] = repr(exc)
    finally:
        # Always tear down Chrome.
        try:
            chrome_proc.terminate()
            chrome_proc.wait(timeout=10)
        except Exception:
            try:
                chrome_proc.kill()
            except Exception:
                pass

    (iter_dir / "console.log").write_text("\n".join(console_logs), encoding="utf-8")
    result["finished_at"] = datetime.now(tz=timezone.utc).isoformat()

    apply_result = result.get("apply_run_result") or {}
    confidence_report = apply_result.get("confidence_report") or {}
    result["pass"] = bool(
        result["stage_outcomes"].get("navigate") == "OK"
        and result["stage_outcomes"].get("apply_flow") == "OK"
        and confidence_report.get("simplify_autofill_detected")
        and confidence_report.get("resume_uploaded")
    )

    (iter_dir / "result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    return result


def _summarize_for_runlog(result: dict[str, Any]) -> str:
    """Render a compact markdown summary of one iteration."""

    iter_num = result["iteration"]
    url = result["target_url"]
    stages = result.get("stage_outcomes", {})
    apply_result = result.get("apply_run_result") or {}
    confidence_report = apply_result.get("confidence_report") or {}
    simplify_scan = result.get("simplify_scan") or {}

    short_stages = {}
    for k, v in stages.items():
        s = str(v)
        short_stages[k] = s if len(s) < 120 else s[:120] + "..."

    lines = [
        f"## Iteration {iter_num} — {url.split('?')[0].rsplit('/', 1)[-1]}",
        "",
        f"- target: `{url}`",
        f"- pass: **{result.get('pass')}**",
        f"- stages: {short_stages}",
        f"- shadow_host_present: {simplify_scan.get('shadow_host_present')} | "
        f"shadow_root_accessible: {simplify_scan.get('shadow_root_accessible')} | "
        f"buttons_found: {len(simplify_scan.get('buttons', []))}",
        f"- simplify_autofill_detected: {confidence_report.get('simplify_autofill_detected')}",
        f"- resume_uploaded: {confidence_report.get('resume_uploaded')}",
        f"- unresolved_required: {confidence_report.get('unresolved_required_count')}",
        f"- confidence_score: {confidence_report.get('score')}",
        f"- artifacts: `.research/simplify-loop/iterations/{iter_num:03d}/`",
    ]
    if "apply_worker_import_error" in result:
        lines.append(f"- import_error: `{result['apply_worker_import_error']}`")
    if apply_result.get("failure_reason"):
        lines.append(f"- failure_reason: {apply_result['failure_reason']}")
    return "\n".join(lines)


async def main() -> int:
    """Entrypoint: parse args, pick target, run one iteration, write artifacts."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-index",
        type=int,
        default=None,
        help="Index into targets.txt (0-based). Defaults to rotating through.",
    )
    parser.add_argument(
        "--target-url",
        type=str,
        default=None,
        help="Override target URL (skips targets.txt).",
    )
    args = parser.parse_args()

    targets = _read_targets()
    if not targets:
        logger.error("No targets in {}", TARGETS_FILE)
        return 2

    state = _load_state()

    if args.target_url:
        url = args.target_url
        idx = -1
    else:
        if args.target_index is not None:
            idx = args.target_index % len(targets)
        else:
            idx = (state.get("last_target_index", -1) + 1) % len(targets)
        url = targets[idx]

    iter_num = _next_iter_num()
    logger.info("Starting iteration {} against {}", iter_num, url)

    result = await run_one(url, iter_num)

    state["iteration_count"] = iter_num
    state["last_target_index"] = idx
    state["last_run_status"] = "PASS" if result.get("pass") else "FAIL"
    if result.get("pass"):
        state["consecutive_successes"] = state.get("consecutive_successes", 0) + 1
    else:
        state["consecutive_successes"] = 0
    if state.get("loop_started_at") is None:
        state["loop_started_at"] = datetime.now(tz=timezone.utc).isoformat()
    _save_state(state)

    _append_runlog(_summarize_for_runlog(result))

    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""Run the end-to-end Wi-Fi-off verification for the local Knowledge Galaxy.

Requires the Ada backend and Knowledge Galaxy viewer to be running. The optional
browser pass uses the project's installed Playwright/Chromium and opens ?mute=1.
"""
from __future__ import annotations

import argparse
import array
import base64
import io
import wave
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from network_audit import install, read_events

install(ROOT)
BACKEND = "http://127.0.0.1:8001"
VIEWER = "http://127.0.0.1:4700"


def request(url: str, payload: dict | None = None, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wav24_to_wav16k(wav_bytes: bytes) -> str:
    with wave.open(io.BytesIO(wav_bytes), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise RuntimeError("The TTS response must be mono 16-bit PCM WAV.")
        source_rate = source.getframerate()
        samples = array.array("h")
        samples.frombytes(source.readframes(source.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    target_rate = 16000
    target_count = max(1, round(len(samples) * target_rate / source_rate))
    target = array.array("h")
    for index in range(target_count):
        position = index * source_rate / target_rate
        left = min(int(position), len(samples) - 1)
        right = min(left + 1, len(samples) - 1)
        fraction = position - left
        target.append(int(samples[left] * (1 - fraction) + samples[right] * fraction))
    if sys.byteorder != "little":
        target.byteswap()
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(target_rate)
        wav.writeframes(target.tobytes())
    return base64.b64encode(output.getvalue()).decode("ascii")

def run_browser(question: str) -> list[str]:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(VIEWER + "/?mute=1", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#galaxy canvas", timeout=30000)
        page.locator("#question").fill(question)
        page.locator("#send").click()
        page.wait_for_function(
            "() => document.querySelector('#answer')?.textContent.trim().length > 0",
            timeout=180000,
        )
        hosts = page.evaluate("""() => [...new Set(
          performance.getEntriesByType('resource').map(entry => {
            try { return new URL(entry.name).host; } catch { return ''; }
          }).filter(Boolean)
        )]""")
        page.request.post(VIEWER + "/network-audit", data=json.dumps({"hosts": hosts}), headers={"Content-Type": "application/json"})
        browser.close()
        return hosts


def external(host: str) -> bool:
    value = host.casefold().strip()
    if value.startswith("[") and "]" in value:
        value = value[1:value.index("]")]
    elif value.count(":") == 1:
        value = value.rsplit(":", 1)[0]
    return not (
        value in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
        or value.startswith("127.")
    )


def honest_internet_list() -> list[str]:
    hosts: set[str] = set()
    for folder in (ROOT / "backend", ROOT / "scripts", ROOT / "viewer"):
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.suffix not in {".py", ".ps1", ".js", ".html", ".json", ".md"}:
                continue
            if any(part in {"node_modules", ".git", ".ada", "__pycache__"} for part in path.parts):
                continue
            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for host in re.findall(r"https?://([^/\s\"'<>]+)", source):
                if external(host):
                    hosts.add(host.rstrip("),;"))
    return sorted(hosts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="Skip the Playwright viewer pass.")
    args = parser.parse_args()

    try:
        request(BACKEND + "/network-audit/clear", {})
        graph = request(VIEWER + "/graph")
        nodes = graph.get("nodes", [])
        if not nodes:
            raise RuntimeError("No Markdown notes are indexed; add notes before the end-to-end drill.")
        note = nodes[0]
        question = f"What are the key facts in the note {note.get('label', 'first note')}?"
        chat = request(VIEWER + "/chat", {"question": question, "session_id": "offline-drill"})
        answer = chat.get("answer", "")
        if not answer:
            raise RuntimeError("Local /chat returned an empty answer.")
        print("CHAT:", answer)

        speech_payload = {"text": answer}
        speech_request = urllib.request.Request(
            BACKEND + "/speak",
            data=json.dumps(speech_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(speech_request, timeout=120) as response:
                speech_wav = response.read()
                voice_receipt = response.headers.get("X-Jarvis-Voice", "unknown")
        except urllib.error.HTTPError as exc:
            if exc.code != 503:
                raise
            speech_payload["provider"] = "piper"
            fallback_request = urllib.request.Request(
                BACKEND + "/speak",
                data=json.dumps(speech_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(fallback_request, timeout=120) as response:
                speech_wav = response.read()
                voice_receipt = response.headers.get("X-Jarvis-Voice", "unknown")
        if len(speech_wav) < 44 or speech_wav[:4] != b"RIFF":
            raise RuntimeError("Local /speak did not return a valid audio/wav response.")
        print("VOICE:", voice_receipt)
        heard = request(BACKEND + "/hear", {
            "audio_wav": wav24_to_wav16k(speech_wav),
            "mode": "command",
        })
        if heard.get("error"):
            raise RuntimeError("Local /hear failed: " + heard["error"])
        print("HEAR:", heard.get("transcript", "(no transcript returned)"))

        browser_hosts = []
        if not args.no_browser:
            try:
                browser_hosts = run_browser(question)
                print("BROWSER RESOURCE HOSTS:", ", ".join(browser_hosts) or "(none)")
            except Exception as exc:
                raise RuntimeError(f"Browser resource-timing pass failed: {type(exc).__name__}: {exc}") from exc

        events = read_events()
        hosts = sorted({str(event.get("host", "")) for event in events if event.get("host")})
        outside = [host for host in hosts if external(host)]
        print("SERVER CONNECTIONS:")
        for event in events:
            print(f"  {event.get('host')}:{event.get('port') or ''} — {event.get('reason')}")
        print("NON-LOCAL HOSTS:", json.dumps(outside))
        print("CLOUD BRAIN:", "disabled; local-only build")
        print("HONEST LIST — internet may be needed for initial setup/downloads or optional external integrations:")
        for host in honest_internet_list():
            print("  " + host)
        if outside:
            print("FAIL: at least one server connection left loopback.")
            return 1
        if not heard.get("transcript"):
            print("FAIL: the TTS audio did not produce a Whisper transcript.")
            return 1
        print("PASS: /chat, local TTS, Whisper transcription, browser resource timing, and server outbound audit completed.")
        return 0
    except (OSError, urllib.error.URLError, RuntimeError, ValueError) as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

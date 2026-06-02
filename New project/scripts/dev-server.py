#!/usr/bin/env python3
"""Local static server that refreshes fix JSON from the workbook before serving."""

from __future__ import annotations

import argparse
import cgi
import http.server
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIX_WORKBOOK = ROOT / "Assets" / "FIXES ORF.xlsx"
FIX_JSON = ROOT / "Assets" / "orf-fixes.json"
UPDATE_SCRIPT = ROOT / "scripts" / "update-fixes-json.py"
SID_ROUTE_WORKBOOK = ROOT / "Assets" / "ORF_Destination_SID_Transition_Route_Map.xlsx"
SID_ROUTE_JSON = ROOT / "Assets" / "orf-sid-route-map.json"
SID_ROUTE_SCRIPT = ROOT / "scripts" / "generate_sid_route_map.py"
OPENAI_API_BASE = "https://api.openai.com/v1"
SESSION_OPENAI_API_KEY = ""


def refresh_fixes_if_needed() -> None:
    if not FIX_WORKBOOK.exists():
        return
    if FIX_JSON.exists() and FIX_JSON.stat().st_mtime >= FIX_WORKBOOK.stat().st_mtime:
        return
    try:
        subprocess.run([sys.executable, str(UPDATE_SCRIPT), str(FIX_WORKBOOK), str(FIX_JSON)], check=True)
    except subprocess.CalledProcessError as error:
        print(f"Warning: fix refresh failed; serving existing {FIX_JSON.name}: {error}", file=sys.stderr)


def refresh_sid_routes_if_needed() -> None:
    if not SID_ROUTE_WORKBOOK.exists():
        return
    if SID_ROUTE_JSON.exists() and SID_ROUTE_JSON.stat().st_mtime >= SID_ROUTE_WORKBOOK.stat().st_mtime:
        return
    try:
        subprocess.run([sys.executable, str(SID_ROUTE_SCRIPT)], check=True)
    except subprocess.CalledProcessError as error:
        print(f"Warning: SID route refresh failed; serving existing {SID_ROUTE_JSON.name}: {error}", file=sys.stderr)


class RefreshingHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        refresh_fixes_if_needed()
        refresh_sid_routes_if_needed()
        super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/openai-key":
            self.handle_openai_key()
            return
        if self.path == "/api/transcribe":
            self.handle_transcribe()
            return
        if self.path == "/api/tts":
            self.handle_tts()
            return
        self.send_error(404, "Unknown API endpoint")

    def api_key(self) -> str:
        return (SESSION_OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")).strip()

    def send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def handle_openai_key(self) -> None:
        global SESSION_OPENAI_API_KEY
        try:
            payload = self.read_json_body()
            api_key = str(payload.get("apiKey", "")).strip()
            if not api_key.startswith("sk-"):
                self.send_json(400, {"ok": False, "error": "That does not look like an OpenAI API key."})
                return
            SESSION_OPENAI_API_KEY = api_key
            self.send_json(200, {"ok": True, "configured": True})
        except Exception as error:  # noqa: BLE001
            self.send_json(400, {"ok": False, "error": str(error)})

    def handle_transcribe(self) -> None:
        key = self.api_key()
        if not key:
            self.send_json(503, {"error": "OPENAI_API_KEY is not set on the local dev server."})
            return
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        audio_field = form["audio"] if "audio" in form else None
        if audio_field is None or not getattr(audio_field, "file", None):
            self.send_json(400, {"error": "Missing audio field."})
            return
        audio_bytes = audio_field.file.read()
        if not audio_bytes:
            self.send_json(400, {"error": "Empty audio clip."})
            return
        model = os.environ.get("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
        try:
            response = self.openai_multipart(
                "/audio/transcriptions",
                {
                    "model": model,
                    "language": "en",
                    "response_format": "json",
                    "prompt": "Air traffic control phraseology around Norfolk Approach. Callsigns include AAL, JBU, DAL, NKS, FFT, SWA, UAL, and November aircraft. Fixes include OMRIE, RILLO, MERFE, CEGLI, CROOM, OUTLA, KOHLS, NUTZE, WINAL, ETUME, ISUBE, MOTUE, and HCM.",
                },
                "file",
                getattr(audio_field, "filename", "controller.webm") or "controller.webm",
                audio_bytes,
                getattr(audio_field, "type", "audio/webm") or "audio/webm",
            )
            text = json.loads(response.decode("utf-8")).get("text", "")
            self.send_json(200, {"text": text})
        except Exception as error:  # noqa: BLE001 - local dev server should surface API failures.
            self.send_json(502, {"error": str(error)})

    def handle_tts(self) -> None:
        key = self.api_key()
        if not key:
            self.send_json(503, {"error": "OPENAI_API_KEY is not set on the local dev server."})
            return
        try:
            payload = self.read_json_body()
            text = str(payload.get("text", "")).strip()
            voice = str(payload.get("voice", "alloy")).strip() or "alloy"
            if not text:
                self.send_json(400, {"error": "Missing text."})
                return
            body = json.dumps({
                "model": os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
                "voice": voice,
                "input": text,
                "instructions": "Sound like a calm, concise VHF radio pilot readback. Clear aviation cadence, no extra words.",
                "response_format": "mp3",
            }).encode("utf-8")
            request = urllib.request.Request(
                f"{OPENAI_API_BASE}/audio/speech",
                data=body,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                audio = response.read()
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(audio)
        except Exception as error:  # noqa: BLE001
            self.send_json(502, {"error": str(error)})

    def openai_multipart(
        self,
        path: str,
        fields: dict[str, str],
        file_field: str,
        filename: str,
        file_bytes: bytes,
        mime_type: str,
    ) -> bytes:
        boundary = "----orf-atc-sim-openai-boundary"
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.append(f"--{boundary}\r\n".encode("utf-8"))
            chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            chunks.append(str(value).encode("utf-8"))
            chunks.append(b"\r\n")
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
            .encode("utf-8")
        )
        chunks.append(file_bytes)
        chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(chunks)
        request = urllib.request.Request(
            f"{OPENAI_API_BASE}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key()}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API error {error.code}: {detail}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), RefreshingHandler)
    print(f"Serving ORF sim at http://127.0.0.1:{args.port}/")
    print("Fixes refresh from Assets/FIXES ORF.xlsx whenever the page is refreshed.")
    print("SID routes refresh from Assets/ORF_Destination_SID_Transition_Route_Map.xlsx whenever the page is refreshed.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

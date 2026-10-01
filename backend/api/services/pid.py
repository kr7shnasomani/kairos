"""
P&ID topology service — Layer 3: engineering-drawing perception (Path B).

Extracts structured topology JSON from a Piping & Instrumentation Diagram using a
cloud vision-language model (NVIDIA NIM). This is vision-*understanding*, NOT OCR:
OCR would flatten the drawing into disconnected text labels and destroy the
spatial connections that ARE the drawing's information (which valve isolates which
pump, which loop controls which line).

Path A (custom-trained YOLOv9 + LayoutLMv3 on local GPU) is the documented future
upgrade once a labeled P&ID dataset exists — see docs/ARCHITECTURE.md Layer 3.
Either way, every extracted element routes to mandatory element-by-element engineer
verification before it becomes canonical (Layer 7), so an imperfect extraction is
safe by design — the model pre-populates the review, a human confirms.
"""

import json
import os
from typing import Any

import httpx
import structlog

from api.services.http import shared_client
from api.services.image_utils import shrink_image_for_nim_b64
from api.services.ocr import capped_dpi

log = structlog.get_logger(__name__)

# Inline base64 cap — defined in image_utils, imported above for reference in _fit_b64.
_PID_DPI = 150  # rasterize PDFs denser than OCR (96) — drawings are detail-heavy

_TOPOLOGY_KEYS = ("equipment_nodes", "isolation_valves", "instrumentation_loops", "isolation_boundaries")

_PROMPT = """You are a process-safety engineer digitizing a P&ID (Piping & Instrumentation Diagram).
Extract the drawing's TOPOLOGY as strict JSON. Preserve connection meaning — do not just read text.

Return ONLY a JSON object (no prose, no markdown fences) with exactly these keys:
- "drawing_id": string (drawing number if visible, else "")
- "title": string
- "revision": string
- "equipment_nodes": [ {"id":"TOPO-EQ-001","tag":"P-101","type":"centrifugal_pump","service":"...","equipment_class":"pump|vessel|heat_exchanger|instrument"} ]
- "isolation_valves": [ {"id":"TOPO-VLV-001","tag":"XV-203","type":"gate_valve","service":"...","normally_open":true} ]
- "instrumentation_loops": [ {"id":"TOPO-LOOP-001","loop_id":"FIC-3047","type":"flow_control","instruments":["FT-3047","FV-3047"]} ]
- "isolation_boundaries": [ {"id":"TOPO-ISO-001","boundary_id":"ISO-...","description":"...","primary_isolations":["XV-203"],"requires_double_block_bleed":true,"ptw_type":"mechanical","requires_engineer_signoff":true} ]

Rules:
- Give every element a unique "id" using the TOPO-EQ / TOPO-VLV / TOPO-LOOP / TOPO-ISO prefixes.
- Use "" or [] for anything not legible. Never invent tags you cannot see.
- Isolation boundaries are safety-critical: capture which valves isolate which equipment.

Respond with ONLY the JSON object. No preamble, no explanation, no markdown. Begin your response with { and end with }."""

_SYSTEM = "You are a JSON extraction engine. Your entire response is a single valid JSON object and nothing else — never prose, never markdown fences, never commentary."


class PIDService:
    """Vision-model P&ID topology extractor (Layer 3, Path B)."""

    def __init__(self) -> None:
        self.api_key = os.getenv("NVIDIA_NIM_API_KEY", "")
        self.model = os.getenv("NVIDIA_NIM_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct")
        self.base_url = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")

    async def extract_topology(self, file_bytes: bytes, mime_type: str) -> dict[str, Any] | None:
        """Extract topology from a drawing. Returns the topology dict, or None on any
        failure so the caller can fall back (to the demo fixture) without crashing."""
        if not self.api_key:
            log.error("pid.no_nim_key", hint="Set NVIDIA_NIM_API_KEY")
            return None

        img = self._first_image(file_bytes, mime_type)
        if img is None:
            log.warning("pid.no_image", mime=mime_type)
            return None

        fitted = self._fit_b64(*img)
        if fitted is None:
            log.warning("pid.image_could_not_fit_inline_limit")
            return None
        b64, img_mime = fitted

        answer = await self._call_vlm(b64, img_mime)
        if not answer:
            return None

        topology = self._parse_json(answer)
        if topology is None or not any(topology.get(k) for k in _TOPOLOGY_KEYS):
            log.warning("pid.unparseable_or_empty", preview=answer[:200])
            return None

        for k in _TOPOLOGY_KEYS:  # downstream flattening reads every group
            topology.setdefault(k, [])
        log.info(
            "pid.topology_extracted",
            model=self.model,
            equipment=len(topology["equipment_nodes"]),
            valves=len(topology["isolation_valves"]),
            loops=len(topology["instrumentation_loops"]),
            boundaries=len(topology["isolation_boundaries"]),
        )
        return topology

    async def _call_vlm(self, b64: str, img_mime: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{img_mime};base64,{b64}"}},
                    ],
                },
            ],
            "max_tokens": 4096,
            "temperature": 0.1,
            "top_p": 0.7,
            "stream": False,
        }
        try:
            client = shared_client(120.0)
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
                json=payload,
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"] or ""
        except httpx.HTTPStatusError as exc:
            log.error("pid.nim_error", status=exc.response.status_code, body=exc.response.text[:300])
            return ""
        except Exception as exc:
            log.error("pid.nim_failed", error=str(exc))
            return ""

    @staticmethod
    def _parse_json(answer: str) -> dict[str, Any] | None:
        """Pull the JSON object out of the model's reply (tolerates markdown fences/prose)."""
        s = answer.strip()
        start, end = s.find("{"), s.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(s[start : end + 1])
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _first_image(file_bytes: bytes, mime_type: str) -> tuple[bytes, str] | None:
        """One PNG of the drawing (first page for PDFs, the image itself otherwise)."""
        if mime_type == "application/pdf":
            try:
                import fitz

                doc = fitz.open(stream=file_bytes, filetype="pdf")
                try:
                    if doc.page_count == 0:
                        return None
                    rect = doc[0].rect
                    # Drawings are large sheets; the shared ceiling keeps one page from becoming a
                    # multi-gigabyte bitmap (an A0 sheet at 150 DPI already exceeds the pixel cap).
                    dpi = capped_dpi(rect.width, rect.height, _PID_DPI)
                    if dpi is None:
                        log.warning("pid.page_size_rejected", width_pt=rect.width, height_pt=rect.height)
                        return None
                    png = doc[0].get_pixmap(dpi=dpi).tobytes("png")
                finally:
                    doc.close()
                return (png, "image/png")
            except Exception as exc:
                log.error("pid.rasterize_failed", error=str(exc))
                return None
        return (file_bytes, mime_type)

    @staticmethod
    def _fit_b64(img_bytes: bytes, img_mime: str) -> tuple[str, str] | None:
        """Base64 the image, downscaling with Pillow until it fits the inline cap.

        Thin wrapper around `image_utils.shrink_image_for_nim_b64` — algorithm
        and constant now live there so OCR and PID share a single implementation.
        If the image is already under the ceiling it is returned as-is (original
        mime type preserved), otherwise it is re-encoded as JPEG with progressive
        downscale.
        """
        return shrink_image_for_nim_b64(img_bytes, img_mime)

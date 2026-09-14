"""
OCR service — Layer 3: Multimodal Perception Engine.
Primary: NVIDIA NIM Nemotron-OCR-v2 via the CV API (https://ai.api.nvidia.com/v1/cv/<model>).
Fast path: plain text and native digital PDFs need no API call.

NOTE: The OCR model uses a DIFFERENT base URL and request format than the chat/LLM models.
- LLM/NER: https://integrate.api.nvidia.com/v1/chat/completions  (OpenAI-compatible)
- OCR/CV:  https://ai.api.nvidia.com/v1/cv/<model-name>           (CV API)
"""

import base64
import io
from typing import Any

import httpx
import structlog

from api.services.http import shared_client
from api.services.image_utils import _NIM_IMAGE_SIZE_LIMIT, shrink_image_for_nim

log = structlog.get_logger(__name__)

# CV API — model name is part of the URL path, not the payload
_NIM_CV_BASE = "https://ai.api.nvidia.com/v1/cv"

# A span the model itself does not trust. Matches the `< 0.7` quarantine threshold in CLAUDE.md so
# "the model is unsure about this text" and "this knowledge needs a human" mean the same number.
_LOW_CONFIDENCE_SPAN = 0.7
# Below this weighted mean the text is unusable as a whole, not merely suspect in places.
_UNUSABLE_OVERALL = 0.5


def ocr_review_reason(result: dict[str, Any]) -> str | None:
    """Why an OCR result must stop for human review, or None when it may continue (decision D1 = b).

    Gates on *shape*, not only on the mean: a scan whose average passes can still carry one misread
    value ("18.5 bar" for "16.2 bar"), and that single span is the dangerous failure. So any span the
    model itself scores under `_LOW_CONFIDENCE_SPAN` holds the document, whatever the overall score.
    Native text and digital PDFs carry no spans and default to passing.
    """
    if result.get("overall_confidence", 0.0) < _UNUSABLE_OVERALL:
        return "low_ocr_confidence"
    if result.get("low_confidence_spans", 0) > 0:
        return "low_confidence_spans"
    return None

_TEXT_MIMES = ("text/plain", "text/markdown", "text/csv")

# Spreadsheets: work-order exports, asset registries, inspection logs.
_SPREADSHEET_MIMES = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.ms-excel",                                          # .xls (xlsx-era files often mislabelled)
    "application/vnd.oasis.opendocument.spreadsheet",                    # .ods
)

# Email archives: the "scattered across email" corpus in the problem statement.
_EMAIL_MIMES = ("message/rfc822", "application/mbox", "text/rfc822-headers")

# Headers worth keeping — they carry the personnel/date entities NER looks for.
_EMAIL_HEADERS = ("Date", "From", "To", "Cc", "Subject")


class OCRService:
    def __init__(self):
        import os
        self.api_key = os.getenv("NVIDIA_NIM_API_KEY", "")
        self.model = os.getenv("NVIDIA_NIM_OCR_MODEL", "nvidia/nemotron-ocr-v2")

    async def extract_text(
        self,
        file_bytes: bytes,
        mime_type: str = "application/pdf",
        language_hint: str | None = None,
    ) -> dict[str, Any]:
        # Fast path: plain text files — decode directly, no API cost
        if mime_type in _TEXT_MIMES:
            text = file_bytes.decode("utf-8", errors="replace").strip()
            if text:
                return self._native(text, "native_text")

        # Fast path: spreadsheets — structured cells, never an OCR problem
        if mime_type in _SPREADSHEET_MIMES:
            text = self._extract_spreadsheet(file_bytes)
            if text:
                return self._native(text, "spreadsheet")
            return self._empty("spreadsheet_unreadable")

        # Fast path: email archives (.eml / .mbox) — stdlib parsing, no API cost
        if mime_type in _EMAIL_MIMES:
            text = self._extract_email(file_bytes)
            if text:
                return self._native(text, "email")
            return self._empty("email_unreadable")

        # Fast path: native text from digital PDFs — no API cost
        if mime_type == "application/pdf":
            native = self._extract_native_pdf(file_bytes)
            if native["blocks"]:
                return native

        # Scanned/image document — rasterize and send to NIM
        images = self._to_images(file_bytes, mime_type)
        if not images:
            return self._empty("could_not_rasterize")

        blocks = []
        spans: list[tuple[str, float]] = []
        for page_num, (img_bytes, img_mime) in enumerate(images):
            page_text, page_spans = await self._nim_ocr(img_bytes, img_mime)
            if page_text:
                spans.extend(page_spans)
                blocks.append({
                    "text": page_text,
                    "confidence": self._weighted_confidence(page_spans),
                    "page": page_num + 1,
                    "extraction_method": "nim_ocr",
                })

        if not blocks:
            return self._empty("nim_returned_no_text")

        full_text = "\n".join(b["text"] for b in blocks)
        confidence = self._weighted_confidence(spans)
        weak = [c for _, c in spans if c < _LOW_CONFIDENCE_SPAN]
        if weak:
            # Not an error — a degraded scan legitimately transcribes badly in places. Logged so a
            # document that reached the canonical graph on a passing average can still be traced.
            log.warning("ocr.low_confidence_spans", weak=len(weak), total=len(spans),
                        min_confidence=round(min(c for _, c in spans), 3),
                        overall_confidence=round(confidence, 3))
        return {
            "text": full_text,
            "blocks": blocks,
            # The model's own confidence, weighted by how much text each span carries — NOT the
            # hardcoded 0.95 this used to report. That constant meant a badly garbled scan and a
            # clean one were indistinguishable to every downstream gate, and the `< 0.7` quarantine
            # rule was being applied to a number that could never be below 0.7.
            "overall_confidence": confidence,
            # A single average cannot express "4 of 22 spans are unreliable", and the dangerous
            # failure here is one misread value (`16.2 bar` as `18.5 bar`), not a poor mean. These
            # carry that shape to anything that wants to act on it.
            "min_span_confidence": round(min((c for _, c in spans), default=0.0), 4),
            "low_confidence_spans": len(weak),
            "span_count": len(spans),
            "requires_review": False,
            "block_count": len(blocks),
            "extraction_method": "nim_ocr",
            # Layer 3: text that came off an image, not out of a digital document. Scans and
            # field forms are where handwriting lives, so this flag — not a lowered confidence
            # score — is what marks it. Deliberately NOT scaling `overall_confidence`: that would
            # push these extractions under the 0.7 quarantine threshold and silently move real
            # facts out of the canonical graph, which is a retrieval regression, not a safeguard.
            "extraction_path": "ocr",
            "handwriting_suspect": True,
        }

    @staticmethod
    def _weighted_confidence(spans: list[tuple[str, float]]) -> float:
        """
        Mean of the model's per-span confidence, weighted by span length.

        Length-weighted rather than plain: a long garbled line should move the number more than a
        two-character margin mark. Measured on the corpus this is what separates the documents —
        plain mean rates the worst scan 0.805, weighted rates it 0.719, while the clean handwritten
        notes stay at 0.90.
        """
        chars = sum(len(text) for text, _ in spans)
        if not chars:
            return 0.0
        return round(sum(len(text) * conf for text, conf in spans) / chars, 4)

    async def _nim_ocr(self, img_bytes: bytes, img_mime: str) -> tuple[str, list[tuple[str, float]]]:
        """Returns (joined text, [(span text, span confidence), ...]) — empty on every failure."""
        if not self.api_key:
            log.error("ocr.no_nim_key", hint="Set NVIDIA_NIM_API_KEY in .env")
            return "", []

        b64 = base64.b64encode(img_bytes).decode()
        if len(b64) > _NIM_IMAGE_SIZE_LIMIT:
            shrunk = self._shrink_for_inline(img_bytes)
            if shrunk is None:
                log.error("ocr.image_too_large", b64_len=len(b64), limit=_NIM_IMAGE_SIZE_LIMIT,
                          hint="Could not re-encode under the inline limit; use the NIM assets API")
                return "", []
            img_bytes, img_mime = shrunk
            b64 = base64.b64encode(img_bytes).decode()
            log.info("ocr.image_downscaled", b64_len=len(b64), limit=_NIM_IMAGE_SIZE_LIMIT, mime=img_mime)

        # CV API: model name in URL, "input" array (not chat messages format)
        url = f"{_NIM_CV_BASE}/{self.model}"
        payload = {
            "input": [
                {"type": "image_url", "url": f"data:{img_mime};base64,{b64}"}
            ]
        }

        try:
            client = shared_client(60.0)
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
            body = resp.json()
            # CV API response: {"data": [{"index": 0, "text_detections": [...]}]}
            detections = body.get("data", [{}])[0].get("text_detections", [])
            if not detections:
                # The model ran and saw no text. Distinct from the case below on purpose.
                log.info("ocr.no_detections", model=self.model)
                return "", []
            spans = [s for s in (self._detection_span(d) for d in detections) if s[0]]
            text = "\n".join(s[0] for s in spans).strip()
            if not text:
                # Detections came back but none yielded text — a schema mismatch, not a blank page.
                # This is the failure that hid the original bug: it used to be indistinguishable
                # from "no detections", so a response-key change read as a model limitation.
                log.error("ocr.detections_unparsed", model=self.model, detection_count=len(detections),
                          observed_keys=sorted({k for d in detections[:3] if isinstance(d, dict) for k in d}),
                          hint="text_detections present but no text field matched — CV schema changed?")
            return text, spans
        except httpx.HTTPStatusError as exc:
            log.error("ocr.nim_error", status=exc.response.status_code, body=exc.response.text[:200])
            return "", []
        except Exception as exc:
            log.error("ocr.nim_failed", error=str(exc))
            return "", []

    @staticmethod
    def _detection_text(detection: Any) -> str:
        """
        Pull the text out of one CV-API detection.

        The live response keys each detection `{"bounding_box": ..., "text_prediction": {"text": ...}}`.
        This used to read `label` or `text`, which the response has never carried, so every line
        resolved to "" and the caller reported `nim_returned_no_text` — read ever since as the
        documented "no handwriting model" limitation. It was a key name: the model transcribes the
        corpus's handwritten notes at 0.91 confidence. `label`/`text` stay as fallbacks so a future
        schema does not re-break this silently.
        """
        if not isinstance(detection, dict):
            return ""
        prediction = detection.get("text_prediction")
        if isinstance(prediction, dict) and prediction.get("text"):
            return str(prediction["text"])
        for key in ("label", "text"):
            if detection.get(key):
                return str(detection[key])
        return ""

    @classmethod
    def _detection_span(cls, detection: Any) -> tuple[str, float]:
        """
        One detection as (text, confidence).

        Confidence defaults to 0.0 when the response omits it, never to a flattering constant: an
        unknown confidence must not be able to lift a document over the quarantine threshold.
        """
        text = cls._detection_text(detection)
        confidence = 0.0
        if isinstance(detection, dict):
            prediction = detection.get("text_prediction")
            if isinstance(prediction, dict) and isinstance(prediction.get("confidence"), (int, float)):
                confidence = float(prediction["confidence"])
        return text, confidence

    @staticmethod
    def _shrink_for_inline(img_bytes: bytes) -> tuple[bytes, str] | None:
        """
        Re-encode an oversized image to fit the CV API's inline base64 ceiling.

        Thin wrapper around `image_utils.shrink_image_for_nim` — algorithm and
        constant now live there so OCR and PID share a single implementation.
        Returns raw (bytes, mime) because the CV API call in `_nim_ocr` passes
        bytes directly, unlike the VLM path which needs a b64 string.
        """
        return shrink_image_for_nim(img_bytes)

    def _extract_native_pdf(self, pdf_bytes: bytes) -> dict[str, Any]:
        try:
            import fitz
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            blocks = []
            for page_num, page in enumerate(doc):
                text = page.get_text().strip()
                if text:
                    blocks.append({
                        "text": text,
                        "confidence": 0.95,
                        "page": page_num + 1,
                        "extraction_method": "native_pdf",
                    })
            doc.close()
            full_text = "\n".join(b["text"] for b in blocks)
            return {
                "text": full_text,
                "blocks": blocks,
                "overall_confidence": 0.95 if blocks else 0.0,
                "requires_review": False,
                "block_count": len(blocks),
                "extraction_method": "native_pdf",
                # Text layer parsed straight out of the PDF — no image was read.
                "extraction_path": "native",
                "handwriting_suspect": False,
            }
        except Exception as exc:
            log.error("ocr.native_pdf_failed", error=str(exc))
            return {"text": "", "blocks": [], "overall_confidence": 0.0,
                    "requires_review": True, "block_count": 0, "extraction_method": "error",
                    "extraction_path": "unknown", "handwriting_suspect": False}

    def _native(self, text: str, method: str) -> dict[str, Any]:
        """Result envelope for extraction paths that need no OCR model."""
        return {
            "text": text,
            "blocks": [{"text": text, "confidence": 1.0, "page": 1, "extraction_method": method}],
            "overall_confidence": 1.0,
            "requires_review": False,
            "block_count": 1,
            "extraction_method": method,
            # Digital text — parsed, not read off an image. Handwriting cannot be present.
            "extraction_path": "native",
            "handwriting_suspect": False,
        }

    @staticmethod
    def _extract_spreadsheet(file_bytes: bytes) -> str:
        """
        Flattens every sheet to tab-separated rows, prefixed by sheet name.

        openpyxl rather than hand-rolling zip+XML: xlsx cell typing (dates stored as
        serial numbers, shared vs inline strings) is exactly the kind of silent
        corruption that must not reach the knowledge graph. read_only streams rows
        instead of loading the whole workbook.
        """
        try:
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        except Exception as exc:
            log.warning("ocr.spreadsheet_open_failed", error=str(exc))
            return ""

        lines: list[str] = []
        try:
            for sheet in wb.worksheets:
                rows = [
                    "\t".join("" if c is None else str(c) for c in row)
                    for row in sheet.iter_rows(values_only=True)
                ]
                rows = [r for r in rows if r.strip()]
                if rows:
                    lines.append(f"# Sheet: {sheet.title}")
                    lines.extend(rows)
        except Exception as exc:
            log.warning("ocr.spreadsheet_read_failed", error=str(exc))
        finally:
            wb.close()

        return "\n".join(lines).strip()

    @staticmethod
    def _extract_email(file_bytes: bytes) -> str:
        """
        Extracts headers + plaintext bodies from a .eml or .mbox archive.

        stdlib `email` only — no dependency needed. An mbox is concatenated messages
        separated by a line starting "From "; splitting on that is the format's own
        delimiter. Attachments are listed by filename, not decoded: their bytes belong
        in the vault as their own documents, not inlined into this one's text.
        """
        from email import message_from_bytes
        from email.message import Message

        raw = file_bytes.lstrip()
        # mbox: split on the "From " line that opens each message.
        chunks = [c for c in raw.split(b"\nFrom ") if c.strip()] if raw.startswith(b"From ") else [raw]

        def render(msg: Message) -> str:
            parts: list[str] = []
            for header in _EMAIL_HEADERS:
                value = msg.get(header)
                if value:
                    parts.append(f"{header}: {value}")

            attachments: list[str] = []
            for part in msg.walk() if msg.is_multipart() else [msg]:
                disposition = str(part.get("Content-Disposition") or "")
                if "attachment" in disposition:
                    name = part.get_filename()
                    if name:
                        attachments.append(name)
                    continue
                if part.get_content_type() == "text/plain":
                    try:
                        payload = part.get_payload(decode=True) or b""
                        body = payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
                    except Exception:
                        continue
                    if body:
                        parts.append("")
                        parts.append(body)

            if attachments:
                parts.append(f"\n[Attachments: {', '.join(attachments)}]")
            return "\n".join(parts).strip()

        rendered = []
        for i, chunk in enumerate(chunks):
            try:
                rendered.append(render(message_from_bytes(chunk if i == 0 else b"From " + chunk)))
            except Exception as exc:
                log.warning("ocr.email_parse_failed", index=i, error=str(exc))

        return "\n\n---\n\n".join(r for r in rendered if r).strip()

    def _to_images(self, file_bytes: bytes, mime_type: str) -> list[tuple]:
        """Returns list of (image_bytes, mime) — one per page for PDFs, one for images."""
        if mime_type == "application/pdf":
            try:
                import fitz
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                pages = []
                for page in doc:
                    # 96 DPI keeps base64 under the 180KB CV API inline limit for typical A4
                    pix = page.get_pixmap(dpi=96)
                    pages.append((pix.tobytes("png"), "image/png"))
                doc.close()
                return pages
            except Exception as exc:
                log.error("ocr.rasterize_failed", error=str(exc))
                return []
        else:
            return [(file_bytes, mime_type)]

    @staticmethod
    def _empty(reason: str) -> dict[str, Any]:
        return {
            "text": "",
            "blocks": [],
            "overall_confidence": 0.0,
            "requires_review": True,
            "block_count": 0,
            "extraction_method": "error",
            "error": reason,
            "extraction_path": "unknown",
            "handwriting_suspect": False,
        }

"""Service-free: NER's NIM concurrency cap, and skipping an unconfigured Ollama."""

import asyncio
import json

from api.services import ner as ner_mod
from api.services.ner import NERService


async def test_nim_calls_never_exceed_the_concurrency_cap(monkeypatch):
    active = peak = 0

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "[]"}}]}

    class FakeClient:
        async def post(self, *args, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return FakeResponse()

    monkeypatch.setattr(ner_mod, "shared_client", lambda *_: FakeClient())
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-key")
    svc = NERService()

    await asyncio.gather(*[svc._extract_via_nim("Seal failure on EQ-101") for _ in range(12)])

    assert peak == ner_mod._NIM_NER_CONCURRENCY


async def test_nim_timeout_is_retried_once_before_falling_back(monkeypatch):
    import httpx

    calls = 0

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '[{"text": "EQ-101", "type": "ASSET_TAG", "confidence": 0.9}]'}}]}

    class FlakyClient:
        async def post(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ReadTimeout("slow")
            return FakeResponse()

    monkeypatch.setattr(ner_mod, "shared_client", lambda *_: FlakyClient())
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-key")

    result = await NERService()._extract_via_nim("Seal failure on EQ-101")

    assert calls == 2
    assert result is not None


async def test_nim_5xx_is_retried_but_4xx_is_not(monkeypatch):
    import httpx

    def status_error(code):
        request = httpx.Request("POST", "https://nim.test")
        return httpx.HTTPStatusError("err", request=request, response=httpx.Response(code, request=request))

    ok = '[{"text": "EQ-101", "type": "ASSET_TAG", "confidence": 0.9}]'
    monkeypatch.setattr(ner_mod, "_NIM_NER_BACKOFF_S", 0)
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-key")

    for first_status, expected_calls, recovered in ((500, 2, True), (400, 1, False)):
        calls = 0

        class Client:
            async def post(self, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise status_error(first_status)

                class R:
                    def raise_for_status(self):
                        return None

                    def json(self):
                        return {"choices": [{"message": {"content": ok}}]}

                return R()

        monkeypatch.setattr(ner_mod, "shared_client", lambda *_: Client())
        result = await NERService()._extract_via_nim("Seal failure on EQ-101")

        assert calls == expected_calls, first_status
        assert (result is not None) is recovered, first_status


def _tagging_client(sent, fail_when=None):
    """Fake NIM that returns an ASSET_TAG for whichever made-up tag the chunk contains."""
    import httpx

    class Response:
        def __init__(self, content):
            self._content = content

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    class Client:
        async def post(self, *args, **kwargs):
            prompt = kwargs["json"]["messages"][0]["content"]
            sent.append(prompt)
            if fail_when and fail_when(prompt):
                request = httpx.Request("POST", "https://nim.test")
                raise httpx.HTTPStatusError("bad", request=request, response=httpx.Response(400, request=request))
            tags = [t for t in ("ZX-901", "QY-402") if t in prompt]
            return Response(json.dumps([{"text": t, "entity_type": "ASSET_TAG", "confidence": 0.9} for t in tags]))

    return Client()


# Regression: a dense 2,000-character document timed out on every attempt as one call, and the whole
# document fell to regex. Its halves answered quickly.
async def test_long_text_is_extracted_in_chunks_and_merged(monkeypatch):
    sent = []
    monkeypatch.setattr(ner_mod, "shared_client", lambda *_: _tagging_client(sent))
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-key")
    text = "Seal failure on ZX-901. " * 30 + "Tube fouling on QY-402. " * 30

    result = await NERService()._extract_via_nim(text)

    assert len(sent) >= 2
    assert {e["text"] for e in result["entities"]} == {"ZX-901", "QY-402"}
    assert result["parse_recovered"] is False


async def test_a_failed_chunk_keeps_the_others_and_flags_recall_as_a_floor(monkeypatch):
    sent = []
    only_second_tag = lambda prompt: "QY-402" in prompt and "ZX-901" not in prompt  # noqa: E731
    monkeypatch.setattr(ner_mod, "shared_client", lambda *_: _tagging_client(sent, fail_when=only_second_tag))
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-key")
    text = "Seal failure on ZX-901. " * 30 + "Tube fouling on QY-402. " * 30

    result = await NERService()._extract_via_nim(text)

    # The chunk holding only QY-402 fails; the chunks that reached ZX-901 still count.
    assert "ZX-901" in {e["text"] for e in result["entities"]}
    assert len(sent) >= 2
    assert result["parse_recovered"] is True


async def test_empty_ollama_url_goes_straight_to_regex(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "")
    monkeypatch.setenv("OLLAMA_BASE_URL", "")
    svc = NERService()

    async def must_not_run(_text):
        raise AssertionError("called an unconfigured Ollama")

    monkeypatch.setattr(svc, "_extract_via_ollama", must_not_run)

    result = await svc.extract_entities("Seal failure on EQ-101")

    assert any(e.get("text") == "EQ-101" for e in result.get("entities", []))

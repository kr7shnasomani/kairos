"""Service-free: a transient NIM 5xx is retried once before the cascade falls to another model."""

from types import SimpleNamespace

import httpx

from api.services import llm as llm_mod
from api.services.llm import LLMService

_URL = "https://nim.test/v1/chat/completions"


def _response(status: int) -> httpx.Response:
    body = {"model": "nvidia/nemotron-3-super-120b-a12b", "choices": [{"message": {"content": "ANSWER: ok"}}]}
    return httpx.Response(status, json=body if status == 200 else {}, request=httpx.Request("POST", _URL))


def _service(monkeypatch, statuses: list[int]):
    calls = []

    class FakeClient:
        async def post(self, *args, **kwargs):
            calls.append(kwargs)
            return _response(statuses[len(calls) - 1])

    monkeypatch.setattr(llm_mod, "shared_client", lambda *_: FakeClient())
    monkeypatch.setattr(llm_mod, "_NIM_RETRY_DELAY_S", 0)
    svc = LLMService.__new__(LLMService)
    svc.settings = SimpleNamespace(
        NVIDIA_NIM_TIMEOUT=60, NVIDIA_NIM_BASE_URL="https://nim.test/v1", NVIDIA_NIM_API_KEY="k",
        NVIDIA_NIM_MODEL="nvidia/nemotron-3-super-120b-a12b", NVIDIA_NIM_MAX_TOKENS=512,
        NVIDIA_NIM_TEMPERATURE=0.1, NVIDIA_NIM_DISABLE_THINKING=True,
    )
    return svc, calls


async def test_a_503_is_retried_and_the_pinned_model_answers(monkeypatch):
    svc, calls = _service(monkeypatch, [503, 200])

    result = await svc._synthesize_nim("q", [])

    assert len(calls) == 2
    assert result["model"] == "nim" and result["answer"] == "ANSWER: ok"


async def test_a_client_error_is_not_retried(monkeypatch):
    svc, calls = _service(monkeypatch, [400])

    result = await svc._synthesize_nim("q", [])

    assert len(calls) == 1
    assert result["answer"] is None and result["failed_provider"] == "nim"


async def test_a_second_503_gives_up_so_the_cascade_can_fall_through(monkeypatch):
    svc, calls = _service(monkeypatch, [503, 503])

    result = await svc._synthesize_nim("q", [])

    assert len(calls) == 2
    assert result["answer"] is None and result["failed_provider"] == "nim"

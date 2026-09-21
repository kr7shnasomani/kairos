"""Service-free: the shared provider call path, and the registry that feeds it.

Filename kept as `test_nim_retry` because CI's service-free job lists test files by name; the
retry behaviour it was written for now belongs to every OpenAI-compatible tier, not just NIM.
"""

from types import SimpleNamespace

import httpx

from api.services import llm as llm_mod
from api.services.llm import LLMService
from api.services.model_providers import Provider, all_tiers, synthesis_cascade

_PROVIDER = Provider(name="nim", base_url="https://nim.test/v1", api_key="k",
                     model="nvidia/nemotron-3-super-120b-a12b", timeout=60.0,
                     extra_body={"chat_template_kwargs": {"enable_thinking": False}})


def _response(status: int) -> httpx.Response:
    body = {"model": "nvidia/nemotron-3-super-120b-a12b", "choices": [{"message": {"content": "ANSWER: ok"}}]}
    return httpx.Response(status, json=body if status == 200 else {},
                          request=httpx.Request("POST", _PROVIDER.chat_url))


def _service(monkeypatch, statuses: list[int]):
    calls = []

    class FakeClient:
        async def post(self, *args, **kwargs):
            calls.append(kwargs)
            return _response(statuses[len(calls) - 1])

    monkeypatch.setattr(llm_mod, "shared_client", lambda *_: FakeClient())
    monkeypatch.setattr(llm_mod, "_RETRY_DELAY_S", 0)
    svc = LLMService.__new__(LLMService)
    svc.settings = SimpleNamespace(NVIDIA_NIM_MAX_TOKENS=512, NVIDIA_NIM_TEMPERATURE=0.1)
    return svc, calls


# --- the retry, which every tier now shares ----------------------------------------

async def test_a_503_is_retried_and_the_pinned_model_answers(monkeypatch):
    svc, calls = _service(monkeypatch, [503, 200])

    result = await svc._synthesize_provider(_PROVIDER, "q", [])

    assert len(calls) == 2
    assert result["model"] == "nim" and result["answer"] == "ANSWER: ok"


async def test_a_client_error_is_not_retried(monkeypatch):
    svc, calls = _service(monkeypatch, [400])

    result = await svc._synthesize_provider(_PROVIDER, "q", [])

    assert len(calls) == 1
    assert result["answer"] is None and result["failed_provider"] == "nim"


async def test_a_second_503_gives_up_so_the_cascade_can_fall_through(monkeypatch):
    svc, calls = _service(monkeypatch, [503, 503])

    result = await svc._synthesize_provider(_PROVIDER, "q", [])

    assert len(calls) == 2
    assert result["answer"] is None and result["failed_provider"] == "nim"


async def test_the_body_carries_the_tier_model_and_its_own_extra_keys(monkeypatch):
    """Two regressions in one: a tier must post its *own* model id, and provider-specific body
    keys must not leak to tiers that would reject them."""
    svc, calls = _service(monkeypatch, [200])
    plain = Provider(name="openrouter", base_url="https://or.test/v1", api_key="k",
                     model="meta-llama/llama-3.1-70b-instruct", timeout=60.0)

    await svc._synthesize_provider(_PROVIDER, "q", [])
    await svc._synthesize_provider(plain, "q", [])

    nemotron_body, plain_body = calls[0]["json"], calls[1]["json"]
    assert nemotron_body["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert nemotron_body["chat_template_kwargs"] == {"enable_thinking": False}
    assert plain_body["model"] == "meta-llama/llama-3.1-70b-instruct"
    assert "chat_template_kwargs" not in plain_body


# --- the registry ------------------------------------------------------------------

def _settings(**keys) -> SimpleNamespace:
    base = dict(
        NEBIUS_TOKEN_FACTORY_API_KEY="", NEBIUS_TOKEN_FACTORY_BASE_URL="https://tf.test/v1",
        NEBIUS_TOKEN_FACTORY_MODEL="nvidia/nemotron-3-super-120b-a12b", NEBIUS_TOKEN_FACTORY_TIMEOUT=60.0,
        NEBIUS_TOKEN_FACTORY_DISABLE_THINKING=True,
        NVIDIA_NIM_API_KEY="", NVIDIA_NIM_BASE_URL="https://nim.test/v1",
        NVIDIA_NIM_MODEL="nvidia/nemotron-3-super-120b-a12b", NVIDIA_NIM_TIMEOUT=60.0,
        NVIDIA_NIM_DISABLE_THINKING=True,
        OPENROUTER_API_KEY="", OPENROUTER_BASE_URL="https://or.test/v1",
        OPENROUTER_MODEL="meta-llama/llama-3.1-70b-instruct", OPENROUTER_TIMEOUT=60.0,
        GEMINI_API_KEY="", GEMINI_BASE_URL="https://gem.test/v1", GEMINI_MODEL="gemini-2.5-flash-lite",
    )
    base.update(keys)
    return SimpleNamespace(**base)


def test_an_unkeyed_tier_is_not_in_the_cascade_at_all():
    """The property the whole registry rests on: adding a tier cannot change the behaviour of a
    deployment that has not configured it."""
    assert synthesis_cascade(_settings()) == []
    nim_only = synthesis_cascade(_settings(NVIDIA_NIM_API_KEY="k"))
    assert [p.name for p in nim_only] == ["nim"]


def test_token_factory_takes_tier_one_when_configured():
    cascade = synthesis_cascade(_settings(NEBIUS_TOKEN_FACTORY_API_KEY="k", NVIDIA_NIM_API_KEY="k",
                                          GEMINI_API_KEY="k"))
    assert [p.name for p in cascade] == ["tokenfactory", "nim", "gemini"]


def test_thinking_off_reaches_both_nemotron_tiers_and_no_others():
    cascade = synthesis_cascade(_settings(NEBIUS_TOKEN_FACTORY_API_KEY="k", NVIDIA_NIM_API_KEY="k",
                                          OPENROUTER_API_KEY="k"))
    by_name = {p.name: p for p in cascade}
    assert by_name["tokenfactory"].extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert by_name["nim"].extra_body == by_name["tokenfactory"].extra_body
    assert by_name["openrouter"].extra_body == {}


def test_token_factory_thinking_switch_is_independent_of_nim():
    """If Token Factory rejects the flag, turning it off there must not change the NIM tier."""
    cascade = synthesis_cascade(_settings(NEBIUS_TOKEN_FACTORY_API_KEY="k", NVIDIA_NIM_API_KEY="k",
                                          NEBIUS_TOKEN_FACTORY_DISABLE_THINKING=False))
    by_name = {p.name: p for p in cascade}
    assert by_name["tokenfactory"].extra_body == {}
    assert by_name["nim"].extra_body == {"chat_template_kwargs": {"enable_thinking": False}}


def test_all_tiers_lists_unkeyed_tiers_so_the_probe_can_say_not_configured():
    """The health probe looks names up here; an unkeyed tier must be found (and reported as not
    configured) rather than missing (and reported as an unknown provider)."""
    tiers = all_tiers(_settings(NVIDIA_NIM_API_KEY="k"))
    assert [p.name for p in tiers] == ["tokenfactory", "nim", "openrouter", "gemini"]
    assert [p.name for p in tiers if p.api_key] == ["nim"]


async def test_the_cascade_skips_a_tier_that_already_failed_this_request(monkeypatch):
    svc = LLMService.__new__(LLMService)
    svc.settings = SimpleNamespace(OLLAMA_BASE_URL="")
    tiers = [Provider(name=n, base_url="https://x.test/v1", api_key="k", model=n, timeout=5.0)
             for n in ("tokenfactory", "nim")]
    monkeypatch.setattr(LLMService, "providers", property(lambda self: tiers))
    called = []

    async def _answer(provider, prompt, context):
        called.append(provider.name)
        return {"answer": "ANSWER: ok", "sources": context, "model": provider.name}

    monkeypatch.setattr(svc, "_synthesize_provider", _answer)

    result = await svc._synthesize_cascade("q", [], skip="tokenfactory")

    assert called == ["nim"] and result["model"] == "nim"

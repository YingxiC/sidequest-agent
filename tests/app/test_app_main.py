"""Server tests with the model mocked out (no GCP needed)."""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("litellm")

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402


class FakeMessage(SimpleNamespace):
    def model_dump(self):
        calls = [{"id": c.id, "type": "function",
                  "function": {"name": c.function.name, "arguments": c.function.arguments}}
                 for c in self.tool_calls or []]
        return {"role": "assistant", "content": self.content, "tool_calls": calls or None}


def tool_call(name, args, call_id="c1"):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def script(monkeypatch, replies):
    """Make litellm.completion return `replies` in order."""
    it = iter(replies)
    seen = []

    def fake_completion(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=next(it))])

    monkeypatch.setattr(main.litellm, "completion", fake_completion)
    return seen


@pytest.fixture
def client():
    main.sessions.clear()
    return TestClient(main.app)


def test_index_and_status(client):
    assert "Day as Someone" in client.get("/").text
    feats = {f["id"]: f for f in client.get("/api/status").json()["features"]}
    assert feats["repair"]["available"] and feats["weather"]["available"]
    assert feats["places"]["available"]  # Reality's match_theme is registered
    assert not feats["plan"]["available"]
    assert feats["plan"]["missing_tools"] == ["build_sidequest"]


def test_system_prompt_mentions_missing_features():
    prompt = main.build_system_prompt()
    assert "Not available yet" in prompt and "Build the full SideQuest" in prompt
    assert "match_theme" in prompt


def test_demo_then_repair_through_chat(client, monkeypatch):
    sid = "s-demo"
    demo = client.post("/api/demo", json={"session_id": sid}).json()
    assert demo["ok"] and demo["sidequest"]["version"] == 1

    seen = script(monkeypatch, [
        FakeMessage(content=None, tool_calls=[
            tool_call("repair_sidequest", {"unavailable_stops": ["gallery"], "bad_weather": True})]),
        FakeMessage(content="Fixed chapters 2 and 3.", tool_calls=None),
    ])
    body = client.post("/chat", json={"message": "The gallery is closed and it's raining.",
                                      "session_id": sid}).json()

    # Starter response shape is kept.
    assert set(body) == {"response", "session_id", "tool_calls"}
    assert body["response"] == "Fixed chapters 2 and 3." and body["session_id"] == sid
    call = body["tool_calls"][0]
    assert call["name"] == "repair_sidequest" and json.loads(call["result"])["ok"]
    assert seen[0]["tools"] == main.TOOLS

    quest = client.get("/api/sidequest", params={"session_id": sid}).json()
    assert quest["sidequest"]["version"] == 2

    undone = client.post("/api/undo", json={"session_id": sid}).json()
    assert undone["ok"] and undone["sidequest"]["version"] == 1
    assert not client.post("/api/undo", json={"session_id": sid}).json()["ok"]


def test_bad_tool_arguments_reach_model_not_crash(client, monkeypatch):
    bad = SimpleNamespace(id="c1", function=SimpleNamespace(name="get_weather", arguments="{not json"))
    script(monkeypatch, [FakeMessage(content=None, tool_calls=[bad]),
                         FakeMessage(content="Sorry!", tool_calls=None)])
    body = client.post("/chat", json={"message": "weather?"}).json()
    assert body["response"] == "Sorry!"
    assert "not valid JSON" in body["tool_calls"][0]["result"]


def test_model_failure_is_shown_in_chat(client, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("no credentials")
    monkeypatch.setattr(main.litellm, "completion", boom)
    body = client.post("/chat", json={"message": "hi"}).json()
    assert body["response"].startswith("Model call failed") and body["tool_calls"] == []


def test_clear_forgets_quest(client):
    client.post("/api/demo", json={"session_id": "gone"})
    client.post("/clear", params={"session_id": "gone"})
    assert not client.get("/api/sidequest", params={"session_id": "gone"}).json()["ok"]

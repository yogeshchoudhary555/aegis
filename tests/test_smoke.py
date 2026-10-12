"""AEGIS smoke tests — every module's code path, no live keys needed."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from llm import ChatResult, MockProvider  # noqa: E402
import arena  # noqa: E402
import forge  # noqa: E402
import recon  # noqa: E402
import router as router_mod  # noqa: E402


class StubProvider:
    """Deterministic stub: returns canned JSON/text per call type."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        user = ""
        system = ""
        for m in messages:
            if m.get("role") == "user":
                user = m.get("content", "")
            if m.get("role") == "system":
                system = m.get("content", "")
        if "tournament judge" in system:
            return ChatResult(text='{"a": 8, "b": 6, "winner": "a", "reason": "more specific"}')
        if "software analyst" in system:
            return ChatResult(text="ANALYSIS: test site does X. Evidence-based bullets.")
        if "software architect" in system:
            plan = {
                "project_name": "test-app",
                "stack": "single HTML file",
                "files": [
                    {"path": "index.html", "content": "<html><body>hi</body></html>"}
                ],
            }
            return ChatResult(text=json.dumps(plan))
        return ChatResult(text=f"stub solution #{self.calls}")


class FailingProvider:
    def chat(self, messages, tools=None):
        raise RuntimeError("simulated outage")


def test_router_failover():
    r = router_mod.SmartRouter([("bad", FailingProvider()), ("mock", MockProvider())])
    res = r.chat([{"role": "user", "content": "hello"}])
    assert res is not None
    stats = r.stats()
    assert stats["total_calls"] == 2
    assert stats["failed"] == 1
    assert stats["successful"] == 1
    assert stats["failovers"] == {"bad": 1}
    print("router failover: OK")


def test_router_all_fail():
    r = router_mod.SmartRouter([("bad1", FailingProvider()), ("bad2", FailingProvider())])
    try:
        r.chat([{"role": "user", "content": "hi"}])
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "all providers failed" in str(e)
    print("router all-fail: OK")


def test_arena_tournament():
    stub = StubProvider()
    result = arena.run_arena("write a haiku about rust", stub, agents=4, seed=42)
    assert result["agents"] == 4
    assert len(result["rounds"]) == 2  # 4 -> 2 -> 1
    champ = result["champion"]
    assert champ["wins"] == 2
    assert "stub solution" in champ["solution"]
    assert set(champ["strategy_card"].keys()) == {"reasoning", "workflow", "tactic"}
    print("arena tournament: OK")


def test_arena_deck_no_repeats():
    cards = arena.deal_cards(50, seed=7)
    seen = {(c["reasoning"], c["workflow"], c["tactic"]) for c in cards}
    assert len(seen) == 50
    print("arena deck: OK")


def test_forge_sandbox():
    stub = StubProvider()
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "proj")
        result = forge.build("a test app", stub, out)
        assert result["project_name"] == "test-app"
        assert "index.html" in result["files"]
        assert "README.md" in result["files"]
        assert os.path.isfile(os.path.join(out, "index.html"))
    # traversal is neutralized (stripped), never escapes
    neutralized = forge._safe_path("/tmp/x", "../../etc/passwd")
    assert neutralized == "/tmp/x/etc/passwd", neutralized
    assert neutralized.startswith("/tmp/x" + os.sep)
    print("forge sandbox: OK")


def test_recon_structure_parser():
    html = (
        "<html><head><title>TestCo</title>"
        '<meta name="description" content="We sell tests">'
        '<meta name="generator" content="TestPress">'
        "</head><body><h1>Welcome</h1>"
        '<form action="/signup" method="post"><input name="email"></form>'
        "</body></html>"
    )
    p = recon._StructureParser()
    p.feed(html)
    assert p.title == "TestCo"
    assert p.meta["description"] == "We sell tests"
    assert p.forms[0]["action"] == "/signup"
    hints = recon._guess_stack([], p.meta, {})
    assert any("TestPress" in h for h in hints)
    print("recon parser: OK")


def test_recon_analyze_with_stub():
    # stub the fetch to avoid network
    orig = recon.fetch_structure
    recon.fetch_structure = lambda url, timeout=15: {
        "url": url, "final_url": url, "status": 200, "title": "T",
        "meta_description": "D", "headings": ["H"], "scripts": [],
        "forms": [], "tech_hints": ["X"], "html_bytes": 10,
    }
    try:
        out = recon.analyze("https://example.com", StubProvider())
        assert "ANALYSIS" in out["analysis"]
        assert "disclaimer" in out and "Read-only" in out["disclaimer"]
    finally:
        recon.fetch_structure = orig
    print("recon analyze: OK")


def test_mock_provider_chat():
    m = MockProvider()
    res = m.chat([{"role": "user", "content": "hello there"}])
    assert isinstance(res.text, str)
    print("mock provider: OK")


if __name__ == "__main__":
    test_router_failover()
    test_router_all_fail()
    test_arena_tournament()
    test_arena_deck_no_repeats()
    test_forge_sandbox()
    test_recon_structure_parser()
    test_recon_analyze_with_stub()
    test_mock_provider_chat()
    print("\nALL SMOKE TESTS PASSED")

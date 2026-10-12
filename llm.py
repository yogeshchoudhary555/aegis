"""Pluggable LLM backend.

- NebiusProvider: NVIDIA Nemotron via Nebius Token Factory (OpenAI-compatible).
- MockProvider:   offline stand-in that simulates tool-calling so the whole
                  app (agent loop + tools + UI) works end-to-end with no keys.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    name: str
    arguments: dict
    id: str = ""


@dataclass
class ChatResult:
    text: str = ""
    tool_calls: list = field(default_factory=list)


class LLMProvider:
    def chat(self, messages, tools=None) -> ChatResult:
        raise NotImplementedError


class NebiusProvider(LLMProvider):
    """NVIDIA Nemotron served by Nebius Token Factory (OpenAI-compatible)."""

    def __init__(self, api_key: str, base_url: str, model: str):
        from openai import OpenAI  # lazy: mock path needs no openai package

        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def chat(self, messages, tools=None) -> ChatResult:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        # Nemotron reasoning models may put the answer in `reasoning` /
        # `reasoning_content` with message.content empty — fall back gracefully.
        raw = msg.model_dump() if hasattr(msg, "model_dump") else {}
        text = (
            msg.content
            or getattr(msg, "reasoning_content", "")
            or raw.get("reasoning", "")
            or ""
        )
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(
                ToolCall(name=tc.function.name, arguments=args, id=tc.id or "")
            )
        return ChatResult(text=text, tool_calls=calls)


class MockProvider(LLMProvider):
    """Rule-based offline stand-in. Demonstrates the tool loop without any key."""

    MEMORY_STORE_HINTS = (
        "remember that",
        "remember my",
        "please remember",
        "my name is ",
        "i live in ",
        "i prefer ",
    )

    def chat(self, messages, tools=None) -> ChatResult:
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break
        low = user_text.lower()
        tool_results = [m for m in messages if m.get("role") == "tool"]
        has_search = any(m.get("name") == "tavily_search" for m in tool_results)
        brief_intent = "brief" in low and not any(
            h in low for h in self.MEMORY_STORE_HINTS
        )

        if not tool_results:
            # Explicit memory intents win over every other keyword match.
            if any(h in low for h in self.MEMORY_STORE_HINTS):
                calls = [
                    ToolCall("memory_write", {"key": k, "value": v})
                    for k, v in self._extract_facts(user_text)
                ]
                return ChatResult(tool_calls=calls)
            if "remember" in low and any(
                q in low for q in ("what do", "do you", "show me", "list")
            ):
                return ChatResult(tool_calls=[ToolCall("memory_read", {})])
            if brief_intent:
                return ChatResult(tool_calls=[ToolCall("memory_read", {})])
            if any(
                w in low
                for w in ("rent", "flat", "rental", "bhk", "dealer", "listing")
            ):
                return ChatResult(
                    tool_calls=[
                        ToolCall(
                            "tavily_search",
                            {
                                "query": "2 BHK flat for rent Sri Ganganagar H Block family",
                                "max_results": 5,
                            },
                        )
                    ]
                )
            if any(w in low for w in ("news", "headline")):
                return ChatResult(
                    tool_calls=[
                        ToolCall(
                            "tavily_search",
                            {"query": "top news headlines today", "max_results": 5},
                        )
                    ]
                )
            return ChatResult(text=self._smalltalk(user_text))

        if brief_intent and not has_search:
            return ChatResult(
                tool_calls=[
                    ToolCall(
                        "tavily_search",
                        {"query": "top news India today", "max_results": 5},
                    )
                ]
            )
        rental_kw = any(
            w in low for w in ("rent", "flat", "rental", "bhk", "dealer", "listing")
        )
        already_asked = any(
            m.get("name") == "request_approval" for m in tool_results
        )
        if rental_kw and has_search and not already_asked:
            # Consequential beat: draft the dealer message, then PAUSE for
            # user approval instead of printing it as done.
            return ChatResult(
                tool_calls=[
                    ToolCall(
                        "request_approval",
                        {
                            "action_type": "message",
                            "draft_text": self._draft_dealer_message(
                                user_text, tool_results
                            ),
                            "recipient": "property dealer",
                        },
                    )
                ]
            )
        return ChatResult(
            text=self._compose_from_tools(user_text, tool_results, brief_intent)
        )

    # -- helpers -----------------------------------------------------------
    def _extract_facts(self, text: str):
        """Pull every durable fact out of a memory-store message."""
        low = text.lower()
        facts = []
        m = re.search(r"my name is (.+?)(?: and |$)", low)
        if m:
            facts.append(
                ("name", " ".join(m.group(1).strip().split()[:2]).title())
            )
        m = re.search(r"i live in (.+?)(?: and |$)", low)
        if m:
            facts.append(
                ("location", " ".join(m.group(1).strip().split()[:3]).title())
            )
        m = re.search(r"i prefer (.+?)(?: and |$)", low)
        if m:
            facts.append(("preference", m.group(1).strip()))
        if not facts:
            m = re.search(r"remember (?:that |my )?(.+)", text, re.IGNORECASE)
            if m:
                facts.append(("note", m.group(1).strip().rstrip(".")))
        return facts or [("note", text.strip())]

    def _draft_dealer_message(self, user_text, tool_results):
        """Build a WhatsApp-ready dealer outreach draft from search results."""
        listing_hint = "your 2 BHK listing"
        for m in tool_results:
            if m.get("name") != "tavily_search":
                continue
            try:
                data = json.loads(m.get("content", "{}"))
            except json.JSONDecodeError:
                data = {}
            results = data.get("results") or []
            if results:
                title = (results[0].get("title") or "").strip()
                if title:
                    listing_hint = f"your listing ({title[:60]})"
                break
        name = "Yogesh"
        for m in tool_results:
            if m.get("name") == "memory_read":
                try:
                    facts = json.loads(m.get("content", "[]"))
                    for f in facts:
                        if f.get("key") == "name":
                            name = f.get("value") or name
                except (json.JSONDecodeError, AttributeError):
                    pass
        return (
            f"Namaste! I came across {listing_hint} near H Block, Sri Ganganagar. "
            "Is it still available for a family? We're looking under ₹10,000/month "
            f"and would love a visit this weekend if possible. — {name}"
        )

    def _smalltalk(self, text: str) -> str:
        return (
            "I'm Chief of Staff (offline demo mode). I can search the web, "
            "remember your facts across sessions, and generate a morning "
            "briefing. Try: 'remember my name is Yogesh', "
            "'find 2 BHK rentals under 10000 near H Block Ganganagar', "
            "or 'give me my morning briefing'."
        )

    def _compose_from_tools(self, user_text, tool_results, brief_intent=False):
        lines = []
        for m in tool_results:
            name = m.get("name", "")
            try:
                data = json.loads(m.get("content", "{}"))
            except json.JSONDecodeError:
                data = {}
            if name == "memory_write":
                lines.append(
                    f"Saved to memory: {data.get('key', '')} = "
                    f"'{data.get('value', '')}'. I'll remember this next session."
                )
            elif name == "memory_read":
                facts = data if isinstance(data, list) else []
                if facts:
                    lines.append(
                        "From memory: "
                        + "; ".join(
                            f"{f['key']}={f['value']}" for f in facts[:8]
                        )
                    )
                else:
                    lines.append("Memory is empty — nothing remembered yet.")
            elif name == "tavily_search":
                results = data.get("results", []) if isinstance(data, dict) else []
                if results:
                    lines.append("Web results:")
                    for r in results[:5]:
                        lines.append(f"- {r.get('title','')} — {r.get('url','')}")
                else:
                    note = data.get("note") or data.get("error") or "no results"
                    lines.append(f"Web search: {note} (offline demo mode).")
        if brief_intent:
            head = "Good morning! Here's your briefing (offline demo):"
        else:
            head = "Here's what I found:"
        return head + "\n" + "\n".join(lines)


def build_provider():
    """Pick backend: vault Nebius credential > env key > offline mock."""
    import config

    if _vault_nebius_available():
        return VaultNebiusProvider(
            base_url=config.NEBIUS_BASE_URL,
            model=config.NEMOTRON_MODEL,
        )
    if config.active_provider() == "nebius":
        return NebiusProvider(
            api_key=config.NEBIUS_API_KEY,
            base_url=config.NEBIUS_BASE_URL,
            model=config.NEMOTRON_MODEL,
        )
    return MockProvider()


def _vault_nebius_available() -> bool:
    """True when the stored custom.nebius credential can be exchanged."""
    try:
        import sys

        sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
        from dynamic_credentials import dynamic_credential_entry

        entry = dynamic_credential_entry("custom.nebius", "access_token")
        return bool(entry.get("surrogate"))
    except Exception:
        return False


class VaultNebiusProvider(LLMProvider):
    """Nemotron via Nebius Token Factory using the vault-stored credential.

    Uses the dynamic-credentials surrogate exchange (urllib) so the raw key
    never appears in env vars, files, or logs. OpenAI-compatible JSON,
    including tool calling.
    """

    def __init__(self, base_url: str, model: str):
        import sys

        sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
        from dynamic_credentials import add_surrogate_to_request  # noqa: F401

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.allowed_hosts = ("api.tokenfactory.nebius.com",)

    def chat(self, messages, tools=None) -> ChatResult:
        import json as _json
        import sys
        import urllib.request

        sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
        from dynamic_credentials import (
            add_surrogate_to_request,
            read_json_response,
        )

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=_json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        add_surrogate_to_request(
            req,
            "custom.nebius",
            entry_name="access_token",
            allowed_hosts=self.allowed_hosts,
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = read_json_response(resp)
        msg = data["choices"][0]["message"]
        text = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or ""
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                args = _json.loads(fn.get("arguments") or "{}")
            except _json.JSONDecodeError:
                args = {}
            calls.append(
                ToolCall(name=fn.get("name", ""), arguments=args, id=tc.get("id") or "")
            )
        return ChatResult(text=text, tool_calls=calls)

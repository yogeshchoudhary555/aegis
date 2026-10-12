"""AEGIS SmartRouter — inspired by the free-token aggregator idea.

One interface, many backends. The router tries providers in priority order,
fails over automatically on errors/rate limits, and tracks usage per
provider so you always know what each request cost.

This is a simplified, honest version of the "aggregate every free tier
behind one endpoint" pattern: instead of claiming dozens of providers,
it routes between the configured live backend (Nebius Token Factory)
and the offline mock, with per-request usage accounting.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class UsageRecord:
    provider: str
    model: str
    started_at: float
    latency_s: float = 0.0
    ok: bool = True
    error: str = ""


class SmartRouter:
    """Routes chat() calls across providers with failover + usage tracking."""

    def __init__(self, providers):
        """providers: ordered list of (name, provider_instance). First = primary."""
        if not providers:
            raise ValueError("SmartRouter needs at least one provider")
        self.providers = list(providers)
        self.usage: list[UsageRecord] = []
        self._failover_counts: dict[str, int] = {}

    @property
    def primary(self) -> str:
        return self.providers[0][0]

    def chat(self, messages, tools=None):
        """Try each provider in order; fail over on exception. Records usage."""
        last_error = None
        for name, provider in self.providers:
            rec = UsageRecord(
                provider=name,
                model=getattr(provider, "model", "mock"),
                started_at=time.time(),
            )
            try:
                result = provider.chat(messages, tools=tools)
                rec.latency_s = time.time() - rec.started_at
                rec.ok = True
                self.usage.append(rec)
                return result
            except Exception as e:  # noqa: BLE001 — failover must be total
                rec.latency_s = time.time() - rec.started_at
                rec.ok = False
                rec.error = f"{type(e).__name__}: {e}"[:200]
                self.usage.append(rec)
                self._failover_counts[name] = self._failover_counts.get(name, 0) + 1
                last_error = e
                continue
        raise RuntimeError(f"all providers failed; last error: {last_error}")

    def stats(self) -> dict:
        total = len(self.usage)
        ok = sum(1 for u in self.usage if u.ok)
        by_provider: dict[str, dict] = {}
        for u in self.usage:
            d = by_provider.setdefault(u.provider, {"calls": 0, "ok": 0, "avg_latency_s": 0.0})
            d["calls"] += 1
            d["ok"] += 1 if u.ok else 0
            d["avg_latency_s"] += u.latency_s
        for d in by_provider.values():
            if d["calls"]:
                d["avg_latency_s"] = round(d["avg_latency_s"] / d["calls"], 3)
        return {
            "total_calls": total,
            "successful": ok,
            "failed": total - ok,
            "failovers": dict(self._failover_counts),
            "by_provider": by_provider,
        }


def build_router(config, llm_module):
    """Build the default router: Nebius live first, mock fallback.

    Mirrors the app's provider selection: live when a Nebius key exists,
    otherwise the mock carries every call (still tracked).
    """
    providers = []
    if config.active_provider() == "nebius":
        providers.append(("nebius", llm_module.NebiusProvider(
            api_key=config.NEBIUS_API_KEY,
            base_url=config.NEBIUS_BASE_URL,
            model=config.NEMOTRON_MODEL,
        )))
    # Mock is always the last resort so the app never hard-fails.
    providers.append(("mock", llm_module.MockProvider()))
    return SmartRouter(providers)

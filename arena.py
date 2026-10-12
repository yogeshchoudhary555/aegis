"""AEGIS Arena — inspired by the "100 sub-agents fight to the death" idea.

When an answer has to be *great* — not just first — the Arena spawns N
competitors, each attacking the same task with a different strategy card
(reasoning mode × workflow × tactic). They pair off in a single-elimination
bracket: each match, both solutions are critiqued and a judge scores them
against a written rubric. Losers are eliminated. One solution survives.

Original implementation of the tournament concept: strategy deck,
bracket state machine, and judging rubric are our own. No code is copied
from any other project.
"""
from __future__ import annotations

import itertools
import json
import random


# -- strategy deck -----------------------------------------------------------
# Each card = (reasoning mode, workflow, tactic). The deck is dealt without
# replacement so every competitor truly attacks the task differently.
REASONING_MODES = [
    "first-principles",
    "analogical",
    "adversarial",
    "systems-thinking",
    "empirical",
    "minimalist",
]

WORKFLOWS = [
    "decompose-then-synthesize",
    "draft-critique-rewrite",
    "evidence-first",
    "constraint-driven",
    "example-anchored",
    "inversion",
]

TACTICS = [
    "steelman-opposing-views",
    "quantify-everything",
    "optimize-for-actionability",
    "hunt-edge-cases",
    "prefer-simple",
    "maximize-specificity",
]


def deal_cards(n: int, seed: int | None = None) -> list[dict]:
    """Deal n unique strategy cards (no repeats)."""
    rng = random.Random(seed)
    deck = [
        {"reasoning": r, "workflow": w, "tactic": t}
        for r in REASONING_MODES
        for w in WORKFLOWS
        for t in TACTICS
    ]
    rng.shuffle(deck)
    return deck[:n]


JUDGE_RUBRIC = """Score each solution 0-10 on:
- Correctness (does it actually solve the task?): 0-4
- Specificity (concrete, not vague?): 0-3
- Usefulness (can the user act on it now?): 0-3
Reply with ONLY a JSON object: {"a": <0-10>, "b": <0-10>, "winner": "a"|"b", "reason": "<one line>"}"""


def _chat(provider, system: str, user: str) -> str:
    res = provider.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    return (res.text or "").strip()


def _compete(provider, task: str, card: dict, seed: int) -> str:
    system = (
        "You are a problem-solving competitor in a tournament. "
        f"Your strategy card: reasoning={card['reasoning']}, "
        f"workflow={card['workflow']}, tactic={card['tactic']}. "
        "Follow your card strictly. Be concrete and decisive."
    )
    return _chat(provider, system, f"Task: {task}\n\nSolve it now, following your strategy card.")


def _judge(provider, task: str, a: str, b: str) -> dict:
    system = "You are an impartial tournament judge. " + JUDGE_RUBRIC
    user = f"Task: {task}\n\n--- Solution A ---\n{a[:3000]}\n\n--- Solution B ---\n{b[:3000]}"
    raw = _chat(provider, system, user)
    try:
        # tolerate prose around the JSON
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        if data.get("winner") not in ("a", "b"):
            data["winner"] = "a" if data.get("a", 0) >= data.get("b", 0) else "b"
        return data
    except Exception:
        return {"a": 5, "b": 5, "winner": "a", "reason": "judge output unparseable; defaulted"}


def run_arena(
    task: str,
    provider,
    agents: int = 8,
    seed: int | None = None,
    quick: bool = False,
) -> dict:
    """Run a single-elimination tournament. Returns the surviving solution.

    agents: competitors (default 8; use 4 for speed). Must be a power of 2
    for a clean bracket; anything else is padded with byes.
    """
    if quick:
        agents = 4
    agents = max(2, agents)
    # round up to power of 2
    size = 1
    while size < agents:
        size *= 2

    cards = deal_cards(size, seed)
    rng = random.Random(seed)
    competitors = []
    for i in range(size):
        if i < agents:
            solution = _compete(provider, task, cards[i], seed or 0)
            competitors.append({"id": i, "card": cards[i], "solution": solution, "wins": 0})
        else:
            competitors.append(None)  # bye
    rng.shuffle(competitors)

    rounds = []
    round_no = 1
    alive = [c for c in competitors if c is not None]
    # byes advance automatically when odd
    while len(alive) > 1:
        matches = []
        nxt = []
        it = iter(alive)
        for a in it:
            try:
                b = next(it)
            except StopIteration:
                nxt.append(a)  # bye
                continue
            verdict = _judge(provider, task, a["solution"], b["solution"])
            winner = a if verdict["winner"] == "a" else b
            loser = b if winner is a else a
            winner["wins"] += 1
            matches.append(
                {
                    "a": a["id"],
                    "b": b["id"],
                    "winner": winner["id"],
                    "score_a": verdict.get("a"),
                    "score_b": verdict.get("b"),
                    "reason": verdict.get("reason", ""),
                }
            )
            nxt.append(winner)
        rounds.append({"round": round_no, "matches": matches})
        alive = nxt
        round_no += 1

    champion = alive[0]
    return {
        "task": task,
        "agents": agents,
        "rounds": rounds,
        "champion": {
            "id": champion["id"],
            "strategy_card": champion["card"],
            "wins": champion["wins"],
            "solution": champion["solution"],
        },
    }

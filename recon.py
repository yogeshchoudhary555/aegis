"""AEGIS Recon — inspired by the "reverse engineer anything" idea.

Point Recon at any public website and it tells you how the thing works:
what it does, how its key features are likely built, and what tech stack
it runs on. Strictly read-only and honest about uncertainty — it analyzes
publicly visible structure (HTML, meta tags, script URLs, headers), never
bypasses access controls, and every conclusion is labeled with the
evidence behind it.

This is an original, lightweight implementation of the *concept*
(inspect → explain → rebuild the idea in your own stack). It does not
decompile binaries and does not copy any other project's code.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class _StructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self.scripts: list[str] = []
        self.links: list[str] = []
        self.headings: list[str] = []
        self.forms: list[dict] = []
        self._in_title = False
        self._in_h = False
        self._cur_form: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and a.get("name") or a.get("property"):
            self.meta[a.get("name") or a.get("property")] = a.get("content", "")[:200]
        elif tag == "script" and a.get("src"):
            self.scripts.append(a["src"][:200])
        elif tag == "link" and a.get("href"):
            self.links.append(a["href"][:200])
        elif tag in ("h1", "h2"):
            self._in_h = True
        elif tag == "form":
            self._cur_form = {"action": a.get("action", ""), "method": a.get("method", "get"), "inputs": []}
        elif tag == "input" and self._cur_form is not None:
            self._cur_form["inputs"].append(a.get("name") or a.get("type") or "input")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in ("h1", "h2"):
            self._in_h = False
        elif tag == "form" and self._cur_form is not None:
            self.forms.append(self._cur_form)
            self._cur_form = None

    def handle_data(self, data):
        t = data.strip()
        if not t:
            return
        if self._in_title:
            self.title += t
        elif self._in_h and len(self.headings) < 20:
            self.headings.append(t[:120])


def _guess_stack(scripts: list[str], meta: dict, headers: dict) -> list[str]:
    hints: list[str] = []
    blob = " ".join(scripts).lower()
    if "next" in blob or "_next/static" in blob:
        hints.append("Next.js")
    if "nuxt" in blob:
        hints.append("Nuxt")
    if "wp-" in blob or "wp-content" in blob:
        hints.append("WordPress")
    if "shopify" in blob:
        hints.append("Shopify")
    if "react" in blob:
        hints.append("React")
    if "vue" in blob:
        hints.append("Vue")
    gen = meta.get("generator", "")
    if gen:
        hints.append(f"generator meta: {gen}")
    server = headers.get("server") or headers.get("Server")
    if server:
        hints.append(f"server header: {server}")
    if "cloudflare" in str(headers.get("cf-ray", "")).lower() or "cloudflare" in blob:
        hints.append("Cloudflare (CDN/WAF)")
    return hints or ["could not determine from public signals"]


def fetch_structure(url: str, timeout: int = 15) -> dict:
    """Fetch a URL and extract its public structure. Read-only."""
    import requests

    if not re.match(r"^https?://", url):
        url = "https://" + url
    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "AEGIS-Recon/1.0 (read-only site analysis)"},
    )
    resp.raise_for_status()
    parser = _StructureParser()
    parser.feed(resp.text[:500_000])
    headers = {k.lower(): v for k, v in resp.headers.items()}
    return {
        "url": url,
        "final_url": resp.url,
        "status": resp.status_code,
        "title": parser.title.strip()[:200],
        "meta_description": parser.meta.get("description", "")[:300],
        "headings": parser.headings[:12],
        "scripts": parser.scripts[:25],
        "forms": parser.forms[:8],
        "tech_hints": _guess_stack(parser.scripts, parser.meta, headers),
        "html_bytes": len(resp.text),
    }


def analyze(url: str, provider, tavily_search_fn=None) -> dict:
    """Recon a site: fetch structure, then have the LLM explain how it works.

    Returns the evidence (structure) plus the analysis, each labeled.
    tavily_search_fn: optional callable(query) -> results, used to enrich
    with public info about the site.
    """
    structure = fetch_structure(url)

    evidence = (
        f"URL: {structure['final_url']} (HTTP {structure['status']})\n"
        f"Title: {structure['title']}\n"
        f"Meta description: {structure['meta_description']}\n"
        f"Headings: {'; '.join(structure['headings'][:8])}\n"
        f"Tech hints: {', '.join(structure['tech_hints'])}\n"
        f"Forms: {len(structure['forms'])} (actions: "
        + ", ".join(f.get("action", "?")[:60] for f in structure["forms"][:4])
        + ")\n"
        f"Script bundles: {len(structure['scripts'])}"
    )

    extra = ""
    if tavily_search_fn:
        try:
            res = tavily_search_fn(f"{structure['title']} website what does it do")
            items = (res or {}).get("results", [])[:3]
            extra = "\n".join(f"- {i.get('title', '')}: {i.get('content', '')[:200]}" for i in items)
        except Exception:
            pass

    system = (
        "You are a software analyst. Given public, read-only evidence about a "
        "website, explain: 1) what the site does (one paragraph), 2) how its "
        "key features most likely work (3-5 bullets, each starting with the "
        "evidence it is based on), 3) the probable tech stack. Be honest about "
        "uncertainty — mark guesses as guesses. Never claim to have seen "
        "non-public code."
    )
    user = f"EVIDENCE (public, fetched read-only):\n{evidence}\n\nPUBLIC WEB CONTEXT:\n{extra or '(none)'}"
    res = provider.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    return {
        "url": structure["final_url"],
        "evidence": evidence,
        "tech_hints": structure["tech_hints"],
        "analysis": (res.text or "").strip(),
        "disclaimer": (
            "Read-only analysis of public signals. No access controls were "
            "bypassed; conclusions are inferences, not recovered source code."
        ),
    }

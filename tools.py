"""Tool implementations + OpenAI function-calling specs for the agent loop."""
import config

TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "tavily_search",
            "description": "Search the live web for current information, news, listings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {
                        "type": "integer",
                        "description": "Max results (1-10)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_read",
            "description": "Read remembered facts/preferences about the user from persistent memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Optional filter; empty returns all facts",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_write",
            "description": "Save a durable fact/preference about the user to persistent memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Short key, e.g. 'name'"},
                    "value": {"type": "string", "description": "The fact to remember"},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_approval",
            "description": (
                "MANDATORY before sending or acting on anything consequential "
                "(a message, email, booking, post, payment). Pauses the run and "
                "shows the user the exact draft to Approve, Edit, or Reject. "
                "The action is only 'sent' after explicit approval. Never claim "
                "something was sent without calling this first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "description": "e.g. 'message', 'email', 'booking'",
                    },
                    "draft_text": {
                        "type": "string",
                        "description": "The exact draft the user will review",
                    },
                    "recipient": {
                        "type": "string",
                        "description": "Who the action targets, e.g. 'property dealer'",
                    },
                },
                "required": ["action_type", "draft_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arena_run",
            "description": (
                "Run a tournament of AI strategies on a hard task: spawn N "
                "competitors with different strategy cards, let them debate "
                "pairwise, and return the winning solution. Use when the user "
                "wants the BEST answer, says 'arena', or is unhappy with a "
                "previous answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The task to compete on"},
                    "agents": {
                        "type": "integer",
                        "description": "Competitors (4 or 8; default 4 for speed)",
                        "default": 4,
                    },
                },
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recon_site",
            "description": (
                "Reverse-engineer a public website (read-only): fetch its "
                "structure and explain what it does, how its features likely "
                "work, and its probable tech stack. Every conclusion is "
                "labeled with its evidence."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The website URL to analyze"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forge_app",
            "description": (
                "Scaffold a working app from a plain-language description: "
                "designs the project and writes real files to disk inside a "
                "sandbox directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "What to build, in plain language",
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Folder name for the project (kebab-case)",
                        "default": "forged-app",
                    },
                },
                "required": ["description"],
            },
        },
    },
]


def _vault_tavily_available() -> bool:
    try:
        import sys

        sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
        from dynamic_credentials import dynamic_credential_entry

        entry = dynamic_credential_entry("custom.tavily", "access_token")
        return bool(entry.get("surrogate"))
    except Exception:
        return False


def _vault_tavily_search(query: str, max_results: int):
    """Live Tavily search via the vault-stored credential (surrogate exchange)."""
    import json as _json
    import sys
    import urllib.request

    sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
    from dynamic_credentials import add_surrogate_to_request, read_json_response

    body = {
        "query": query,
        "max_results": max(1, min(10, max_results)),
        "search_depth": "basic",
        "include_answer": False,
    }
    req = urllib.request.Request(
        config.TAVILY_URL,
        data=_json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    add_surrogate_to_request(
        req,
        "custom.tavily",
        entry_name="access_token",
        allowed_hosts=("api.tavily.com",),
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = read_json_response(resp)
    out = []
    for item in data.get("results", []):
        out.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": (item.get("content", "") or "")[:600],
            }
        )
    return {"results": out, "source": "tavily-live"}


def tavily_search(query: str, max_results: int = 5):
    """Web search via Tavily: vault credential > env key > offline stub."""
    if _vault_tavily_available():
        try:
            return _vault_tavily_search(query, max_results)
        except Exception as e:  # never crash the agent loop on a tool failure
            return {"results": [], "error": f"tavily_search failed: {e}"}
    if not config.TAVILY_API_KEY:
        return {
            "results": [],
            "note": "TAVILY_API_KEY not set — web search unavailable in offline mode.",
        }
    import requests  # lazy: keeps the mock path dependency-free

    try:
        r = requests.post(
            config.TAVILY_URL,
            json={
                "api_key": config.TAVILY_API_KEY,
                "query": query,
                "max_results": max(1, min(10, max_results)),
                "search_depth": "basic",
            },
            timeout=20,
        )
        r.raise_for_status()
        out = []
        for item in r.json().get("results", []):
            out.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": (item.get("content", "") or "")[:600],
                }
            )
        return {"results": out}
    except Exception as e:  # never crash the agent loop on a tool failure
        return {"results": [], "error": f"tavily_search failed: {e}"}

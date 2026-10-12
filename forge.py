"""AEGIS Forge — inspired by the "describe it, get an app" idea.

Tell Forge what you want in plain language and it scaffolds a working
project: a plan plus real files written to disk. The LLM designs the
structure; Forge writes it safely inside a sandbox directory, never
outside it.

Original implementation of the concept. No code copied from any
app-builder project.
"""
from __future__ import annotations

import json
import os
import re


def _safe_path(out_dir: str, name: str) -> str:
    """Resolve a generated filename safely inside out_dir (no traversal)."""
    name = name.strip().lstrip("/").replace("\\", "/")
    parts = [p for p in name.split("/") if p not in ("", ".", "..")]
    if not parts:
        raise ValueError(f"unsafe filename: {name!r}")
    full = os.path.abspath(os.path.join(out_dir, *parts))
    base = os.path.abspath(out_dir)
    if not full.startswith(base + os.sep):
        raise ValueError(f"path escapes sandbox: {name!r}")
    return full


def plan(description: str, provider) -> dict:
    """Ask the LLM to design the project: file list with contents."""
    system = (
        "You are a senior software architect. The user describes an app in "
        "plain language. Respond with ONLY a JSON object (no prose):\n"
        '{"project_name": "<kebab-case>", "stack": "<one line>", '
        '"files": [{"path": "relative/path.ext", "content": "<full file content>"}]}\n'
        "Rules: 4-10 files max. Prefer a single self-contained web app "
        "(index.html + style.css + app.js) OR a small Python project "
        "(main.py + requirements.txt + README.md). Every file must be "
        "complete and runnable — no TODOs, no placeholders. Keep each file "
        "under 300 lines."
    )
    res = provider.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Build this: {description}"},
        ]
    )
    raw = (res.text or "").strip()
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except Exception as e:
        raise ValueError(f"forge plan was not valid JSON: {e}")
    if not data.get("files"):
        raise ValueError("forge plan contained no files")
    return data


def build(description: str, provider, out_dir: str) -> dict:
    """Generate the plan and write all files. Returns manifest."""
    os.makedirs(out_dir, exist_ok=True)
    spec = plan(description, provider)
    written = []
    for f in spec["files"][:12]:  # hard cap
        path = _safe_path(out_dir, f["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f.get("content", ""))
        written.append(os.path.relpath(path, out_dir))
    # always include a README if the model didn't
    if not any(w.lower() == "readme.md" for w in written):
        rp = _safe_path(out_dir, "README.md")
        with open(rp, "w", encoding="utf-8") as fh:
            fh.write(
                f"# {spec.get('project_name', 'forged-app')}\n\n"
                f"Scaffolded by AEGIS Forge.\n\nStack: {spec.get('stack', 'n/a')}\n\n"
                f"Original request: {description}\n"
            )
        written.append("README.md")
    return {
        "project_name": spec.get("project_name", "forged-app"),
        "stack": spec.get("stack", ""),
        "out_dir": os.path.abspath(out_dir),
        "files": written,
    }

"""Reusable prompt-skills: markdown files the agent can invoke.

Each skill file has optional frontmatter:

    ---
    name: morning-briefing
    description: Generates the daily morning briefing.
    when: briefing, morning, good morning
    ---
    <skill prompt body...>

The `when` keywords auto-activate the skill when they appear in the user message.
Users can also force a skill with `/skill <name>` in chat.
"""
import glob
import os


def load_skills(directory: str = "skills"):
    skills = []
    for path in sorted(glob.glob(os.path.join(directory, "*.md"))):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        meta, body = {}, text
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                for line in text[3:end].strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip().lower()] = v.strip()
                body = text[end + 3 :].strip()
        stem = os.path.splitext(os.path.basename(path))[0]
        skills.append(
            {
                "name": meta.get("name", stem),
                "description": meta.get("description", ""),
                "when": [
                    w.strip().lower()
                    for w in meta.get("when", "").split(",")
                    if w.strip()
                ],
                "body": body,
                "path": path,
            }
        )
    return skills


def match_skill(skills, user_message: str):
    """Return the first skill whose `when` keywords match, or an explicit /skill call.

    Explicit memory-store intents ("remember my name is…") never auto-activate
    a skill — the agent should just save the fact.
    """
    low = user_message.lower().strip()
    if low.startswith("/skill"):
        want = low.replace("/skill", "", 1).strip()
        for s in skills:
            if s["name"].lower() == want:
                return s
        return None
    memory_store_hints = (
        "remember that",
        "remember my",
        "please remember",
        "my name is ",
        "i live in ",
        "i prefer ",
    )
    if any(h in low for h in memory_store_hints):
        return None
    for s in skills:
        if any(k in low for k in s["when"]):
            return s
    return None

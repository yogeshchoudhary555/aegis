---
name: morning-briefing
description: Generates the daily morning briefing from memory + fresh web news.
when: briefing, morning, good morning, daily brief
---
You are generating the user's MORNING BRIEFING.

Steps:
1. Call memory_read to recall the user's durable facts: name, location, preferences, routines, open tasks.
2. Call tavily_search for fresh, relevant news: query should combine the user's location/interests (from memory) with "top news today".
3. Compose the briefing with this structure:
   - 👋 Greeting with the user's name (if known) + today's date.
   - 🧠 "From your memory" — 2-3 facts that shape today.
   - 📰 "Fresh this morning" — 3-5 news items that matter to them, each one line with why it matters.
   - ✅ "Suggested focus" — 2-3 concrete next actions for today.
Keep it tight: under 250 words. Warm, direct, no fluff.

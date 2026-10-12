---
name: rental-hunt
description: Researches rental listings and drafts a dealer outreach message.
when: rental, rent, flat, bhk, dealer, listing, accommodation
---
You are running a RENTAL HUNT for the user. You MUST complete ALL steps in
order. Do NOT give your final answer until step 5 is done.

Steps:
1. Call memory_read first — check for the user's budget, preferred location, family size, or past rental preferences.
2. Call tavily_search with a specific query, e.g. "2 BHK flat for rent <location> family under <budget>".
3. Summarize the top 3-5 real listings: price, location, key specs, source link.
4. Draft a short, polite dealer/owner outreach message the user can send as-is (WhatsApp-ready, under 60 words), referencing the listing and asking for a visit slot.
5. TRUST BEAT (MANDATORY — never skip): call request_approval with action_type="message", the exact draft_text, and recipient="property dealer". The run pauses here: the user reviews the draft in the UI and Approves / Edits / Rejects it. NOTHING is sent until they approve. Never present the message as sent, and never finish your turn without this call.
6. If memory has no budget/location, ask ONE clarifying question instead of guessing.

Never invent listings or phone numbers — only report what the search returned.

"""AEGIS — web UI + API. Run:  python app.py   then open http://localhost:8000"""
import config
import llm as llm_module
from agent import ChiefOfStaff
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from memory import Memory
from pydantic import BaseModel
from router import build_router
from skills import load_skills

router = build_router(config, llm_module)
provider = router  # agent talks to the router; router fails over
memory = Memory(config.MEMORY_DB)
skills = load_skills("skills")
agent = ChiefOfStaff(provider, memory, skills)


def _provider_kind() -> str:
    """Primary backend behind the SmartRouter."""
    return router.primary

app = FastAPI(title="AEGIS")


class ChatIn(BaseModel):
    message: str
    history: list = []


class MemoryIn(BaseModel):
    key: str
    value: str


class ApproveIn(BaseModel):
    approval_id: str
    edited_text: str = ""


class RejectIn(BaseModel):
    approval_id: str


@app.get("/api/health")
def health():
    kind = _provider_kind()
    return {
        "provider": kind,
        "live": kind == "nebius",
        "model": config.NEMOTRON_MODEL,
        "backend": "SmartRouter",
        "router": router.stats(),
        "nebius_key_set": kind == "nebius",
        "tavily_key_set": True,  # resolved per-call: vault > env > stub
    }


class ArenaIn(BaseModel):
    task: str
    agents: int = 4


@app.post("/api/arena")
def arena_run(inp: ArenaIn):
    """Tournament of strategies on a hard task."""
    import arena as arena_mod
    result = arena_mod.run_arena(inp.task, provider, agents=inp.agents)
    champ = result["champion"]
    return {
        "task": result["task"],
        "agents": result["agents"],
        "rounds": result["rounds"],
        "champion_solution": champ["solution"],
        "champion_card": champ.get("strategy_card", champ.get("card")),
        "wins": champ["wins"],
    }


class ReconIn(BaseModel):
    url: str


@app.post("/api/recon")
def recon_site(inp: ReconIn):
    """Read-only reverse-engineering of a public website."""
    import recon as recon_mod
    from tools import tavily_search
    return recon_mod.analyze(inp.url, provider, tavily_search_fn=lambda q: tavily_search(q, 3))


class ForgeIn(BaseModel):
    description: str
    project_name: str = "forged-app"


@app.post("/api/forge")
def forge_app(inp: ForgeIn):
    """Scaffold a working app from a plain-language description."""
    import forge as forge_mod
    safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in inp.project_name.lower()).strip("-") or "forged-app"
    return forge_mod.build(inp.description, provider, f"data/forged/{safe}")


@app.get("/api/router-stats")
def router_stats():
    """SmartRouter usage + failover stats."""
    return router.stats()


@app.post("/api/chat")
def chat(inp: ChatIn):
    return agent.respond(inp.message, inp.history)


class HuntIn(BaseModel):
    location: str = "H Block, Sri Ganganagar"
    budget: str = "10000"


@app.post("/api/rental-hunt")
def rental_hunt(inp: HuntIn):
    """Deterministic rental-hunt demo pipeline with the approval gate."""
    return agent.run_rental_hunt(inp.location, inp.budget)


@app.get("/api/briefing")
def briefing():
    return agent.morning_briefing()


@app.get("/api/memory")
def memory_list():
    return {"facts": memory.read()}


@app.post("/api/memory")
def memory_add(inp: MemoryIn):
    memory.write(inp.key, inp.value)
    return {"ok": True}


@app.get("/api/skills")
def skills_list():
    return {
        "skills": [
            {"name": s["name"], "description": s["description"]} for s in skills
        ]
    }


@app.get("/api/approvals")
def approvals_list():
    """Pending approval requests (the trust beat)."""
    return {"pending": agent.list_pending_approvals()}


@app.post("/api/approvals/approve")
def approvals_approve(inp: ApproveIn):
    return agent.approve(inp.approval_id, inp.edited_text or None)


@app.post("/api/approvals/reject")
def approvals_reject(inp: RejectIn):
    return agent.reject(inp.approval_id)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AEGIS — your always-on AI</title>
<style>
  :root { --bg:#0f1420; --panel:#171e2e; --line:#26304a; --txt:#e8ecf5; --dim:#93a0bd;
          --acc:#6ea8fe; --acc2:#38d39a; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--txt);
         font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  header { padding:14px 20px; border-bottom:1px solid var(--line);
           display:flex; align-items:center; gap:12px; }
  header h1 { font-size:18px; margin:0; }
  header .badge { font-size:12px; color:var(--dim); border:1px solid var(--line);
                  border-radius:20px; padding:3px 10px; }
  main { display:grid; grid-template-columns:1fr 340px; gap:0; height:calc(100vh - 57px); }
  #chatcol { display:flex; flex-direction:column; border-right:1px solid var(--line); }
  #msgs { flex:1; overflow-y:auto; padding:18px; display:flex; flex-direction:column; gap:12px; }
  .msg { max-width:78%; padding:10px 14px; border-radius:14px; line-height:1.5;
         white-space:pre-wrap; font-size:14.5px; }
  .user { align-self:flex-end; background:var(--acc); color:#0a1020; }
  .bot { align-self:flex-start; background:var(--panel); border:1px solid var(--line); }
  .meta { font-size:11px; color:var(--dim); margin-top:6px; }
  #composer { display:flex; gap:8px; padding:12px 16px; border-top:1px solid var(--line); }
  #composer input { flex:1; background:var(--panel); border:1px solid var(--line);
                    color:var(--txt); border-radius:10px; padding:10px 14px; font-size:15px; }
  #composer button { background:var(--acc); border:0; border-radius:10px; padding:0 20px;
                     font-weight:600; cursor:pointer; }
  aside { display:flex; flex-direction:column; overflow:hidden; }
  .tabs { display:flex; border-bottom:1px solid var(--line); }
  .tabs button { flex:1; background:none; border:0; color:var(--dim); padding:12px;
                 cursor:pointer; font-size:13.5px; border-bottom:2px solid transparent; }
  .tabs button.on { color:var(--txt); border-bottom-color:var(--acc); }
  .pane { flex:1; overflow-y:auto; padding:16px; display:none; font-size:13.5px;
          line-height:1.6; white-space:pre-wrap; }
  .pane.on { display:block; }
  .fact { background:var(--panel); border:1px solid var(--line); border-radius:10px;
          padding:8px 12px; margin-bottom:8px; }
  .fact b { color:var(--acc2); }
  .hint { color:var(--dim); font-size:12.5px; }
  .appr { border-color:var(--acc); }
  .appr-title { font-weight:700; margin-bottom:8px; }
  .appr-draft { background:#0f1420; border:1px dashed var(--line); border-radius:8px;
                padding:10px 12px; margin-bottom:10px; }
  .appr-edit { width:100%; min-height:90px; background:#0f1420; color:var(--txt);
               border:1px solid var(--acc); border-radius:8px; padding:10px 12px;
               margin-bottom:10px; font:inherit; }
  .appr-actions { display:flex; gap:8px; flex-wrap:wrap; }
  .abtn { background:var(--panel); color:var(--txt); border:1px solid var(--line);
          border-radius:8px; padding:8px 14px; cursor:pointer; font-size:13px; }
  .abtn.go { background:var(--acc2); color:#06130c; font-weight:700; border:0; }
  .abtn.no { border-color:#7a2f3a; color:#f0a3ae; }
  @media (max-width:800px){ main{grid-template-columns:1fr;} aside{display:none;} }
</style>
</head>
<body>
<header>
  <h1>🛡️ AEGIS</h1>
  <span class="badge" id="prov">…</span>
</header>
<main>
  <div id="chatcol">
    <div id="msgs"></div>
    <div id="composer">
      <input id="inp" placeholder="Ask anything — try 'remember my name is…' or 'morning briefing'" autocomplete="off">
      <button onclick="send()">Send</button>
      <button onclick="hunt()" title="Live rental hunt: memory → Tavily → draft → your approval">🏠 Hunt</button>
    </div>
  </div>
  <aside>
    <div class="tabs">
      <button class="on" onclick="tab('brief',this)">Briefing</button>
      <button onclick="tab('mem',this)">Memory</button>
      <button onclick="tab('skl',this)">Skills</button>
    </div>
    <div class="pane on" id="pane-brief"><span class="hint">Loading…</span></div>
    <div class="pane" id="pane-mem"><span class="hint">Loading…</span></div>
    <div class="pane" id="pane-skl"><span class="hint">Loading…</span></div>
  </aside>
</main>
<script>
const history = [];
async function api(path, opts){ const r = await fetch(path, opts); return r.json(); }
function addMsg(cls, text, meta){
  const d = document.createElement('div');
  d.className = 'msg ' + cls;
  d.innerHTML = text.replace(/</g,'&lt;');
  if (meta){ const m = document.createElement('div'); m.className='meta'; m.textContent = meta; d.appendChild(m); }
  document.getElementById('msgs').appendChild(d);
  d.scrollIntoView({behavior:'smooth', block:'end'});
}
async function send(){
  const inp = document.getElementById('inp');
  const text = inp.value.trim();
  if (!text) return;
  inp.value = '';
  addMsg('user', text);
  history.push({role:'user', content:text});
  addMsg('bot', '…');
  const res = await api('/api/chat', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({message:text, history:history.slice(0,-1)})});
  document.querySelectorAll('#msgs .bot').forEach(e => { if (e.textContent.trim()==='…') e.remove(); });
  showReply(res);
}
async function hunt(){
  addMsg('user', '🏠 rental hunt: 2 BHK under ₹10k near H Block, Sri Ganganagar');
  history.push({role:'user', content:'rental hunt'});
  addMsg('bot', '…');
  const res = await api('/api/rental-hunt', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: '{}'});
  document.querySelectorAll('#msgs .bot').forEach(e => { if (e.textContent.trim()==='…') e.remove(); });
  showReply(res);
}
function showReply(res){
  history.push({role:'assistant', content:res.reply});
  let meta = '';
  if (res.steps && res.steps.length)
    meta = res.steps.map((s,i) => (i+1) + '. ' + s.tool + (s.detail ? ' — ' + s.detail : '')).join(String.fromCharCode(10));
  else if (res.tools_used && res.tools_used.length) meta = 'tools: ' + res.tools_used.join(', ');
  if (res.skill) meta += (meta ? String.fromCharCode(10) : '') + 'skill: ' + res.skill;
  addMsg('bot', res.reply, meta);
  if (res.pending_approval) addApprovalCard(res.pending_approval);
  loadMemory();
}
function esc(s){ return String(s == null ? '' : s).replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function addApprovalCard(ap){
  const wrap = document.createElement('div');
  wrap.className = 'msg bot appr';
  wrap.id = 'appr-' + ap.id;
  const draft = document.createElement('div');
  draft.className = 'appr-draft';
  draft.textContent = ap.draft_text;
  const ta = document.createElement('textarea');
  ta.className = 'appr-edit';
  ta.style.display = 'none';
  const title = document.createElement('div');
  title.className = 'appr-title';
  title.textContent = '✋ Approval needed — ' + ap.action_type + (ap.recipient ? ' → ' + ap.recipient : '');
  const actions = document.createElement('div');
  actions.className = 'appr-actions';
  const bGo = document.createElement('button'); bGo.className = 'abtn go'; bGo.textContent = 'Approve & send';
  const bEdit = document.createElement('button'); bEdit.className = 'abtn'; bEdit.textContent = 'Edit';
  const bNo = document.createElement('button'); bNo.className = 'abtn no'; bNo.textContent = 'Reject';
  bGo.onclick = () => apprDecide(ap.id, 'approve');
  bEdit.onclick = () => { ta.value = draft.textContent; draft.style.display = 'none'; ta.style.display = 'block'; ta.focus(); };
  bNo.onclick = () => apprDecide(ap.id, 'reject');
  actions.append(bGo, bEdit, bNo);
  wrap.append(title, draft, ta, actions);
  document.getElementById('msgs').appendChild(wrap);
  wrap.scrollIntoView({behavior:'smooth', block:'end'});
}
async function apprDecide(id, how){
  const w = document.getElementById('appr-' + id);
  const ta = w.querySelector('.appr-edit');
  const edited = (ta && ta.style.display !== 'none') ? ta.value : '';
  const path = how === 'approve' ? '/api/approvals/approve' : '/api/approvals/reject';
  const res = await api(path, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({approval_id:id, edited_text:edited})});
  w.querySelector('.appr-actions').innerHTML = '<span class="hint">' + esc(res.reply || 'Done.') + '</span>';
  if (ta) ta.style.display = 'none';
  const d = w.querySelector('.appr-draft'); if (d && edited) d.textContent = edited;
}
function tab(name, btn){
  document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  document.querySelectorAll('.pane').forEach(p => p.classList.remove('on'));
  document.getElementById('pane-'+name).classList.add('on');
}
async function loadBrief(){
  const res = await api('/api/briefing');
  document.getElementById('pane-brief').textContent = res.reply;
}
async function loadMemory(){
  const res = await api('/api/memory');
  const el = document.getElementById('pane-mem');
  if (!res.facts.length){ el.innerHTML = '<span class="hint">Nothing remembered yet. Tell me a fact — e.g. “remember my name is…”.</span>'; return; }
  el.innerHTML = res.facts.map(f =>
    `<div class="fact"><b>${f.key}</b><br>${String(f.value).replace(/</g,'&lt;')}<br><span class="hint">${f.updated_at}</span></div>`
  ).join('');
}
async function loadSkills(){
  const res = await api('/api/skills');
  document.getElementById('pane-skl').innerHTML = res.skills.map(s =>
    `<div class="fact"><b>/${s.name}</b><br>${s.description}<br><span class="hint">type /skill ${s.name} in chat</span></div>`
  ).join('') || '<span class="hint">No skills found.</span>';
}
(async function init(){
  const h = await api('/api/health');
  document.getElementById('prov').textContent =
    h.live ? '⚡ ' + h.model + ' · Nebius Token Factory · LIVE' : '🔌 offline demo mode (no API key)';
  addMsg('bot', "Hi — I'm AEGIS. I remember what matters, research the live web, settle hard calls in the Arena, X-ray any website, and forge apps from plain words. What's on your mind?");
  loadBrief(); loadMemory(); loadSkills();
})();
document.getElementById('inp').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


if __name__ == "__main__":
    import uvicorn

    print(f"AEGIS starting — router primary: {router.primary}")
    uvicorn.run(app, host="0.0.0.0", port=config.PORT)

if(!requireAuth()) throw new Error("auth");
recordVisit();
const user = currentUser();
if(!user || user.role!=="admin"){ location.href="/app.html"; throw new Error("not-admin"); }

function escapeHtml(s){ return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
function parseDT(s){ s=String(s||""); return new Date(/(Z|[+-]\d{2}:?\d{2})$/i.test(s)?s:s+"Z"); }
function fmtAdminDate(s){ return parseDT(s).toLocaleString('sw-TZ',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}); }
function fmtAdminTime(s){ return parseDT(s).toLocaleTimeString('sw-TZ',{hour:'2-digit',minute:'2-digit'}); }

async function createPred(){
  try{
    await API.post("/api/admin/predictions", {
      home_team: document.getElementById("home").value,
      away_team: document.getElementById("away").value,
      match_date: document.getElementById("date").value,
      odds: parseFloat(document.getElementById("odds").value)
    });
    document.getElementById("msg").textContent="Imeundwa";
    load();
  }catch(e){ document.getElementById("msg").textContent=e.message; }
}

async function syncFs(){
  try{
    const r = await API.post("/api/admin/sync-footystats", {});
    document.getElementById("syncmsg").textContent = "Zimeingizwa mechi " + r.imported;
    load();
  }catch(e){ document.getElementById("syncmsg").textContent = e.message; }
}

async function load(){
  try{
    const preds = await API.get("/api/admin/predictions");
    const el = document.getElementById("list");
    el.innerHTML = preds.map(p=>`
      <div class="card" style="padding:12px">
        <div style="display:flex;justify-content:space-between;align-items:start;gap:8px">
          <div>
            <div style="font-size:16px"><b>${escapeHtml(p.home_team)}</b> <span style="color:#999">vs</span> <b>${escapeHtml(p.away_team)}</b></div>
            <div class="muted" style="margin-top:4px">📅 ${escapeHtml(fmtAdminDate(p.match_date))}</div>
          </div>
          <div style="text-align:right">
            <div style="font-weight:700;color:#1a73e8;font-size:18px">${p.odds}</div>
            <div class="muted" style="font-size:11px">Odds</div>
          </div>
        </div>
        <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
          <span class="badge">${p.status==="scheduled"?"⏳ Haijaanza":p.status==="live"?"🔴 Moja kwa moja":"✅ Imemalizika"}</span>
          <span class="badge ${p.outcome==="win"?"win":p.outcome==="lose"?"lose":""}">${p.outcome==="win"?"✔ Kushinda":p.outcome==="lose"?"❌ Kupotea":p.outcome||"— Hakuna matokeo"}</span>
          <span class="badge" style="background:${p.allowed?'#e6f4ea':'#fce8e6'};color:${p.allowed?'#1e8e3e':'#d93025'}">${p.allowed?"✔ Imeruhusiwa":"⛔ Imezuiwa"}</span>
        </div>
        <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">
          <button class="btn small secondary" data-action="toggleAllow" data-id="${p.id}" data-allowed="${!p.allowed}">${p.allowed?"🔒 Zuia":"✅ Ruhusu"}</button>
          <button class="btn small secondary" data-action="setStatus" data-id="${p.id}" data-status="live">🔴 Moja kwa moja</button>
          <button class="btn small secondary" data-action="settleWin" data-id="${p.id}">✔ Imeshinda</button>
          <button class="btn small secondary" data-action="settleLose" data-id="${p.id}">✘ Imepotea</button>
        </div>
        ${p.locked?"<div class='muted' style='margin-top:6px'>🔒 Imefungwa</div>":""}
      </div>
    `).join("");
  }catch(e){
    const m = document.getElementById("msg");
    if(m) m.textContent = e.message;
  }
}

async function toggleAllow(id, allowed){
  try{ await API.post("/api/admin/predictions/"+id+"/allow", {allowed}); load(); }
  catch(e){ alert(e.message); }
}
async function settle(id, outcome){
  try{ await API.put("/api/admin/predictions/"+id, {status:"finished", outcome}); load(); }
  catch(e){ alert(e.message); }
}
async function setStatus(id, status){
  try{ await API.put("/api/admin/predictions/"+id, {status}); load(); }
  catch(e){ alert(e.message); }
}

async function settleNow(){
  try{
    document.getElementById("histmsg").textContent = "Inatafuta matokeo...";
    const r = await API.post("/api/admin/settle", {});
    let msg = "Zimepimwa " + r.checked + ", zimeshina " + r.settled;
    if(r.note) msg += " → " + r.note;
    document.getElementById("histmsg").textContent = msg;
    loadHistory();
  }catch(e){ document.getElementById("histmsg").textContent = e.message; }
}

const outcomeLabel = o => o==="win" ? "WON" : o==="lose" ? "LOSE" : "INAYOSUBIRI";
const outcomeCls   = o => o==="win" ? "win"  : o==="lose" ? "lose"  : "";

async function loadHistory(){
  try{
    const days = await API.get("/api/admin/history");
    const el = document.getElementById("history-detail");
    if(!days.length){ el.innerHTML = "<div class='muted'>Hakuna mechi bado.</div>"; return; }
    el.innerHTML = days.map(d=>{
      const accaLabel = d.acca==="win" ? "WON" : d.acca==="lose" ? "LOSE" : "INAYOSUBIRI";
      const accaCls = d.acca==="win" ? "win" : d.acca==="lose" ? "lose" : "";
      return `
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
          <h3 style="margin:0">${escapeHtml(d.date)}</h3>
          <span><span class="badge">ACCA</span> <span class="badge ${accaCls}">${accaLabel}</span></span>
        </div>
        <div class="muted" style="margin-top:4px">
          Jumla: ${d.total} → WON ${d.won} → LOSE ${d.lose} → inasubiri ${d.pending}
          ${d.hit_rate!=null ? " → hit rate " + d.hit_rate + "%" : ""}
        </div>
        <div style="margin-top:8px">
        ${d.matches.map(m=>`
          <div class="pick-item" style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
            <div><b>${escapeHtml(m.home_team)}</b> vs <b>${escapeHtml(m.away_team)}</b>
              <div class="muted">Odds ${m.odds} → ${escapeHtml(fmtAdminTime(m.match_date))}</div>
            </div>
            <div style="display:flex;gap:6px;align-items:center">
              <span class="badge">SINGLE</span>
              <span class="badge ${outcomeCls(m.outcome)}">${outcomeLabel(m.outcome)}</span>
            </div>
          </div>
        `).join("")}
        </div>
      </div>`;
    }).join("");
  }catch(e){ document.getElementById("histmsg").textContent = e.message; }
}
load(); loadHistory();

document.addEventListener("click", (e) => {
  const btn = e.target.closest && e.target.closest("[data-action]");
  if(!btn) return;
  const action = btn.dataset.action;
  if(action === "syncFs") syncFs();
  else if(action === "settleNow") settleNow();
  else if(action === "loadHistory") loadHistory();
  else if(action === "toggleAllow") toggleAllow(btn.dataset.id, btn.dataset.allowed === "true");
  else if(action === "setStatus") setStatus(btn.dataset.id, btn.dataset.status);
  else if(action === "settleWin") settle(btn.dataset.id, "win");
  else if(action === "settleLose") settle(btn.dataset.id, "lose");
});
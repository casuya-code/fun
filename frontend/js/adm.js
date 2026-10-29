// ADM - private accumulator engine (admin only)
(async () => {
  // each section loads independently so one failure cannot blank the page
  try { await loadStats(); } catch(e){}
  try { await loadCandidates(); }
  catch(e){ admMsg("Imeshindwa kupata machaguo: " + e.message); }
  try { await loadSlips(); }
  catch(e){ admMsg("Imeshindwa kupata mikeka: " + e.message); }
  renderCompose();
})();

function esc(s){ return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
function parseDT(d){
  if(!d) return new Date(NaN);
  const s = String(d);
  return new Date(/(Z|[+-]\d{2}:?\d{2})$/i.test(s) ? s : s + "Z");
}

function admMsg(t){ const el = document.getElementById("adm-msg"); if(el) el.textContent = t || ""; }

function slipProfit(s){
  if(s.status === "won") return (Number(s.combined_odds) - 1) * 10000;
  if(s.status === "lost") return -10000;
  return 0;
}
function fmtMoney(n){ return Number(n).toLocaleString(undefined,{maximumFractionDigits:2}); }

const AD_MONTHS = ["Jan","Feb","Mac","Apr","Mei","Jun","Jul","Ago","Sep","Okt","Nov","Des"];
function fmtKickoff(iso){
  try{
    const d = parseDT(iso);
    const dd = String(d.getDate()).padStart(2,"0");
    const mm = AD_MONTHS[d.getMonth()];
    const hh = String(d.getHours()).padStart(2,"0");
    const mi = String(d.getMinutes()).padStart(2,"0");
    return `${dd} ${mm} ${hh}:${mi}`;
  }catch(e){ return ""; }
}

async function loadStats(){
  try{
    const s = await API.get("/api/adm/stats");
    document.getElementById("st-slips").textContent = s.slips;
    document.getElementById("st-rate").textContent = s.win_rate == null ? "-" : s.win_rate;
    document.getElementById("st-roi").textContent = s.roi_pct == null ? "-" : s.roi_pct;
    document.getElementById("st-odds").textContent = s.avg_odds == null ? "-" : s.avg_odds;
    document.getElementById("st-won").textContent = s.won;
    document.getElementById("st-pending").textContent = s.pending;
    const names = { over15: "Over 1.5" };
    const parts = Object.keys(s.per_filter || {}).map(k=>{
      const d = s.per_filter[k];
      return `${names[k]||k}: U${d.win}/P${d.lose}${d.win_rate!=null?` (${d.win_rate}%)`:""}`;
    });
    document.getElementById("adm-filter-stats").textContent = parts.length
      ? "Kwa kichujio: " + parts.join(" · ")
      : "Bado hakuna matokeo yaliyorekodiwa.";
  }catch(e){ /* stats are optional */ }
}

async function loadCandidates(){
  const cands = await API.get("/api/adm/candidates");
  document.getElementById("cand-count").textContent = cands.length;
  const el = document.getElementById("adm-candidates");
  if(!cands.length){ el.innerHTML = "<div class='muted'>Hakuna data bado. Bonyeza “Sasisha data”.</div>"; return; }
  el.innerHTML = cands.map(c=>`
    <div class="pick-item ${(composing.includes(c.id)||c.qualifies)?"selected":""}" data-id="${c.id}">
      <div><b>${esc(c.home_team)}</b> vs <b>${esc(c.away_team)}</b></div>
      <div class="muted">${esc(c.reason)} · Odds ${c.odds} · ${(c.kickoff||c.match_date) ? parseDT(c.kickoff||c.match_date).toLocaleString('sw-TZ',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}) : ''}</div>
      <div style="margin-top:6px">
        ${c.used ? `<span class="badge">Imetumika</span>` :
          composing.includes(c.id)
          ? `<button class="btn small secondary" data-action="addToSlip" data-id="${c.id}">Ondoa kwenye mkeka</button>`
          : c.qualifies
          ? `<button class="btn small" data-action="addToSlip" data-id="${c.id}">Ongeza kwenye mkeka</button>`
          : `<span class="badge">Hakustahili</span>`}
      </div>
    </div>
  `).join("");
}

async function syncEngine(){
  admMsg("Inasasisha...");
  try{
    const r = await API.post("/api/adm/sync", {});
    admMsg(`Imekamilika: mpya ${r.added}, jumla ${r.total}`);
    await loadCandidates();
  }catch(e){ admMsg("Imeshindikana: " + e.message); }
}

async function settleNow(){
  admMsg("Inatafuta matokeo...");
  try{
    const r = await API.post("/api/adm/settle", {});
    admMsg(`Imekamilika: mechi ${r.matches_checked}, matokeo ${r.legs_settled}, mikeka ${r.slips_settled}` + (r.note?` · ${r.note}`:""));
    await loadSlips();
    await loadStats();
  }catch(e){ admMsg("Imeshindikana: " + e.message); }
}

async function archiveSettled(){
  admMsg("Inahifadhi mikeka iliyokamilika...");
  try{
    const r = await API.post("/api/adm/archive", {});
    if(!r.archived){
      admMsg("Hakuna mikeka iliyokamilika ya kuhifadhi.");
      return;
    }
    admMsg(`Imehifadhi mikeka ${r.archived} kwenye kumbukumbu.`);
    await loadSlips();
    await loadStats();
  }catch(e){ admMsg("Imeshindikana: " + e.message); }
}

let composing = [];
function renderCompose(){
  const el = document.getElementById("adm-compose");
  if(!el) return;
  if(!composing.length){ el.innerHTML = ""; return; }
  el.innerHTML = `<div class="card">
    <div class="muted">Mechi ${composing.length} kwenye mkeka wako</div>
    <button class="btn" style="margin-top:8px" data-action="saveComposed">Hifadhi mkeka (${composing.length} mechi)</button>
  </div>`;
}
function addToSlip(id){
  if(composing.includes(id)){
    composing = composing.filter(x=>x!==id);
  } else {
    composing.push(id);
  }
  const item = document.querySelector(`#adm-candidates .pick-item[data-id="${id}"]`);
  if(item) item.classList.toggle("selected", composing.includes(id));
  renderCompose();
  loadCandidates().catch(()=>{});
  admMsg(composing.length
    ? "Mkeka unaendelea: mechi " + composing.length + " (unahitaji odds 10+)"
    : "Mkeka umetolewa.");
}

async function generateSlip(){
  admMsg("Inatengeneza...");
  try{
    const s = await API.post("/api/adm/generate", {});
    admMsg("Imetengenezwa: odds " + s.combined_odds + " · Kelly " + s.kelly_stake);
    composing = [];
    renderCompose();
    await loadCandidates();
    await loadSlips();
    await loadStats();
  }catch(e){ admMsg("Imeshindikana: " + e.message); }
}

async function saveComposed(){
  if(!composing.length){ admMsg("Ongeza mechi kwanza"); return; }
  admMsg("Inahifadhiwa...");
  try{
    const s = await API.post("/api/adm/slips", { match_ids: composing });
    admMsg("Imehifadhiwa: odds " + s.combined_odds + " · Kelly " + s.kelly_stake);
    composing = [];
    renderCompose();
    await loadCandidates();
    await loadSlips();
    await loadStats();
  }catch(e){ admMsg("Imeshindikana: " + e.message); }
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest && e.target.closest("[data-action]");
  if(!btn) return;
  const action = btn.dataset.action;
  if(action === "syncEngine") guarded(syncEngine);
  else if(action === "generateSlip") guarded(generateSlip);
  else if(action === "settleNow") guarded(settleNow);
  else if(action === "archiveSettled") guarded(archiveSettled);
  else if(action === "addToSlip") addToSlip(btn.dataset.id);
  else if(action === "saveComposed") guarded(saveComposed);
});

// Prevent a double click from creating two slips at once.
let admBusy = false;
async function guarded(fn){
  if(admBusy) return;
  admBusy = true;
  try { await fn(); }
  finally { admBusy = false; }
}

async function loadSlips(){
  const slips = await API.get("/api/adm/slips");
  const el = document.getElementById("adm-slips");
  const stSw = { draft: "Inasubiri", won: "Imeshinda", lost: "Imepotea" };
  if(!slips.length){ el.innerHTML = "<div class='muted'>Hakuna mikeka bado.</div>"; return; }
  el.innerHTML = slips.map(s=>`
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <b>Odds ${s.combined_odds}</b>
        <span class="badge ${s.status==="won"?"win":s.status==="lost"?"lose":""}">${stSw[s.status]||s.status}</span>
      </div>
      <div class="muted">
        Uwezekano ${s.win_prob!=null?(s.win_prob*100).toFixed(1)+"%":"-"}
        · Kelly ${s.kelly_stake!=null?s.kelly_stake:"-"} (¼ ya thamani)
        · Faida: ${fmtMoney(slipProfit(s))} (stake 10,000)
        · ${s.note||""}
      </div>
      ${s.legs.map(l=>`
        <div class="pick-item">
          <div>${esc(l.home_team)} v ${esc(l.away_team)}</div>
          <div class="muted">
            Over 1.5 ${l.over15_pct!=null?l.over15_pct+"%":"-"} · Odds ${l.odds}
            ${l.score?` · Matokeo <b>${l.score}</b>`:""}
            ${l.kickoff?` · ${fmtKickoff(l.kickoff)}`:""}
          </div>
          ${l.outcome ? `
            <div class="muted">${l.outcome==="win"?"✔ Imeshinda":"✘ Imepotea"}${l.score?` (${l.score})`:""}</div>`
          : s.status==="draft" ? `
            <div class="muted" style="margin-top:6px">Inasubiri matokeo kiotomatiki (AI)...</div>` : ""}
        </div>
      `).join("")}
    </div>
  `).join("");
}

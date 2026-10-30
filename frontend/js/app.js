if(!requireAuth()) throw new Error("auth");
recordVisit();

let selected = new Set();
let preloaded = false;
let editingPickId = null;
let availablePreds = [];

function statusSw(s){
  if(s==="scheduled") return "Inasubiri";
  if(s==="live") return "Moja kwa moja";
  if(s==="finished") return "Imemalizika";
  return s;
}
function escapeHtml(s){ return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
function pickStatusSw(s){
  if(s==="pending") return "Inasubiri";
  if(s==="won") return "Imeshinda";
  if(s==="lost") return "Imepotea";
  if(s==="void") return "Imerudishiwa";
  return s;
}
function outcomeSw(o){
  if(o==="win") return "✔ Imeshinda";
  if(o==="lose") return "✘ Imepotea";
  if(o==="void") return "Imebatilishwa";
  return "";
}
function pickProfit(p){
  const odds = Number(p.combined_odds);
  const st = p.status;
  if(st === "won") return (odds - 1) * 10000;
  if(st === "lost") return -10000;
  return 0;
}
function fmtMoney(n){ return Number(n).toLocaleString(undefined,{maximumFractionDigits:2}); }
// Server datetimes are stored as UTC without a timezone suffix; parse them
// as UTC so the browser shows the correct local time.
function parseDT(d){
  if(!d) return new Date(NaN);
  const s = String(d);
  return new Date(/(Z|[+-]\d{2}:?\d{2})$/i.test(s) ? s : s + "Z");
}
function fmtDay(d){
  const x = parseDT(d);
  const dd = String(x.getDate()).padStart(2,"0");
  const mm = String(x.getMonth()+1).padStart(2,"0");
  const yy = x.getFullYear();
  return `${dd}/${mm}/${yy}`;
}
function fmtDate(d){
  const x = parseDT(d);
  const dd = String(x.getDate()).padStart(2,"0");
  const mm = String(x.getMonth()+1).padStart(2,"0");
  const yy = x.getFullYear();
  const hh = String(x.getHours()).padStart(2,"0");
  const mi = String(x.getMinutes()).padStart(2,"0");
  return `${dd}/${mm}/${yy}, ${hh}:${mi}`;
}
function localDateStr(d=new Date()){
  const x = new Date(d);
  const dd = String(x.getDate()).padStart(2,"0");
  const mm = String(x.getMonth()+1).padStart(2,"0");
  return `${x.getFullYear()}-${mm}-${dd}`;
}
function isPastMatch(d){
  const md = parseDT(d);
  const now = new Date();
  return md.getTime() < now.getTime() - 60000;
}

const PAGE_FILES = { picks:"mechi.html", mypicks:"mkeka.html", experts:"wataalamu.html", me:"mimi.html", adm:"adm.html" };
function switchTab(tab){
  if(PAGE_FILES[tab]) location.href = PAGE_FILES[tab];
}
// ADM is private: a normal user is bounced away before anything loads.
const sessionUser = currentUser();
if(location.pathname.split("/").pop().toLowerCase() === "adm.html"){
  if(!sessionUser || sessionUser.role !== "admin") location.href = "/mechi.html";
}
document.body.classList.toggle("is-admin", (sessionUser||{}).role === "admin");
function initPage(){
  const file = (location.pathname.split("/").pop() || "mechi.html").toLowerCase();
  let tab = "picks";
  if(file === "mkeka.html") tab = "mypicks";
  else if(file === "wataalamu.html") tab = "experts";
  else if(file === "mimi.html") tab = "me";
  else if(file === "adm.html") tab = "adm";
  document.querySelectorAll(".bottom-nav button").forEach(b=>b.classList.toggle("active", b.dataset.tab===tab));
  const u = currentUser();
  const name = u ? u.nickname : "";
  const msgs = {
    picks: `Habari, ${name}! Leo tumekuletea orodha hii ya match tafadhali chagua match zako na tengeneza mkeka wako sehemu ya "Mkeka".`,
    mypicks: `Habari, ${name}! Hapa unaweza kutengeneza na kuhariri mkeka wako.`,
    experts: `Habari, ${name}! Fuata wataalamu na tazama mikeka yao ya leo.`,
    me: `Habari, ${name}! Wasifu wako na machaguo ya wafuatwao.`
  };
  const helloEl = document.getElementById("hello");
  if(helloEl) helloEl.textContent = msgs[tab] || "";
  if(tab==="picks" && document.getElementById("picks-list")) loadPicks();
  if(tab==="mypicks" && document.getElementById("mypicks-available")) loadMyPicks();
  if(tab==="experts" && document.getElementById("experts-list")) loadExperts();
  if(tab==="me" && document.getElementById("profile")) loadMe();
}
initPage();

async function loadPicks(){
  const now = new Date();
  const dstr = localDateStr(now);
  let allToday = [];
  try { 
    allToday = await API.get("/api/predictions/allowed?date="+dstr+"&include_finished=true"); 
  } catch(e){ 
    allToday = []; 
  }
  const el = document.getElementById("picks-list");
  if(!allToday || !allToday.length){ el.innerHTML = "<div class='muted'>Hakuna machaguo leo.</div>"; return; }
  el.innerHTML = allToday.map(p=>{
    const md = parseDT(p.match_date);
    const started = md.getTime() <= now.getTime();
    // A match that has kicked off is live until the result is actually known;
    // only the outcome/status makes it "finished".
    const isFinished = p.status === "finished" || !!p.outcome;
    const isLive = !isFinished && (p.status === "live" || started);
    const stateLabel = isFinished
      ? "Imemalizika" + (p.outcome ? " · " + outcomeSw(p.outcome) : "")
      : isLive ? "Moja kwa moja" : "Inasubiri";
    return `
    <div class="pick-item">
      <div><b>${escapeHtml(p.home_team)}</b> vs <b>${escapeHtml(p.away_team)}</b></div>
      <div class="muted">Over 1.5 · Anza: ${fmtDate(p.match_date)} · Odds ${p.odds} · ${stateLabel}</div>
    </div>
  `;
  }).join("");
}

async function loadMyPicks(){
  // available: only today's not-yet-started matches
  let preds = await API.get("/api/predictions/allowed?date=" + localDateStr());
  const now = new Date();
  availablePreds = preds.filter(p=> {
    const md = parseDT(p.match_date);
    return md.getTime() > now.getTime() + 60000 && p.status !== "finished" && p.status !== "live";
  });
  const av = document.getElementById("mypicks-available");
  if(av){
    if(!availablePreds.length){
      av.innerHTML = "<div class='muted'>Hakuna mechi zinazoweza kuchaguliwa kwa mkeka mpya.</div>";
    }else{
      av.innerHTML = availablePreds.map(p=>`
        <div class="pick-item ${selected.has(p.id)?"selected":""}" data-id="${p.id}">
          <label style="display:flex;align-items:center;gap:10px;cursor:pointer;">
            <input type="checkbox" ${selected.has(p.id)?"checked":""} data-action="togglePick" data-id="${p.id}" style="width:18px;height:18px;">
            <div>
              <div><b>${escapeHtml(p.home_team)}</b> vs <b>${escapeHtml(p.away_team)}</b></div>
              <div class="muted">Over 1.5 · Odds ${p.odds} · Saa: ${fmtDate(p.match_date)} · Inasubiri</div>
            </div>
          </label>
        </div>
      `).join("");
    }
  }
  const saveBtn = document.getElementById("mypicks-save");
  if(saveBtn) saveBtn.textContent = editingPickId ? "Hifadhi mabadiliko" : "Hifadhi chaguo";
  updateOddsPreview();
  // history
  const history = await API.get("/api/picks");
  const h = document.getElementById("mypicks-history");
  // if first load, preload the latest editable pending pick
  if(!preloaded){
    preloaded = true;
    if(!editingPickId && !selected.size){
      const cur = history.find(p=>p.status==="pending" && p.legs.every(l=>l.status==="scheduled"));
      if(cur){
        const availIds = new Set(availablePreds.map(x=>x.id));
        const legs = cur.legs.map(l=>l.prediction_id).filter(x=>availIds.has(x));
        if(legs.length){ editingPickId = cur.id; selected = new Set(legs); return loadMyPicks(); }
      }
    }
  }
  if(!history.length){ h.innerHTML = "<div class='muted'>Hakuna machaguo bado.</div>"; return; }
  h.innerHTML = history.map(p=>{
    const editable = p.legs.every(l=>l.status==="scheduled");
    const accaStatus = pickStatusSw(p.status);
    const legDetails = p.legs.map((l,idx)=>{
      const sStatus = statusSw(l.status);
      const scoreTxt = l.score ? ` (${l.score})` : "";
      const sOutcome = l.outcome === "win" ? "✔ Imeshinda" + scoreTxt
        : l.outcome === "lose" ? "✘ Imepotea" + scoreTxt
        : l.outcome === "void" ? "⏸ Imesimamishwa (haijahesabiwa)"
        : sStatus;
      return `Mechi ${idx+1}: ${escapeHtml(l.home_team)} v ${escapeHtml(l.away_team)} | Saa: ${fmtDate(l.match_date)} | Odds: ${l.odds} | Hali: ${sOutcome}`;
    }).join("\n");
    return `
    <div class="pick-item">
      <div><b>${p.legs.map(l=>escapeHtml(l.home_team)+" v "+escapeHtml(l.away_team)).join(" + ")}</b></div>
      <div class="muted">Odds jumla: ${p.combined_odds} · ${fmtDay(p.created_at)} · Faida: ${fmtMoney(pickProfit(p))}</div>
      <details style="margin-top:8px">
        <summary style="cursor:pointer;font-weight:600">ACCA: ${accaStatus} | Angalia hali za kila mechi ▾</summary>
        <div style="margin-top:6px;padding:8px;background:#f9f9f9;border-radius:6px">
          ${p.legs.map((l,idx)=>`
            <div style="padding:4px 0;border-bottom:1px solid #eee">
              <div><b>${idx+1}. ${escapeHtml(l.home_team)} v ${escapeHtml(l.away_team)}</b></div>
              <div class="muted">Anza: ${fmtDate(l.match_date)} · Odds: ${l.odds}</div>
              <div>SINGLE: ${l.outcome === "win" ? "✔ IMESHINDA" + (l.score ? ` (${l.score})` : "") : l.outcome === "lose" ? "✘ IMEPOTEA" + (l.score ? ` (${l.score})` : "") : l.outcome === "void" ? "⏸ IMESIMAMISHWA (haijahesabiwa)" : statusSw(l.status)}</div>
            </div>
          `).join("")}
        </div>
      </details>
      <div style="margin-top:6px">
        ${editable?`<button class="btn secondary" data-action="editPick" data-id="${p.id}">Hariri</button>`:""}
      </div>
    </div>`;
  }).join("");
}

function togglePick(id){
  if(selected.has(id)) selected.delete(id); else selected.add(id);
  const el = document.querySelector(`#mypicks-available .pick-item[data-id="${id}"]`);
  if(el) el.classList.toggle("selected", selected.has(id));
  updateOddsPreview();
}

function updateOddsPreview(){
  const preds = availablePreds.filter(p=>selected.has(p.id));
  let odds = 1;
  preds.forEach(p=>odds*=p.odds);
  const msg = document.getElementById("mypicks-msg");
  if(msg) msg.textContent = `Vilivyochaguliwa ${selected.size} · Odds jumla ${odds.toFixed(2)}`;
}

async function submitMyPick(){
  const ids = Array.from(selected);
  if(!ids.length){ document.getElementById("mypicks-msg").textContent="Chagua angalau moja"; return; }
  const preds = availablePreds.filter(p=>selected.has(p.id));
  let odds = 1; preds.forEach(p=>odds*=p.odds);
  if(odds < 1.5 || odds > 6){ document.getElementById("mypicks-msg").textContent="Odds jumla lazima iwe 1.5-6.0 (sasa: "+odds.toFixed(2)+")"; return; }
  try{
    let done;
    if(editingPickId){
      await API.put("/api/picks/"+editingPickId, {prediction_ids: ids});
      editingPickId = null;
      selected.clear();
      done = "Imesasishwa";
    } else {
      await API.post("/api/picks", {prediction_ids: ids});
      selected.clear();
      done = "Imehifadhiwa";
    }
    await loadMyPicks();
    document.getElementById("mypicks-msg").textContent = done;
  }catch(e){ document.getElementById("mypicks-msg").textContent = e.message; }
}

async function editPick(id){
  const history = await API.get("/api/picks");
  const p = history.find(x=>x.id===id);
  if(!p) return;
  if(!availablePreds.length) availablePreds = await API.get("/api/predictions/allowed");
  const availIds = new Set(availablePreds.map(x=>x.id));
  editingPickId = id;
  selected = new Set(p.legs.map(l=>l.prediction_id).filter(x=>availIds.has(x)));
  const missing = p.legs.length - selected.size;
  if(location.pathname.endsWith("mkeka.html")){
    await loadMyPicks();
    if(missing>0) document.getElementById("mypicks-msg").textContent = "Baadhi ya mechi hazipatikani tena; zimeondolewa.";
  } else switchTab("mypicks");
}

async function loadExperts(){
  const experts = await API.get("/api/experts");
  const el = document.getElementById("experts-list");
  const cnt = document.getElementById("expert-count");
  const search = document.getElementById("expert-search");
  if(!experts.length){ if(el) el.innerHTML = "<div class='muted'>Hakuna wataalamu bado.</div>"; if(cnt) cnt.textContent="0 wataalamu"; return; }
  function render(q=""){
    const list = experts.filter(e=> !q || (e.nickname||"").toLowerCase().includes(q.toLowerCase()));
    if(cnt) cnt.textContent = list.length + " / " + experts.length + " wataalamu";
    if(!el) return;
    if(!list.length){ el.innerHTML = "<div class='muted'>Hakuna matokeo kwa utafutaji huu.</div>"; return; }
    el.innerHTML = list.map(e=>`
      <div class="expert-card">
        <div>
          <div><b>${escapeHtml(e.nickname)}</b></div>
          <div class="muted" style="margin:6px 0">
            <div style="display:flex;flex-wrap:wrap;gap:8px 12px;margin-top:4px">
              <span><b>Mechi moja</b> — Ushindi: ${e.single_won}, Poteza: ${e.single_lost}, Faida: ${Number(e.single_profit).toLocaleString(undefined,{maximumFractionDigits:2})} (stake 10,000)</span>
              <span><b>Mkeka</b> — Ushindi: ${e.combined_won}, Poteza: ${e.combined_lost}, Faida: ${Number(e.combined_profit).toLocaleString(undefined,{maximumFractionDigits:2})} (stake 10,000)</span>
            </div>
          </div>
        </div>
        <div>
          <div class="follow-row">
            ${e.is_following?`<button class="btn small secondary" data-action="unfollow" data-id="${e.id}">Acha kufuata</button>`:`<button class="btn small" ${e.can_follow?"":"disabled"} data-action="follow" data-id="${e.id}">Fuata</button>`}
            ${e.is_following?`<button class="btn small secondary" data-action="viewExpertPicks" data-id="${e.id}" data-nick="${escapeHtml(e.nickname)}">Tazama machaguo</button>`:""}
          </div>
          <div id="expert-picks-${e.id}"></div>
        </div>
      </div>
    `).join("");
  }
  if(search){ search.oninput = ()=>render(search.value); }
  // Keep the active search when the list is reloaded after follow/unfollow.
  render(search ? search.value : "");
}

async function follow(id){
  try{ await API.post("/api/follows", {user_id: id}); loadExperts(); }catch(e){ alert(e.message); }
}
async function unfollow(id){
  try{ await API.del("/api/follows/"+id); loadExperts(); loadMe(); }catch(e){ alert(e.message); }
}

async function viewExpertPicks(id, nickname){
  try{
    const picks = await API.get("/api/experts/"+id+"/picks");
    const el = document.getElementById("expert-picks-"+id);
    if(!picks.length){ el.innerHTML = "<div class='muted'>Hakuna machaguo leo.</div>"; return; }
    el.innerHTML = picks.map(p=>`
      <div class="pick-item">
        <div>${p.legs.map(l=>escapeHtml(l.home_team)+" v "+escapeHtml(l.away_team)).join(" + ")}</div>
        <div class="muted">Over 1.5 · Odds ${p.combined_odds} · ${pickStatusSw(p.status)} · Faida: ${fmtMoney(pickProfit(p))}</div>
      </div>
    `).join("");
  }catch(e){ alert(e.message); }
}

async function loadMe(){
  const u = currentUser();
  const profile = document.getElementById("profile");
  if(!u){ if(profile) profile.innerHTML = "<div class='muted'>Wasifu haupatikani. Tafadhali ingia tena.</div>"; return; }
  if(profile) profile.innerHTML = `
    <div style="display:flex;align-items:center;margin-bottom:8px">
      <span style="font-size:24px;margin-right:8px">${escapeHtml(u.profile_emoji||'⚽')}</span>
      <b>${escapeHtml(u.nickname)}</b>
    </div>
    <div class="muted">${u.email} · ${u.role==="admin"?"Msimamizi":"Mtumiaji"}</div>
    ${u.role==="admin"?'<div style="margin-top:8px"><a class="btn secondary" href="/admin.html">Paneli ya msimamizi</a></div>':""}
  `;
  const follows = await API.get("/api/follows/me");
  const el = document.getElementById("followed-odds");
  if(!follows.length){ el.innerHTML = "<div class='muted'>Hufuatii mtu yeyote.</div>"; return; }
  let html = "";
  for(const f of follows){
    html += `<div class="expert-card"><b>${escapeHtml(f.nickname)}</b>`;
    try{
      const picks = await API.get("/api/experts/"+f.id+"/picks");
      if(!picks.length) html += "<div class='muted'>Hakuna machaguo leo.</div>";
      else html += picks.map(p=>`
        <div class="pick-item">
          <div>${p.legs.map(l=>escapeHtml(l.home_team)+" v "+escapeHtml(l.away_team)).join(" + ")}</div>
          <div class="muted">Over 1.5 · Odds ${p.combined_odds} · ${pickStatusSw(p.status)} · Faida: ${fmtMoney(pickProfit(p))}</div>
        </div>
      `).join("");
    }catch(e){ html += `<div class='muted'>${escapeHtml(e.message)}</div>`; }
    html += "</div>";
  }
  el.innerHTML = html;
}

function logout(){
  API.setToken(null); setUser(null); location.href="/index.html";
}

// init handled by initPage() above
document.addEventListener("click", (e) => {
  const btn = e.target.closest && e.target.closest(".bottom-nav button");
  if(btn && btn.dataset.tab){ switchTab(btn.dataset.tab); }
});
document.addEventListener("click", (e) => {
  const btn = e.target.closest && e.target.closest("[data-action]");
  if(!btn) return;
  const action = btn.dataset.action;
  if(action === "editPick") editPick(btn.dataset.id);
  else if(action === "unfollow") unfollow(btn.dataset.id);
  else if(action === "follow") follow(btn.dataset.id);
  else if(action === "viewExpertPicks") viewExpertPicks(btn.dataset.id, btn.dataset.nick);
});
document.addEventListener("change", (e) => {
  const cb = e.target.closest && e.target.closest("[data-action='togglePick']");
  if(cb) togglePick(cb.dataset.id);
});
document.addEventListener("click", (e) => { const btn = e.target.closest && e.target.closest("[data-action]"); if(!btn) return; if(btn.dataset.action === "logout") logout(); if(btn.dataset.action === "submitMyPick") submitMyPick(); });

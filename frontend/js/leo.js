if(!requireAuth()) throw new Error("auth");
recordVisit();

function parseDT(d){
  if(!d) return new Date(NaN);
  const s = String(d);
  return new Date(/(Z|[+-]\d{2}:?\d{2})$/i.test(s) ? s : s + "Z");
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
function fmtMoney(n){ return Number(n).toLocaleString(undefined,{maximumFractionDigits:0}); }

const PAGE_FILES = { leo:"leo.html", malipo:"malipo.html", mimi:"mimi.html", historia:"historia.html" };
function switchTab(tab){
  if(PAGE_FILES[tab]) location.href = PAGE_FILES[tab];
}

const sessionUser = currentUser();
document.body.classList.toggle("is-admin", (sessionUser||{}).role === "admin");

function initPage(){
  const file = (location.pathname.split("/").pop() || "leo.html").toLowerCase();
  let tab = "leo";
  if(file === "malipo.html") tab = "malipo";
  else if(file === "mimi.html") tab = "mimi";
  else if(file === "historia.html") tab = "historia";
  document.querySelectorAll(".bottom-nav button").forEach(b=>b.classList.toggle("active", b.dataset.tab===tab));
  const u = currentUser();
  const name = u ? (u.phone_number || "") : "";
  const helloEl = document.getElementById("hello");
  if(helloEl) helloEl.textContent = `Habari! Leo tumekuletea mkeka wa machaguo 4.`;
}
initPage();

async function loadLeo(){
  const matchesEl = document.getElementById("leo-matches");
  const stakeEl = document.getElementById("leo-stake");
  const statusEl = document.getElementById("leo-status");
  const totalEl = document.getElementById("leo-total");

  // Check subscription status
  try {
    const sub = await API.get("/api/subscriptions/status");
    if(!sub.is_active && sessionUser && sessionUser.role !== "admin"){
      matchesEl.innerHTML = "<div class='card' style='padding:12px'><div style='color:red;font-weight:bold'>Usajili wako umeisha</div><p class='muted'>Lipa TZS 1,000 kwa wiki kupata machaguo ya kila siku.</p><a class='btn' href='/malipo.html'>Lipa Sasa</a></div>";
      if(stakeEl) stakeEl.textContent = "";
      if(statusEl) statusEl.textContent = "";
      if(totalEl) totalEl.textContent = "";
      return;
    }
  } catch(e){}

  try {
    const acc = await API.get("/api/accumulators/today");
    if(stakeEl) stakeEl.textContent = "";
    if(statusEl) statusEl.textContent = "";
    if(totalEl) totalEl.textContent = "";

    if(!acc){
      matchesEl.innerHTML = "<div class='muted'>Hakuna mkeka leo. Subiri admin kuunda.</div>";
      return;
    }

    if(stakeEl) stakeEl.textContent = `Stake (simulation): TZS ${fmtMoney(acc.stake_amount)}`;
    
    const statusColor = acc.status === "Won" ? "green" : acc.status === "Lost" ? "red" : "";
    const statusIcon = acc.status === "Won" ? "✔" : acc.status === "Lost" ? "✖" : "⏳";
    if(statusEl) statusEl.innerHTML = `<span style="color:${statusColor};font-weight:bold">${statusIcon} ${acc.status}</span>`;

    if(!acc.matches || !acc.matches.length){
      matchesEl.innerHTML = "<div class='muted'>Hakuna mechi zilizowekwa.</div>";
      return;
    }

    matchesEl.innerHTML = acc.matches.map((m, idx) => {
      const mStatusColor = m.status === "Won" ? "green" : m.status === "Lost" ? "red" : "";
      const mStatusIcon = m.status === "Won" ? "✔" : m.status === "Lost" ? "✖" : "⏳";
      return `
      <div class="card" style="padding:12px;margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:start;gap:8px">
          <div>
            <div style="font-size:15px"><b>${idx+1}. ${escapeHtml(m.home_team)}</b> <span style="color:#999">vs</span> <b>${escapeHtml(m.away_team)}</b></div>
            <div class="muted" style="margin-top:4px">Pick: <b>${escapeHtml(m.prediction)}</b> · Odds: ${m.match_odds}</div>
          </div>
          <div style="text-align:right">
            <span style="color:${mStatusColor};font-weight:bold">${mStatusIcon} ${m.status}</span>
          </div>
        </div>
        <div class="muted" style="margin-top:8px;font-size:13px">${escapeHtml(m.analysis_text)}</div>
      </div>
      `;
    }).join("");

    if(totalEl) totalEl.textContent = `Jumla ya Odds: ${acc.total_odds}`;
  } catch(e){
    matchesEl.innerHTML = "<div class='muted'>Hitilafu: " + escapeHtml(e.message) + "</div>";
  }
}

function escapeHtml(s){ return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }

loadLeo();

document.addEventListener("click", (e) => {
  const btn = e.target.closest && e.target.closest(".bottom-nav button");
  if(btn && btn.dataset.tab){ switchTab(btn.dataset.tab); }
});
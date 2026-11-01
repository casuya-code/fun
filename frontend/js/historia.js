if(!requireAuth()) throw new Error("auth");
recordVisit();

const PAGE_FILES = { leo:"leo.html", malipo:"malipo.html", mimi:"mimi.html", historia:"historia.html" };
function switchTab(tab){
  if(PAGE_FILES[tab]) location.href = PAGE_FILES[tab];
}

const sessionUser = currentUser();
document.body.classList.toggle("is-admin", (sessionUser||{}).role === "admin");

function initPage(){
  const file = (location.pathname.split("/").pop() || "historia.html").toLowerCase();
  let tab = "historia";
  document.querySelectorAll(".bottom-nav button").forEach(b=>b.classList.toggle("active", b.dataset.tab===tab));
}
initPage();

let currentFilter = 7;

async function loadHistoria(days){
  currentFilter = days;
  document.querySelectorAll("[data-filter]").forEach(b=>b.classList.toggle("secondary", parseInt(b.dataset.filter) !== days));
  try {
    const data = await API.get("/api/accumulators/history?days=" + days);
    const summaryEl = document.getElementById("summary");
    const listEl = document.getElementById("history-list");

    if(data.summary){
      summaryEl.textContent = `Jumla: ${data.summary.total} | Won: ${data.summary.won}`;
    }

    const accs = data.accumulators || [];
    if(!accs.length){
      listEl.innerHTML = "<div class='muted'>Hakuna historia bado.</div>";
      return;
    }

    listEl.innerHTML = accs.map(a => {
      const statusColor = a.status === "Won" ? "green" : a.status === "Lost" ? "red" : "";
      const statusIcon = a.status === "Won" ? "✔" : a.status === "Lost" ? "✖" : "⏳";
      const dateStr = new Date(a.accumulator_date).toLocaleDateString();
      return `
      <div class="card" style="padding:12px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center">
        <div>
          <div><b>${dateStr}</b></div>
          <div style="color:${statusColor}">${statusIcon} ${a.status}</div>
        </div>
        <button class="btn small secondary" data-action="see" data-id="${a.id}">See</button>
      </div>
      `;
    }).join("");

    // Attach see handlers
    document.querySelectorAll("[data-action='see']").forEach(btn => {
      btn.addEventListener("click", () => seeAccumulator(btn.dataset.id));
    });
  } catch(e){
    document.getElementById("history-list").innerHTML = "<div class='muted'>Hitilafu: " + escapeHtml(e.message) + "</div>";
  }
}

async function seeAccumulator(id){
  try {
    const acc = await API.get("/api/accumulators/" + id);
    document.getElementById("modal-title").textContent = new Date(acc.accumulator_date).toLocaleDateString();
    const content = (acc.matches || []).map((m, idx) => {
      const mStatusColor = m.status === "Won" ? "green" : m.status === "Lost" ? "red" : "";
      const mStatusIcon = m.status === "Won" ? "✔" : m.status === "Lost" ? "✖" : "⏳";
      return `
      <div style="padding:8px;border-bottom:1px solid #eee">
        <div><b>${idx+1}. ${escapeHtml(m.home_team)} vs ${escapeHtml(m.away_team)}</b></div>
        <div class="muted">Pick: ${escapeHtml(m.prediction)} · Odds: ${m.match_odds}</div>
        <div class="muted" style="font-size:12px">${escapeHtml(m.analysis_text)}</div>
        <div style="color:${mStatusColor}">${mStatusIcon} ${m.status}</div>
      </div>
      `;
    }).join("");
    document.getElementById("modal-content").innerHTML = content + `<div style="margin-top:8px;font-weight:bold">Jumla Odds: ${acc.total_odds}</div>`;
    document.getElementById("modal").style.display = "block";
  } catch(e){
    alert("Hitilafu: " + e.message);
  }
}

function closeModal(){
  document.getElementById("modal").style.display = "none";
}

function escapeHtml(s){ return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }

// Filter buttons
document.querySelectorAll("[data-filter]").forEach(btn => {
  btn.addEventListener("click", () => loadHistoria(parseInt(btn.dataset.filter)));
});

loadHistoria(7);

document.addEventListener("click", (e) => {
  const btn = e.target.closest && e.target.closest(".bottom-nav button");
  if(btn && btn.dataset.tab){ switchTab(btn.dataset.tab); }
});
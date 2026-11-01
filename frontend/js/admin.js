if(!requireAuth()) throw new Error("auth");
const sessionUser = currentUser();
if(!sessionUser || sessionUser.role !== "admin"){ location.href="/leo.html"; throw new Error("not-admin"); }

recordVisit();

function escapeHtml(s){ return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }

let currentTab = "watumiaji";

function switchAdminTab(tab){
  currentTab = tab;
  document.querySelectorAll("[data-tab]").forEach(b=>b.classList.toggle("secondary", b.dataset.tab !== tab));
  loadTab(tab);
}

async function loadTab(tab){
  const el = document.getElementById("admin-content");
  el.innerHTML = "<div class='muted'>Inapakia...</div>";
  try {
    if(tab === "watumiaji") await loadWatumiaji(el);
    else if(tab === "mkeka") await loadMkeka(el);
    else if(tab === "adm") await loadADM(el);
    else if(tab === "machaguo") await loadMachaguo(el);
    else if(tab === "mechi") await loadMechi(el);
  } catch(e){
    el.innerHTML = "<div class='muted'>Hitilafu: " + escapeHtml(e.message) + "</div>";
  }
}

// === WATUMIAJI (List of Users) ===
async function loadWatumiaji(el){
  const users = await API.get("/api/admin/users");
  if(!users.length){ el.innerHTML = "<div class='muted'>Hakuna watumiaji.</div>"; return; }
  el.innerHTML = users.map(u => `
    <div class="card" style="padding:12px;margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
        <div>
          <b>${escapeHtml(u.phone_number)}</b>
          <div class="muted">${u.role} · ${new Date(u.created_at).toLocaleDateString()}</div>
          ${u.subscription ? `<div class="muted">Usajili: ${u.subscription.status} · Inaisha: ${u.subscription.expires_at ? new Date(u.subscription.expires_at).toLocaleString() : "-"}</div>` : ""}
        </div>
        <button class="btn small" data-action="activate-sub" data-uid="${u.id}">Amilisha (7 siku)</button>
      </div>
    </div>
  `).join("");
  // Attach handlers
  el.querySelectorAll("[data-action='activate-sub']").forEach(btn => {
    btn.addEventListener("click", () => activateSub(btn.dataset.uid));
  });
}

async function activateSub(uid){
  try {
    await API.post("/api/subscriptions/activate", {user_id: uid});
    alert("Usajili umeamilishwa!");
    loadTab("watumiaji");
  } catch(e){ alert("Hitilafu: " + e.message); }
}

// === MKEKA (Accumulator Management) ===
async function loadMkeka(el){
  const accs = await API.get("/api/admin/accumulators");
  let html = `<div style="margin-bottom:12px"><button class="btn" data-action="new-acc">+ Mkeka Mpya</button></div>`;
  if(!accs.length){ html += "<div class='muted'>Hakuna mkeka bado.</div>"; }
  else {
    html += accs.map(a => `
      <div class="card" style="padding:12px;margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
          <div>
            <b>${a.accumulator_date}</b>
            <div class="muted">Odds: ${a.total_odds} · Mechi: ${a.match_count} · ${a.status}</div>
            <div class="muted">Visible: ${a.is_visible ? "✔" : "✖"}</div>
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn small secondary" data-action="toggle-vis" data-id="${a.id}">${a.is_visible ? "Ficha" : "Onyesha"}</button>
            <button class="btn small secondary" data-action="delete-acc" data-id="${a.id}">Futa</button>
          </div>
        </div>
      </div>
    `).join("");
  }
  el.innerHTML = html;
  el.querySelectorAll("[data-action='toggle-vis']").forEach(btn => {
    btn.addEventListener("click", () => toggleVis(btn.dataset.id));
  });
  el.querySelectorAll("[data-action='delete-acc']").forEach(btn => {
    btn.addEventListener("click", () => deleteAcc(btn.dataset.id));
  });
  const newBtn = el.querySelector("[data-action='new-acc']");
  if(newBtn) newBtn.addEventListener("click", () => showNewAccForm(el));
}

async function toggleVis(id){
  try { await API.post("/api/admin/accumulators/" + id + "/toggle-visibility"); loadTab("mkeka"); }
  catch(e){ alert("Hitilafu: " + e.message); }
}
async function deleteAcc(id){
  if(!confirm("Futa mkeka huu?")) return;
  try { await API.del("/api/admin/accumulators/" + id); loadTab("mkeka"); }
  catch(e){ alert("Hitilafu: " + e.message); }
}

function showNewAccForm(el){
  el.innerHTML = `
    <div class="card" style="padding:12px">
      <h3>Mkeka Mpya</h3>
      <label class="label">Tarehe (YYYY-MM-DD)</label>
      <input id="acc-date" class="input" type="date">
      <label class="label">Jumla ya Odds</label>
      <input id="acc-odds" class="input" type="number" step="0.01" value="4.00">
      <label class="label">Stake (TZS)</label>
      <input id="acc-stake" class="input" type="number" value="5000">
      <button class="btn" data-action="create-acc">Unda Mkeka</button>
      <button class="btn secondary" data-action="cancel-acc" style="margin-left:8px">Ghairi</button>
      <div id="acc-msg" class="muted" style="margin-top:8px"></div>
    </div>
  `;
  el.querySelector("[data-action='create-acc']").addEventListener("click", createAcc);
  el.querySelector("[data-action='cancel-acc']").addEventListener("click", () => loadTab("mkeka"));
}

async function createAcc(){
  try {
    const data = {
      accumulator_date: document.getElementById("acc-date").value,
      total_odds: parseFloat(document.getElementById("acc-odds").value),
      stake_amount: parseFloat(document.getElementById("acc-stake").value),
    };
    const acc = await API.post("/api/accumulators", data);
    document.getElementById("acc-msg").textContent = "Mkeka umeundwa! ID: " + acc.id;
    setTimeout(() => loadTab("mkeka"), 1500);
  } catch(e){ document.getElementById("acc-msg").textContent = "Hitilafu: " + e.message; }
}

// === ADM (Engine Matches from FootyStats) ===
async function loadADM(el){
  try {
    const matches = await API.get("/api/engine/matches");
    let html = `<div style="margin-bottom:12px"><button class="btn" data-action="sync-engine">Sync FootyStats</button></div>`;
    if(!matches.length){ html += "<div class='muted'>Hakuna mechi. Bonyeza Sync.</div>"; }
    else {
      html += matches.map(m => `
        <div class="card" style="padding:10px;margin-bottom:6px">
          <div style="display:flex;justify-content:space-between">
            <div>
              <b>${escapeHtml(m.home_team)}</b> vs <b>${escapeHtml(m.away_team)}</b>
              <div class="muted" style="font-size:12px">${m.match_date} · Over1.5: ${m.over15_pct || "-"}% · Avg: ${m.avg_goals || "-"}</div>
            </div>
            <div style="text-align:right">
              <div style="font-weight:bold">${m.odds}</div>
              <div class="muted" style="font-size:11px">${m.used ? "Imetumika" : "Haijatumika"}</div>
            </div>
          </div>
        </div>
      `).join("");
    }
    el.innerHTML = html;
    const syncBtn = el.querySelector("[data-action='sync-engine']");
    if(syncBtn) syncBtn.addEventListener("click", async () => {
      try { const r = await API.post("/api/engine/sync"); alert("Synced: " + r.imported + " new, " + r.total + " total"); loadTab("adm"); }
      catch(e){ alert("Hitilafu: " + e.message); }
    });
  } catch(e){
    el.innerHTML = "<div class='muted'>Hitilafu: " + escapeHtml(e.message) + "</div>";
  }
}

// === MACHAGUO (Match Management) ===
async function loadMachaguo(el){
  const accs = await API.get("/api/admin/accumulators");
  if(!accs.length){ el.innerHTML = "<div class='muted'>Hakuna mkeka. Unda mkeka kwanza.</div>"; return; }
  let html = `<div style="margin-bottom:12px">
    <label class="label">Chagua Mkeka</label>
    <select id="machaguo-acc" class="input">
      ${accs.map(a => `<option value="${a.id}">${a.accumulator_date} (${a.match_count} mechi)</option>`).join("")}
    </select>
  </div>
  <div id="machaguo-matches"></div>
  <div style="margin-top:12px">
    <button class="btn" data-action="show-add-match">+ Ongeza Mechi</button>
  </div>
  <div id="add-match-form" style="display:none;margin-top:12px"></div>`;
  el.innerHTML = html;
  const sel = document.getElementById("machaguo-acc");
  sel.addEventListener("change", () => loadMatchesForAcc(sel.value));
  loadMatchesForAcc(sel.value);
  el.querySelector("[data-action='show-add-match']").addEventListener("click", () => showAddMatchForm(sel.value));
}

async function loadMatchesForAcc(accId){
  const container = document.getElementById("machaguo-matches");
  try {
    const matches = await API.get("/api/matches/" + accId);
    if(!matches.length){ container.innerHTML = "<div class='muted'>Hakuna mechi bado.</div>"; return; }
    container.innerHTML = matches.map(m => `
      <div class="card" style="padding:10px;margin-bottom:6px">
        <div style="display:flex;justify-content:space-between">
          <div>
            <b>${escapeHtml(m.home_team)} vs ${escapeHtml(m.away_team)}</b>
            <div class="muted" style="font-size:12px">Pick: ${escapeHtml(m.prediction)} · Odds: ${m.match_odds}</div>
            <div class="muted" style="font-size:11px">${escapeHtml(m.analysis_text)}</div>
          </div>
          <div style="display:flex;gap:4px;align-items:center">
            <span style="color:${m.status==='Won'?'green':m.status==='Lost'?'red':''}">${m.status==='Won'?'✔':m.status==='Lost'?'✖':'⏳'} ${m.status}</span>
          </div>
        </div>
      </div>
    `).join("");
  } catch(e){ container.innerHTML = "<div class='muted'>Hitilafu: " + escapeHtml(e.message) + "</div>"; }
}

function showAddMatchForm(accId){
  const form = document.getElementById("add-match-form");
  form.style.display = "block";
  form.innerHTML = `
    <div class="card" style="padding:12px">
      <h3>Ongeza Mechi</h3>
      <label class="label">Timu ya Nyumbani</label>
      <input id="m-home" class="input" type="text">
      <label class="label">Timu ya Ugenini</label>
      <input id="m-away" class="input" type="text">
      <label class="label">Utabiri (Prediction)</label>
      <input id="m-pred" class="input" type="text" placeholder="Over 1.5">
      <label class="label">Odds</label>
      <input id="m-odds" class="input" type="number" step="0.01" value="1.50">
      <label class="label">Uchambuzi (Analysis)</label>
      <textarea id="m-analysis" class="input" rows="3"></textarea>
      <button class="btn" data-action="submit-match" data-acc="${accId}">Hifadhi Mechi</button>
      <button class="btn secondary" data-action="cancel-match" style="margin-left:8px">Ghairi</button>
      <div id="match-msg" class="muted" style="margin-top:8px"></div>
    </div>
  `;
  form.querySelector("[data-action='submit-match']").addEventListener("click", () => submitMatch(accId));
  form.querySelector("[data-action='cancel-match']").addEventListener("click", () => { form.style.display="none"; form.innerHTML=""; });
}

async function submitMatch(accId){
  try {
    const data = {
      accumulator_id: accId,
      home_team: document.getElementById("m-home").value,
      away_team: document.getElementById("m-away").value,
      prediction: document.getElementById("m-pred").value,
      match_odds: parseFloat(document.getElementById("m-odds").value),
      analysis_text: document.getElementById("m-analysis").value,
    };
    await API.post("/api/matches", data);
    document.getElementById("match-msg").textContent = "Mechi imehifadhiwa!";
    document.getElementById("add-match-form").style.display = "none";
    loadMatchesForAcc(accId);
  } catch(e){ document.getElementById("match-msg").textContent = "Hitilafu: " + e.message; }
}

// === MECHI (Match List) ===
async function loadMechi(el){
  const accs = await API.get("/api/admin/accumulators");
  if(!accs.length){ el.innerHTML = "<div class='muted'>Hakuna mkeka bado.</div>"; return; }
  let html = `<div style="margin-bottom:12px">
    <label class="label">Chagua Mkeka</label>
    <select id="mechi-acc" class="input">
      ${accs.map(a => `<option value="${a.id}">${a.accumulator_date} (${a.match_count} mechi)</option>`).join("")}
    </select>
  </div>
  <div id="mechi-list"></div>`;
  el.innerHTML = html;
  const sel = document.getElementById("mechi-acc");
  sel.addEventListener("change", () => loadMatchesForAcc2(sel.value));
  loadMatchesForAcc2(sel.value);
}

async function loadMatchesForAcc2(accId){
  const container = document.getElementById("mechi-list");
  try {
    const matches = await API.get("/api/matches/" + accId);
    if(!matches.length){ container.innerHTML = "<div class='muted'>Hakuna mechi bado.</div>"; return; }
    container.innerHTML = matches.map(m => `
      <div class="card" style="padding:10px;margin-bottom:6px">
        <div style="display:flex;justify-content:space-between">
          <div>
            <b>${escapeHtml(m.home_team)} vs ${escapeHtml(m.away_team)}</b>
            <div class="muted" style="font-size:12px">Pick: ${escapeHtml(m.prediction)} · Odds: ${m.match_odds} · ${m.status}</div>
          </div>
        </div>
      </div>
    `).join("");
  } catch(e){ container.innerHTML = "<div class='muted'>Hitilafu: " + escapeHtml(e.message) + "</div>"; }
}

// Init
document.querySelectorAll("[data-tab]").forEach(btn => {
  btn.addEventListener("click", () => switchAdminTab(btn.dataset.tab));
});
switchAdminTab("watumiaji");
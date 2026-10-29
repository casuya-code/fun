/* Betva — Hali ya Mfumo (System Status)
   Kila hali inatokana na majibu halisi ya HTTP kutoka kwa API.
   Hakuna hali iliyowekwewima (hardcoded). */

const CHECKS = [
  { name: "Tovuti (Frontend)",        url: "/",                          db: false },
  { name: "CSS ya Mfumo",             url: "/css/style.css",             db: false },
  { name: "JS ya Mfumo",              url: "/js/app.js",                 db: false },
  { name: "API: Matembezi ya Wageni", url: "/api/visitor-stats",         db: true  },
  { name: "API: Utabiri",             url: "/api/predictions/allowed",   db: false },
  { name: "API: Wataalamu",           url: "/api/experts",               db: false },
  { name: "API: Mikeka",              url: "/api/picks",                 db: false },
  { name: "API: Auth (me)",           url: "/api/auth/me",               db: false },
];

function classify(status) {
  if (status >= 200 && status < 300) return { st: "up",   label: "Inafanya kazi" };
  if (status === 401 || status === 403) return { st: "up", label: "Imefunguka (inahitaji kuingia)" };
  if (status === 404) return { st: "down", label: "Haipatikani (404)" };
  if (status >= 500)  return { st: "down", label: "Hitilafu ya server (" + status + ")" };
  if (status === 429) return { st: "warn", label: "Vikomo vya mwitikio (429)" };
  return { st: "warn", label: "Hali isiyotarajiwa (" + status + ")" };
}

function msClass(ms) {
  if (ms <= 300) return "fast";
  if (ms <= 1000) return "mid";
  return "slow";
}

async function checkOne(c) {
  const t0 = performance.now();
  const headers = {};
  const token = localStorage.getItem("token");
  if (token) headers["Authorization"] = "Bearer " + token;
  try {
    const res = await fetch(c.url, { method: "GET", cache: "no-store", headers });
    const ms = Math.round(performance.now() - t0);
    const cls = classify(res.status);
    let extra = "";
    if (c.db && res.ok) {
      try {
        const j = await res.json();
        extra = "· Wageni leo: " + (j.today ?? "-") + " · Jumla: " + (j.total ?? "-");
      } catch (e) {}
    }
    return { ...c, ...cls, code: res.status, ms, extra };
  } catch (e) {
    const ms = Math.round(performance.now() - t0);
    return { ...c, st: "down", label: "Haiwezi kufikiwa", code: "ERR", ms, extra: "" };
  }
}

function render(results, when) {
  const grid = document.getElementById("statusGrid");
  grid.innerHTML = "";
  let up = 0;
  for (const r of results) {
    if (r.st === "up") up++;
    const card = document.createElement("div");
    card.className = "status-card " + r.st;
    card.innerHTML =
      '<div class="row1">' +
        '<span class="name"><span class="dot ' + r.st + '"></span> ' + r.name + "</span>" +
        '<span class="badge-status ' + r.st + '">' + r.label + "</span>" +
      "</div>" +
      '<div class="desc">' + r.url + "</div>" +
      '<div class="row2">' +
        '<span class="ms ' + msClass(r.ms) + '">' + r.ms + " ms</span>" +
        '<span class="http-code">HTTP ' + r.code + (r.extra ? " " + r.extra : "") + "</span>" +
      "</div>";
    grid.appendChild(card);
  }

  const total = results.length;
  const banner = document.getElementById("overall");
  const text = document.getElementById("overallText");
  const down = total - up;
  banner.className = "status-banner " + (down === 0 ? "up" : up > 0 ? "down" : "down");
  banner.querySelector(".big").textContent = down === 0 ? "✅" : "🔴";
  text.textContent = down === 0
    ? "Mfumo mzima uko safi — huduma " + up + "/" + total + " zote zinafanya kazi."
    : "Kuna hitilafu — huduma " + up + "/" + total + " zinafanya kazi, " + down + " hazifanyi kazi.";

  document.getElementById("checkedAt").textContent =
    "Iliaguliwa: " + when.toLocaleTimeString("sw-TZ") + " · inajasishwa kila sekunde 30";
}

function renderMini(visits) {
  const box = document.getElementById("miniStats");
  if (!visits) { box.innerHTML = ""; return; }
  box.innerHTML =
    '<div class="mini"><div class="num">' + (visits.today ?? "-") + '</div><div class="lbl">Matembezi leo</div></div>' +
    '<div class="mini"><div class="num">' + (visits.yesterday ?? "-") + '</div><div class="lbl">Jana</div></div>' +
    '<div class="mini"><div class="num">' + (visits.week ?? "-") + '</div><div class="lbl">Wiki hii</div></div>' +
    '<div class="mini"><div class="num">' + (visits.total ?? "-") + '</div><div class="lbl">Jumla</div></div>';
}

async function runChecks() {
  const btn = document.getElementById("refreshBtn");
  btn.disabled = true;
  const results = await Promise.all(CHECKS.map(checkOne));
  render(results, new Date());
  const v = results.find(r => r.url === "/api/visitor-stats");
  if (v && v.st === "up") {
    try {
      const j = await (await fetch("/api/visitor-stats", { cache: "no-store" })).json();
      renderMini(j);
    } catch (e) {}
  }
  btn.disabled = false;
}

document.getElementById("refreshBtn").addEventListener("click", runChecks);
runChecks();
setInterval(runChecks, 30000);

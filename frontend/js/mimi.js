if(!requireAuth()) throw new Error("auth");
recordVisit();

const PAGE_FILES = { leo:"leo.html", malipo:"malipo.html", mimi:"mimi.html", historia:"historia.html" };
function switchTab(tab){
  if(PAGE_FILES[tab]) location.href = PAGE_FILES[tab];
}

const sessionUser = currentUser();
document.body.classList.toggle("is-admin", (sessionUser||{}).role === "admin");

function initPage(){
  const file = (location.pathname.split("/").pop() || "mimi.html").toLowerCase();
  let tab = "mimi";
  document.querySelectorAll(".bottom-nav button").forEach(b=>b.classList.toggle("active", b.dataset.tab===tab));
  const u = currentUser();
  const name = u ? (u.phone_number || "") : "";
  const helloEl = document.getElementById("hello");
  if(helloEl) helloEl.textContent = `Habari, ${name}!`;
}
initPage();

async function loadMimi(){
  try {
    const u = await API.get("/api/auth/me");
    const profileEl = document.getElementById("profile");
    const sub = u.subscription || {};
    const isActive = sub.status === "Hai";
    const statusColor = isActive ? "green" : "red";
    const statusIcon = isActive ? "✔" : "✖";

    profileEl.innerHTML = `
      <div style="display:flex;align-items:center;margin-bottom:8px">
        <span style="font-size:24px;margin-right:8px">👤</span>
        <b>${escapeHtml(u.phone_number)}</b>
      </div>
      <div class="muted">${u.role === "admin" ? "Msimamizi" : "Mteja"}</div>
      <div style="margin-top:12px">
        <div style="color:${statusColor};font-weight:bold">${statusIcon} Usajili: ${sub.status || "Imeisha"}</div>
        ${sub.expires_at ? `<div class="muted">Inaisha: ${new Date(sub.expires_at).toLocaleString()}</div>` : ""}
      </div>
      ${u.role === "admin" ? '<div style="margin-top:12px"><a class="btn secondary" href="/admin.html">Paneli ya msimamizi</a></div>' : ""}
      <div style="margin-top:12px">
        <button class="btn secondary" data-action="logout">Toka (Logout)</button>
      </div>
    `;
  } catch(e){
    document.getElementById("profile").innerHTML = "<div class='muted'>Hitilafu: " + escapeHtml(e.message) + "</div>";
  }
}

function escapeHtml(s){ return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }

function logout(){
  API.setToken(null); setUser(null); location.href="/index.html";
}

loadMimi();

document.addEventListener("click", (e) => {
  const btn = e.target.closest && e.target.closest(".bottom-nav button");
  if(btn && btn.dataset.tab){ switchTab(btn.dataset.tab); }
  const abtn = e.target.closest && e.target.closest("[data-action]");
  if(abtn && abtn.dataset.action === "logout") logout();
});
if(!requireAuth()) throw new Error("auth");


const PAGE_FILES = { leo:"leo.html", malipo:"malipo.html", mimi:"mimi.html", historia:"historia.html" };
function switchTab(tab){
  if(PAGE_FILES[tab]) location.href = PAGE_FILES[tab];
}

const sessionUser = currentUser();
document.body.classList.toggle("is-admin", (sessionUser||{}).role === "admin");

function initPage(){
  const file = (location.pathname.split("/").pop() || "malipo.html").toLowerCase();
  let tab = "malipo";
  document.querySelectorAll(".bottom-nav button").forEach(b=>b.classList.toggle("active", b.dataset.tab===tab));
  const u = currentUser();
  const name = u ? (u.phone_number || "") : "";
  const helloEl = document.getElementById("hello");
  if(helloEl) helloEl.textContent = `Habari, ${name}!`;
}
initPage();

async function loadMalipo(){
  try {
    const s = await API.get("/api/subscriptions/status");
    const statusEl = document.getElementById("sub-status");
    const instrEl = document.getElementById("payment-instructions");

    if(s.is_active){
      statusEl.innerHTML = `<div style="color:green;font-weight:bold">✔ Usajili: Hai (Active)</div><div class="muted">Inaisha: ${new Date(s.expires_at).toLocaleString()}</div>`;
    } else {
      statusEl.innerHTML = `<div style="color:red;font-weight:bold">✖ Usajili: Imeisha (Expired)</div>`;
    }

    instrEl.innerHTML = `
      <div class="card" style="padding:12px;margin-top:12px">
        <h3>Jinsi ya Kulipa</h3>
        <p>1. Fungua M-Pesa kwenye simu yako</p>
        <p>2. Tuma TZS 4,500 kwa namba: <b>07XXXXXXXX</b></p>
        <p>3. Tuma ujumbe (SMS) ukiweka namba yako ya simu iliyosajiliwa</p>
        <p>4. Subiri admin kuthibitisha malipo (kwa kawaida ndani ya saa 24)</p>
        <p class="muted" style="margin-top:8px">Baada ya kuthibitishwa, akaunti yako itaamilishwa hadi Jumapili 18:59.</p>
      </div>
    `;
  } catch(e){
    document.getElementById("sub-status").innerHTML = "<div class='muted'>Hitilafu: " + e.message + "</div>";
  }
}

loadMalipo();

document.addEventListener("click", (e) => {
  const btn = e.target.closest && e.target.closest(".bottom-nav button");
  if(btn && btn.dataset.tab){ switchTab(btn.dataset.tab); }
});
(async()=>{ await recordVisit(); try{const s=await API.get("/api/visitor-stats");document.getElementById("footer").textContent=`Ziara: L:${s.today} · Jumla:${s.total}`;}catch(e){} })();
const token = new URLSearchParams(location.search).get("token");
async function doReset(){
  try{
    await API.post("/api/auth/reset", {token, new_password: document.getElementById("pw").value});
    document.getElementById("msg").textContent = "Nenosiri limesasishwa. Unaweza kuingia.";
  }catch(e){ document.getElementById("msg").textContent = e.message; }
}

document.addEventListener("click", (e) => { const btn = e.target.closest && e.target.closest("[data-action]"); if(btn && btn.dataset.action === "doReset") doReset(); });
document.addEventListener("keydown", (e) => { if(e.key === "Enter") doReset(); });

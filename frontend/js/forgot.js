(async()=>{ await recordVisit(); try{const s=await API.get("/api/visitor-stats");document.getElementById("footer").textContent=`Ziara: L:${s.today} · Jumla:${s.total}`;}catch(e){} })();
async function doForgot(){
  try{
    const data = await API.post("/api/auth/forgot", {email: document.getElementById("email").value});
    let m = data.message;
    if(data.reset_url){ m += " (dev) " + data.reset_url; }
    document.getElementById("msg").textContent = m;
  }catch(e){ document.getElementById("msg").textContent = e.message; }
}

document.addEventListener("click", (e) => { const btn = e.target.closest && e.target.closest("[data-action]"); if(btn && btn.dataset.action === "doForgot") doForgot(); });
document.addEventListener("keydown", (e) => { if(e.key === "Enter") doForgot(); });

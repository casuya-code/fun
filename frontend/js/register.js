(async()=>{ await recordVisit(); try{const s=await API.get("/api/visitor-stats");document.getElementById("footer").textContent=`Ziara: J:${s.yesterday} L:${s.today} W:${s.week} M:${s.month} Y:${s.year} · Jumla:${s.total}`;}catch(e){} })();
async function doReg(){
  try{
    const data = await API.post("/api/auth/register", {email: document.getElementById("email").value, password: document.getElementById("password").value, nickname: document.getElementById("nickname").value});
    API.setToken(data.access_token);
    setUser(data.user);
    location.href = "/mechi.html";
  }catch(e){ document.getElementById("msg").textContent = e.message; }
}

document.addEventListener("click", (e) => { const btn = e.target.closest && e.target.closest("[data-action]"); if(btn && btn.dataset.action === "doReg") doReg(); });
document.addEventListener("keydown", (e) => { if(e.key === "Enter") doReg(); });

(async()=>{ await recordVisit(); try{const s=await API.get("/api/visitor-stats");document.getElementById("footer").textContent=`Ziara: L:${s.today} · Jumla:${s.total}`;}catch(e){} })();
async function doLogin(){
  try{
    const data = await API.post("/api/auth/login", {email: document.getElementById("email").value, password: document.getElementById("password").value});
    API.setToken(data.access_token);
    setUser(data.user);
    location.href = "/mechi.html";
  }catch(e){ document.getElementById("msg").textContent = e.message; }
}

document.addEventListener("click", (e) => { const btn = e.target.closest && e.target.closest("[data-action]"); if(btn && btn.dataset.action === "doLogin") doLogin(); });
document.addEventListener("keydown", (e) => { if(e.key === "Enter") doLogin(); });

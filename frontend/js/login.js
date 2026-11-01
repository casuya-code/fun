(async()=>{ })();
async function doLogin(){
  try{
    const data = await API.post("/api/auth/login", {phone_number: document.getElementById("phone").value, password: document.getElementById("password").value});
    API.setToken(data.access_token);
    setUser(data.user);
    location.href = "/leo.html";
  }catch(e){ document.getElementById("msg").textContent = e.message; }
}

document.addEventListener("click", (e) => { const btn = e.target.closest && e.target.closest("[data-action]"); if(btn && btn.dataset.action === "doLogin") doLogin(); });
document.addEventListener("keydown", (e) => { if(e.key === "Enter") doLogin(); });
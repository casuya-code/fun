async function doReset(){
  try{
    const data = await API.post("/api/auth/reset", {token: document.getElementById("otp").value, new_password: document.getElementById("password").value});
    document.getElementById("msg").textContent = data.message;
    setTimeout(() => location.href = "/login.html", 2000);
  }catch(e){ document.getElementById("msg").textContent = e.message; }
}

document.addEventListener("click", (e) => { const btn = e.target.closest && e.target.closest("[data-action]"); if(btn && btn.dataset.action === "doReset") doReset(); });
document.addEventListener("keydown", (e) => { if(e.key === "Enter") doReset(); });
(async()=>{ await recordVisit(); })();
async function doForgot(){
  try{
    const data = await API.post("/api/auth/forgot", {phone_number: document.getElementById("phone").value});
    let m = data.message;
    if(data.otp_dev){ m += " (dev) OTP: " + data.otp_dev; }
    document.getElementById("msg").textContent = m;
  }catch(e){ document.getElementById("msg").textContent = e.message; }
}

document.addEventListener("click", (e) => { const btn = e.target.closest && e.target.closest("[data-action]"); if(btn && btn.dataset.action === "doForgot") doForgot(); });
document.addEventListener("keydown", (e) => { if(e.key === "Enter") doForgot(); });
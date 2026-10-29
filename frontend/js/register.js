(async()=>{ await recordVisit(); try{const s=await API.get("/api/visitor-stats");document.getElementById("footer").textContent=`Ziara: L:${s.today} · Jumla:${s.total}`;}catch(e){} })();
async function doRegister(){
  try{
    const data = await API.post("/api/auth/register", {email: document.getElem
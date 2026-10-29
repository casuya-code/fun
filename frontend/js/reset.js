(async()=>{ await recordVisit(); try{const s=await API.get("/api/visitor-stats");document.getElementById("footer").textContent=`Ziara: L:${s.today} · Jumla:${s.total}`;}catch(e){} })();
async function doReset(){
  try{
    const data = await API.post("/api/auth/reset", token: document.getElem
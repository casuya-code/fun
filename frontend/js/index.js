(async()=>{ await recordVisit(); loadStats(); })();
async function loadStats(){
  try{
    const s = await API.get("/api/visitor-stats");
    const todayEl = document.getElementById("v-today");
    const totalEl = document.getElementById("v-total");
    if(todayEl) todayEl.textContent = s.today;
    if(totalEl) totalEl.textContent = s.total;
  }catch(e){}
}

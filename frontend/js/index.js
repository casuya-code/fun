(async()=>{ await recordVisit(); loadStats(); })();
async function loadStats(){
  try{
    const s = await API.get("/api/visitor-stats");
    document.getElementById("v-yest").textContent = s.yesterday;
    document.getElementById("v-today").textContent = s.today;
    document.getElementById("v-week").textContent = s.week;
    document.getElementById("v-month").textContent = s.month;
    document.getElementById("v-year").textContent = s.year;
    document.getElementById("v-total").textContent = s.total;
  }catch(e){}
}

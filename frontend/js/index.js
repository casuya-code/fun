// Index page
(async()=>{ 
  try{
    const s=await fetch("/api/visitor-stats");
    if(s.ok){ const d=await s.json(); const el=document.getElementById("v-total"); if(el) el.textContent=d.total; }
  }catch(e){}
})();
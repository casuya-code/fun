const API = {
  base: "",
  token: localStorage.getItem("token"),
  setToken(t){ this.token = t; if(t) localStorage.setItem("token", t); else localStorage.removeItem("token"); },
  async req(path, opts={}){
    const headers = opts.headers || {};
    if(this.token) headers["Authorization"] = "Bearer " + this.token;
    if(opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const res = await fetch(this.base + path, {...opts, headers});
    let data = null;
    try { data = await res.json(); } catch(e){}
    if(res.status === 401){
      API.setToken(null); setUser(null);
      if(!location.pathname.endsWith("login.html")) location.href = "/login.html";
    }
    if(!res.ok){
      const msg = (data && (data.detail || data.message)) || res.statusText;
      throw new Error(msg);
    }
    return data;
  },
  get(p){ return this.req(p); },
  post(p,b){ return this.req(p,{method:"POST",body:JSON.stringify(b)}); },
  put(p,b){ return this.req(p,{method:"PUT",body:JSON.stringify(b)}); },
  del(p){ return this.req(p,{method:"DELETE"}); },
};

async function recordVisit(){
  try {
    const token = localStorage.getItem("token");
    const headers = token ? {Authorization: "Bearer " + token} : {};
    await fetch("/api/visits", {method:"POST", headers});
  } catch(e){}
}

function currentUser(){ try { return JSON.parse(localStorage.getItem("user")||"null"); } catch(e){return null;} }
function setUser(u){ if(u) localStorage.setItem("user", JSON.stringify(u)); else localStorage.removeItem("user"); }

function requireAuth(){
  if(!API.token){ location.href = "/login.html"; return false; }
  return true;
}
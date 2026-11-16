const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const {JSDOM}=require("jsdom");
const root=path.resolve(__dirname,"../findmy_home/rootfs/app/findmy_home/static");
const html=fs.readFileSync(path.join(root,"index.html"),"utf8");
const script=fs.readFileSync(path.join(root,"app.js"),"utf8");
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function setup(options={}){
  const data={channel:"edge",csrf:"synthetic-csrf",health:{status:"ok"},setup:{locations_connected:true,discovery_session_saved:false},recovery:{phase:"idle"},
    items:[{id:"a",name:"Fixture A",enabled:!!options.enabled,report:null},{id:"b",name:"Fixture B",enabled:false,report:null}]};
  const dom=new JSDOM(html,{url:"https://ha.example.invalid/api/hassio_ingress/synthetic/",runScripts:"outside-only"});
  const window=dom.window,requests=[];
  let tick;
  window.setInterval=callback=>{tick=callback;return 1;};
  window.fetch=async(url,init={})=>{
    const body=init.body?JSON.parse(init.body):null;
    requests.push({url,body,headers:init.headers});
    let result=data,ok=true;
    if(url==="ui/select"){
      if(options.failSave){ok=false;result={message:"Fixture save failure"};}
      else {for(const item of data.items)item.enabled=body.ids.includes(item.id);result={saved:true,selected_count:body.ids.length};}
    }else if(url==="ui/recovery"){
      data.recovery={phase:"input",kind:"verification_code",label:"SMS verification code",secret:true,choices:[]};
      result=data.recovery;
    }else if(url==="ui/refresh"){
      data.items.find(item=>item.id===body.id).refresh={status:"queued"};
      result={status:"queued",message:"Refresh queued for this item."};
    }
    return {ok,json:async()=>JSON.parse(JSON.stringify(result))};
  };
  window.eval(script);await flush();
  return {window,document:window.document,data,requests,refresh:()=>tick(),close:()=>dom.window.close()};
}
function submit(env,id){env.document.getElementById(id).dispatchEvent(new env.window.Event("submit",{bubbles:true,cancelable:true}));}

test("save gives exact count and leaves no unsaved changes",async()=>{
  const env=await setup();try{
    const check=env.document.querySelector("#choices input");check.checked=true;check.dispatchEvent(new env.window.Event("change"));
    assert.match(env.document.getElementById("selection-state").textContent,/Unsaved/);
    submit(env,"selection");await flush();
    assert.match(env.document.getElementById("message").textContent,/Saved: 1 item tracked/);
    assert.equal(env.document.getElementById("message").dataset.kind,"success");
    assert.equal(env.document.getElementById("save-selection").disabled,true);
    assert.equal(env.requests.filter(request=>request.url==="ui/select").length,1);
  }finally{env.close();}
});
test("failed save retains edits and gives an error instead of Saved",async()=>{
  const env=await setup({failSave:true});try{
    const check=env.document.querySelector("#choices input");check.checked=true;check.dispatchEvent(new env.window.Event("change"));
    submit(env,"selection");await flush();
    assert.equal(env.document.getElementById("message").textContent,"Fixture save failure");
    assert.equal(env.document.getElementById("message").dataset.kind,"error");
    assert.equal(env.document.getElementById("save-selection").disabled,false);
    assert.equal(env.document.querySelector("#choices input").checked,true);
  }finally{env.close();}
});
test("background refresh preserves a partially typed SMS code",async()=>{
  const env=await setup();try{
    env.data.recovery={phase:"input",kind:"verification_code",label:"SMS verification code",secret:true,choices:[]};
    await env.refresh();
    const input=env.document.querySelector("#recovery input");input.value="000123";
    await env.refresh();
    assert.equal(env.document.querySelector("#recovery input"),input);
    assert.equal(input.value,"000123");
  }finally{env.close();}
});
test("discovery sends email and password together and clears the password field",async()=>{
  const env=await setup();try{
    const form=env.document.getElementById("discovery-start");
    form.elements.namedItem("email").value="fixture@example.invalid";
    form.elements.namedItem("password").value="synthetic-test-password";
    env.document.getElementById("consent").checked=true;
    submit(env,"discovery-start");await flush();
    const calls=env.requests.filter(request=>request.url==="ui/recovery");
    assert.equal(calls.length,1);
    assert.deepEqual(calls[0].body.credentials,{email:"fixture@example.invalid",password:"synthetic-test-password"});
    assert.equal(calls[0].headers["X-CSRF-Token"],"synthetic-csrf");
    assert.equal(form.elements.namedItem("password").value,"");
    assert.equal(env.document.querySelector("#recovery input").autocomplete,"one-time-code");
    assert.equal(env.document.body.textContent.includes("synthetic-test-password"),false);
  }finally{env.close();}
});
test("valid saved discovery session does not ask for credentials",async()=>{
  const env=await setup();try{
    env.data.setup.discovery_session_saved=true;await env.refresh();
    assert.equal(env.document.getElementById("discovery-credentials").hidden,true);
    env.document.getElementById("consent").checked=true;
    submit(env,"discovery-start");await flush();
    const call=env.requests.find(request=>request.url==="ui/recovery");
    assert.equal(call.body.credentials,undefined);
    assert.equal(call.body.fresh_login,undefined);
  }finally{env.close();}
});
test("per-item refresh queues only the clicked item and shows progress",async()=>{
  const env=await setup({enabled:true});try{
    env.document.querySelector("[data-refresh]").click();await flush();
    const calls=env.requests.filter(request=>request.url==="ui/refresh");
    assert.equal(calls.length,1);assert.equal(calls[0].body.id,"a");
    assert.match(env.document.getElementById("message").textContent,/Refresh queued/);
    assert.equal(env.document.querySelector("[data-refresh]").disabled,true);
    assert.match(env.document.querySelector(".item-status").textContent,/Queued/);
    assert.equal(env.document.getElementById("app-title").textContent,"Find My Home Edge");
  }finally{env.close();}
});

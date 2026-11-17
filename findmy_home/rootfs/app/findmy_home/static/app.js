"use strict";
let csrf="", snapshot=null, loginMethod=null, busy=false, selectionDirty=false;
let forceDiscoveryLogin=false, reconnecting=false, recoveryKey="", map=null, markers=null;
let refreshing=false, emailHint="";
const $=id=>document.getElementById(id);
const itemCount=n=>n+" item"+(n===1?"":"s");
const text=(tag,value)=>{const node=document.createElement(tag);node.textContent=value;return node;};
function notice(message,kind="info"){const box=$("message");box.textContent=message;box.dataset.kind=kind;box.hidden=!message;}
async function api(path,data){
  const response=await fetch(path,{method:data?"POST":"GET",headers:data?{"Content-Type":"application/json","X-CSRF-Token":csrf}:{},body:data?JSON.stringify(data):undefined,cache:"no-store",credentials:"same-origin"});
  const result=await response.json();
  if(!response.ok)throw Error(result.message||"The request failed. Your saved choices have not been changed.");
  return result;
}
async function action(fn,pending="Working…",success){
  if(busy)return;
  busy=true;notice(pending,"working");updateButtons();
  try{const result=await fn();if(success)notice(typeof success==="function"?success(result):success,"success");
    else if(result?.phase)notice(result.phase==="input"?"Apple needs the information shown in the discovery step.":result.phase==="complete"?"Discovery complete. Choose items and save your tracking choices.":result.phase==="failed"?"Discovery failed. Try the saved session or sign in again.":"Discovery: "+result.phase,result.phase==="complete"?"success":result.phase==="failed"?"error":"info");
    await refresh();}
  catch(error){notice(error.message,"error");}
  finally{busy=false;updateButtons();}
}
function updateButtons(){
  for(const button of document.querySelectorAll("form button"))button.disabled=busy;
  $("save-selection").disabled=busy||!selectionDirty;
  $("cancel-login").disabled=busy;$("cancel-recovery").disabled=busy;
  for(const button of document.querySelectorAll("[data-refresh]")){
    const state=snapshot?.items.find(item=>item.id===button.dataset.refresh)?.refresh?.status;
    button.disabled=busy||state==="queued"||state==="refreshing";
  }
}
function ago(value){if(!value)return "No sighting yet";const seconds=Math.max(0,Math.floor((Date.now()-Date.parse(value))/1000));return seconds<60?"Just now":seconds<3600?Math.floor(seconds/60)+" minutes ago":seconds<86400?Math.floor(seconds/3600)+" hours ago":Math.floor(seconds/86400)+" days ago";}
const errors={"rate_limited":"Apple requested a pause.","apple_empty_response":"Apple returned an empty response.","authentication_required":"Reconnect location access.","poll_failed":"Refresh failed.","item_timeout":"This item exceeded its query time limit."};
function description(item){
  const parts=[];
  if(item.apple_name&&item.apple_name!==item.name)parts.push(item.apple_name);
  if(item.model_name||item.model)parts.push(item.model_name||item.model);
  if(item.paired_at)parts.push("Paired "+item.paired_at);
  parts.push("ID "+item.id.slice(0,8));
  return parts.join(" · ");
}
function render(data){
  snapshot=data;csrf=data.csrf;
  $("app-title").textContent="Find My Home"+(data.channel==="edge"?" Edge":data.channel==="stable"?"":" Edge");
  $("health").textContent=({"ok":"Tracking","searching":"Tracking; searching remaining items","partial_results":"Some items need attention","no_reports":"No reports returned","reauth_required":"Connect location access","select_items":"Choose tracked items","polling":"Refreshing","error":"Refresh needs attention","starting":"Starting","ready":"Location access connected"})[data.health.status]||"Checking";
  const selected=data.items.filter(item=>item.enabled), known=selected.filter(item=>item.report).length, health=data.health;
  $("poll-summary").textContent=selected.length+" tracked · "+known+" with a saved location · Scheduled check: "+(health.last_poll?ago(health.last_poll):"not completed")+" · Checked "+(health.items_completed??0)+"/"+selected.length+(health.error_code?" · "+(errors[health.error_code]||"Refresh needs attention."):"");
  const cards=$("cards");cards.replaceChildren();
  if(!selected.length)cards.append(text("p","Choose items in Setup, then save your tracking choices."));
  for(const item of selected){
    const card=text("article","");card.append(text("h2",item.name));const detail=text("p",description(item));detail.className="item-description";card.append(detail);const dl=text("dl",""),report=item.report;
    for(const [label,value] of [["Last sighting",ago(report?.timestamp)],["Last checked",item.refresh?.checked_at?ago(item.refresh.checked_at):"Not checked yet"],["Reported at",report?new Date(report.timestamp).toLocaleString():"Not reported"],["Accuracy",report?Math.round(report.accuracy)+" m":"Not reported"]])dl.append(text("dt",label),text("dd",value));
    card.append(dl);
    const state=item.refresh||{}, status=text("p",({"queued":"Queued for the next available worker…","refreshing":"Asking Apple for this item…","updated":"Latest available report checked.","searching":"Recent keys checked. The older key search will continue on the next refresh.","no_report":"Check finished: Apple returned no sighting for this item.","cancelled":"Refresh cancelled."})[state.status]||(state.status==="error"?(errors[state.error]||"Refresh failed. Try again later."):""));
    status.className="item-status";status.setAttribute("role","status");card.append(status);
    const button=text("button",state.status==="queued"?"Refresh queued":state.status==="refreshing"?"Refreshing…":"Refresh this item");button.dataset.refresh=item.id;
    button.onclick=()=>action(async()=>{
      const result=await api("ui/refresh",{id:item.id});
      notice(result.message+(result.status==="paused"?" Try again in "+Math.ceil(result.retry_after/60)+" minutes.":""),["paused","cooldown","reauth_required"].includes(result.status)?"info":"success");
    },"Queueing this item's refresh…");
    card.append(button);cards.append(card);
  }
  if(!selectionDirty){
    const choices=$("choices");choices.replaceChildren();
    for(const item of data.items){
      const label=text("label","");label.className="check";
      const check=document.createElement("input");check.type="checkbox";check.value=item.id;check.checked=item.enabled;
      check.onchange=()=>{selectionDirty=true;$("selection-state").textContent="Unsaved changes";$("selection-count").textContent=choices.querySelectorAll("input:checked").length+" selected";updateButtons();};
      const copy=text("span","");copy.className="item-label";
      copy.append(text("span",item.name));const detail=text("small",description(item));detail.className="item-description";copy.append(detail);
      label.append(check,copy);choices.append(label);
    }
    if(!data.items.length)choices.append(text("p","Discover items in step 2 first."));
    $("selection-count").textContent=selected.length+" selected";
  }
  const connected=Boolean(data.setup?.locations_connected);
  $("location-state").textContent=connected?"Connected":"Not connected";
  $("login").hidden=connected&&!reconnecting;$("reconnect").hidden=!connected;
  const saved=Boolean(data.setup?.discovery_session_saved);
  $("discovery-state").textContent=saved?"Session saved":"First discovery";
  $("discovery-credentials").hidden=saved&&!forceDiscoveryLogin;
  for(const input of $("discovery-credentials").querySelectorAll("input"))input.required=!$("discovery-credentials").hidden;
  $("discovery-signin").hidden=!saved||forceDiscoveryLogin;
  $("discover").textContent=saved&&!forceDiscoveryLogin?"Discover using saved session":"Sign in and discover items";
  renderRecovery(data.recovery);
  renderMap();updateButtons();
}
function renderRecovery(flow){
  const messages={"idle":"","working":"Contacting Apple. Keep this page open…","complete":"Discovery complete. Choose items below and save your tracking choices.","failed":"Discovery did not finish. Try the saved session again, or choose Sign in again if Apple expired it.","timed_out":"Apple did not respond in time. Try again.","expired":"Discovery expired. Start it again.","cancelled":"Discovery cancelled.","busy":"Another user is completing discovery."};
  $("recovery-status").textContent=messages[flow?.phase]??"";
  const key=JSON.stringify(flow||{});if(key===recoveryKey)return;recoveryKey=key;
  const form=$("recovery");form.replaceChildren();form.hidden=flow?.phase!=="input";if(form.hidden)return;
  const label=text("label",flow.label);let input;
  if(flow.kind==="recovery_device"){
    input=document.createElement("select");
    for(const choice of flow.choices){const option=text("option",choice.label);option.value=choice.value;input.append(option);}
    form.append(text("p","Choose a device whose unlock passcode you know. This is not your Apple account password."));
  }else{
    input=document.createElement("input");input.type=flow.secret?"password":flow.kind==="email"?"email":"text";
    input.autocomplete=flow.kind==="password"?"current-password":flow.kind==="email"?"username":flow.kind==="verification_code"?"one-time-code":"off";
    input.inputMode=flow.kind==="verification_code"?"numeric":"text";input.maxLength=512;input.required=true;
    if(flow.kind==="email")input.value=emailHint;
    if(flow.kind==="verification_code")form.append(text("p","Enter the SMS code sent for this discovery attempt, not a separate trusted-device approval code."));
  }
  input.name="response";label.append(input);form.append(label,text("button",flow.kind==="verification_code"?"Verify SMS code":flow.kind==="device_passcode"?"Unlock item keys":"Continue"));
  form.onsubmit=event=>{event.preventDefault();const value=input.value;input.value="";action(()=>api("ui/recovery",{action:"answer",value}),"Verifying with Apple…");};
}
function renderMap(){
  if(!$("map-preview").open||!window.L||!snapshot)return;
  if(!map){map=L.map("map");L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"© OpenStreetMap contributors",maxZoom:19}).addTo(map);markers=L.layerGroup().addTo(map);map.setView([20,0],2);}
  markers.clearLayers();const points=[];
  for(const item of snapshot.items.filter(item=>item.enabled&&item.report)){
    const p=[item.report.latitude,item.report.longitude];points.push(p);
    L.marker(p).bindPopup(text("span",item.name+" · "+ago(item.report.timestamp))).addTo(markers);
    L.circle(p,{radius:item.report.accuracy,weight:1}).addTo(markers);
  }
  map.invalidateSize();if(points.length&&!map._fitted){map.fitBounds(points,{padding:[30,30],maxZoom:15});map._fitted=true;}
}
async function refresh(){if(refreshing)return;refreshing=true;try{render(await api("v1/snapshot"));}catch(error){$("health").textContent="App unavailable";notice(error.message,"error");}finally{refreshing=false;}}
document.querySelectorAll("[data-tab]").forEach(button=>button.onclick=()=>{for(const id of ["overview","setup"])$(id).hidden=id!==button.dataset.tab;document.querySelectorAll("[data-tab]").forEach(other=>other.setAttribute("aria-selected",String(other===button)));renderMap();});
$("map-preview").ontoggle=renderMap;
$("login").onsubmit=event=>{event.preventDefault();const email=event.target.elements.namedItem("email").value,password=event.target.elements.namedItem("password").value;emailHint=email;$("discovery-email").value=email;event.target.elements.namedItem("password").value="";action(async()=>showFactor(await api("ui/login",{email,password})),"Connecting location access…");};
function showFactor(result){
  const form=$("factor");form.replaceChildren();form.hidden=result.phase==="complete";
  if(result.phase==="complete"){reconnecting=false;notice("Location access connected. Next, discover or choose your items.","success");}
  if(result.phase==="choose_method"){
    notice("Choose how Apple should send your location-access verification code.","info");
    const select=document.createElement("select");for(const method of result.methods){const option=text("option",method.label);option.value=method.value;select.append(option);}
    const label=text("label","How should Apple send the location-access code?");label.append(select);form.append(label,text("button","Send verification code"));
    form.onsubmit=event=>{event.preventDefault();loginMethod=Number(select.value);action(async()=>showFactor(await api("ui/factor",{method:loginMethod})),"Requesting your verification code…");};
  }else if(result.phase==="verification_code"){
    notice("Verification code requested. Enter the code from the selected method.","info");
    const code=document.createElement("input");code.type="password";code.inputMode="numeric";code.autocomplete="one-time-code";code.maxLength=8;code.required=true;
    const label=text("label","Code from the selected verification method");label.append(code);form.append(label,text("button","Connect location access"));
    form.onsubmit=event=>{event.preventDefault();const value=code.value;code.value="";action(async()=>showFactor(await api("ui/factor",{method:loginMethod,code:value})),"Verifying location access…");};
  }
}
$("reconnect").onclick=()=>{reconnecting=true;$("login").hidden=false;$("login").elements.namedItem("email").focus();};
$("discovery-signin").onclick=()=>{forceDiscoveryLogin=true;$("discovery-credentials").hidden=false;for(const input of $("discovery-credentials").querySelectorAll("input"))input.required=true;$("discovery-email").focus();$("discover").textContent="Sign in and discover items";};
$("discovery-start").onsubmit=event=>{
  event.preventDefault();
  if(!$("consent").checked){notice("Read and accept the item-key recovery consent first.","error");return;}
  const form=event.target,data={action:"start",consent:true};
  if(!$("discovery-credentials").hidden){data.credentials={email:form.elements.namedItem("email").value,password:form.elements.namedItem("password").value};emailHint=form.elements.namedItem("email").value;form.elements.namedItem("password").value="";data.fresh_login=forceDiscoveryLogin;}
  action(()=>api("ui/recovery",data),"Discovering items. Apple may request an SMS code or a trusted-device passcode…");
};
$("selection").onsubmit=event=>{
  event.preventDefault();
  action(async()=>{
    const ids=[...$("choices").querySelectorAll("input:checked")].map(check=>check.value);
    const result=await api("ui/select",{ids});selectionDirty=false;
    $("selection-state").textContent=itemCount(result.selected_count)+" saved";
    return result;
  },"Saving tracking choices…",result=>"Saved: "+itemCount(result.selected_count)+" tracked. Location checks run separately; each item shows its refresh progress.");
};
$("cancel-recovery").onclick=()=>action(()=>api("ui/recovery",{action:"cancel"}),"Cancelling discovery…","Discovery cancelled.");
$("cancel-login").onclick=()=>action(async()=>{await api("ui/cancel",{});$("factor").hidden=true;},"Cancelling sign-in…","Location sign-in cancelled.");
$("pairing-security").onsubmit=event=>{
  event.preventDefault();
  if(!$("pairing-consent").checked){notice("Confirm that existing read-only access should be revoked.","error");return;}
  action(async()=>{const result=await api("ui/rotate-pairing",{confirm:true});$("pairing-consent").checked=false;return result;},"Revoking old location-read access…",result=>result.message);
};
refresh();setInterval(refresh,5000);

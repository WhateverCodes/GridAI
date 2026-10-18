const API=location.protocol==='file:'?'http://127.0.0.1:8000':location.origin;
let state=null;
let overviewCache=new Map();
let overviewRefreshTimer=null;
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function fmt(x){return Number(x).toLocaleString(undefined,{maximumFractionDigits:0})+' MW'}
function fmtLocal(iso, options={}){
  const d=new Date(iso);
  if(Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short',...options});
}
function localDateValue(d=new Date()){
  const x=new Date(d);
  const y=x.getFullYear();
  const m=String(x.getMonth()+1).padStart(2,'0');
  const day=String(x.getDate()).padStart(2,'0');
  return `${y}-${m}-${day}`;
}
function localTimeParts(d=new Date()){
  const x=new Date(d);
  let hour=x.getHours();
  const minute=x.getMinutes();
  const ampm=hour>=12?'PM':'AM';
  hour=hour%12||12;
  return {hour:String(hour),minute:String(minute).padStart(2,'0'),ampm};
}
function nextQuarter(d=new Date()){
  const x=new Date(d);
  x.setSeconds(0,0);
  const minutes=x.getMinutes();
  const remainder=minutes%15;
  // Strictly future. 08:02 -> 08:15, 08:15 -> 08:30.
  x.setMinutes(minutes+(remainder===0?15:15-remainder));
  return x;
}
function populateHourOptions(){
  const el=$('forecastHour');
  if(!el)return;
  el.innerHTML=Array.from({length:12},(_,i)=>`<option value="${i+1}">${String(i+1).padStart(2,'0')}</option>`).join('');
}
function setForecastControls(d){
  const q=new Date(d);
  const parts=localTimeParts(q);
  $('forecastDate').value=localDateValue(q);
  $('forecastHour').value=String(Number(parts.hour));
  $('forecastMinute').value=parts.minute;
  $('forecastAmPm').value=parts.ampm;
}
function localControlsToISOString(){
  const date=$('forecastDate').value;
  const hour12=Number($('forecastHour').value);
  const minute=Number($('forecastMinute').value);
  const ampm=$('forecastAmPm').value;
  if(!date||!hour12||![0,15,30,45].includes(minute))return null;
  let hour=hour12%12;
  if(ampm==='PM')hour+=12;
  const [y,m,day]=date.split('-').map(Number);
  const d=new Date(y,m-1,day,hour,minute,0,0);
  if(Number.isNaN(d.getTime()))return null;
  // Date is constructed in the computer's local timezone, then serialized with
  // the correct local UTC offset. The backend converts internally to UTC.
  return d.toISOString();
}
async function api(path){const r=await fetch(API+path);if(!r.ok){let message;try{const error=await r.json();message=error.detail||'Request failed';}catch{message='Request failed ('+r.status+')';}throw new Error(message);}return r.json()}

function targetOptions(selectId){
  const el=$(selectId); if(!el||!state)return;
  const current=el.value;
  el.innerHTML=Object.entries(state.targets).map(([k,d])=>`<option value="${esc(k)}">${esc(d.title)}</option>`).join('');
  if(state.targets[current]) el.value=current;
}

function lineChart(rows,targetTitle='Electricity'){
  const svg=$('forecastChart'),tooltip=$('chartTooltip');
  const w=1100,h=430,left=96,right=30,top=30,bottom=82;
  if(!rows.length){svg.innerHTML='';if(tooltip)tooltip.classList.remove('show');return}
  const ys=rows.map(r=>Number(r.predicted));
  const min=Math.min(0,...ys),max=Math.max(...ys),range=max-min||1;
  const plotW=w-left-right,plotH=h-top-bottom;
  const xFor=i=>left+i*plotW/Math.max(1,rows.length-1);
  const yFor=v=>top+plotH-(v-min)*plotH/range;
  const pts=ys.map((v,i)=>`${xFor(i)},${yFor(v)}`).join(' ');
  const first=fmtLocal(rows[0].timestamp),last=fmtLocal(rows.at(-1).timestamp);
  const yMid=min+(max-min)/2;
  const circles=rows.map((r,i)=>`<circle class="hover-point" cx="${xFor(i)}" cy="${yFor(Number(r.predicted))}" r="7" data-index="${i}"/>`).join('');
  svg.innerHTML=`
    <line class="axis" x1="${left}" y1="${top}" x2="${left}" y2="${top+plotH}"/>
    <line class="axis" x1="${left}" y1="${top+plotH}" x2="${w-right}" y2="${top+plotH}"/>
    <line class="grid-line" x1="${left}" y1="${yFor(yMid)}" x2="${w-right}" y2="${yFor(yMid)}"/>
    <polyline class="forecast-line" points="${pts}"/>
    <g class="hover-points">${circles}</g>
    <text class="axis-y-label" x="12" y="${top+4}">${fmt(max)}</text>
    <text class="axis-y-label" x="12" y="${yFor(yMid)+4}">${fmt(yMid)}</text>
    <text class="axis-y-label" x="12" y="${top+plotH+4}">${fmt(min)}</text>
    <text class="axis-x-label" x="${left}" y="${h-18}" text-anchor="start">${esc(first)}</text>
    <text class="axis-x-label" x="${w-right}" y="${h-18}" text-anchor="end">${esc(last)}</text>`;

  svg.querySelectorAll('.hover-point').forEach(point=>{
    point.addEventListener('mouseenter',()=>{
      const row=rows[Number(point.dataset.index)];
      tooltip.innerHTML=`<strong>${esc(targetTitle)}</strong><br><b>${fmt(row.predicted)}</b><br>${esc(fmtLocal(row.timestamp))}`;
      tooltip.classList.add('show');
      positionTooltip(point,svg,tooltip);
      point.classList.add('active');
    });
    point.addEventListener('mousemove',()=>positionTooltip(point,svg,tooltip));
    point.addEventListener('mouseleave',()=>{tooltip.classList.remove('show');point.classList.remove('active');});
  });
}
function positionTooltip(point,svg,tooltip){
  const svgRect=svg.getBoundingClientRect();
  const viewW=1100,viewH=430;
  const cx=Number(point.getAttribute('cx')),cy=Number(point.getAttribute('cy'));
  const px=(cx/viewW)*svgRect.width;
  const py=(cy/viewH)*svgRect.height;
  tooltip.style.left=`${Math.min(Math.max(8,px-75),Math.max(8,svgRect.width-170))}px`;
  tooltip.style.top=`${Math.max(8,py-82)}px`;
}

function renderMetrics(){
  const order=Object.keys(state.targets);
  $('metricCards').innerHTML=order.map(k=>{const d=state.targets[k];return `<div><span>${esc(d.title)}</span><b>${Number(d.test_mae).toFixed(1)} <i>MW MAE</i></b><small>${esc(d.model||'Forecast-safe XGBoost')}</small></div>`}).join('');
}
function renderModels(){
  const order=Object.keys(state.targets);
  $('modelList').innerHTML=order.map(k=>{const d=state.targets[k];return `<p><span>${esc(d.title)}</span><b>${esc(d.model)}${d.long_range?`<small>Long-range: ${esc(d.long_range.model.replace(' (direct long-range Solar)',''))}</small>`:''}</b></p>`}).join('');
}
function renderFeatures(){
  const order=Object.keys(state.targets);
  $('featurePanels').innerHTML=order.map(k=>{
    const d=state.targets[k], fs=d.feature_importance||[], max=fs[0]?.importance||1;
    return `<article class="panel feature-panel"><h3>${esc(d.title)}</h3><div class="bars">${fs.slice(0,10).map(f=>`<p><span>${esc(f.feature)}</span><b style="width:${Math.max(5,100*f.importance/max)}%">${(100*f.importance).toFixed(2)}%</b></p>`).join('')}</div></article>`;
  }).join('');
}

function currentPredictionTime(now=new Date()){
  return new Date(Math.floor(now.getTime()/(15*60*1000))*(15*60*1000));
}
async function updateOverview(force=false){
  if(!state)return;
  const k=$('overviewTarget').value;
  const predictionTime=currentPredictionTime();
  const key=`${k}|${predictionTime.toISOString()}`;
  if(!force && overviewCache.has(key)){
    renderOverviewResult(k,overviewCache.get(key));
    scheduleOverviewRefresh();
    return;
  }
  try{
    $('overviewSnapshot').innerHTML='<span>Generating current prediction…</span>';
    const d=await api(`/api/snapshot/${k}?at=${encodeURIComponent(predictionTime.toISOString())}`);
    overviewCache.set(key,d);
    if($('overviewTarget').value!==k)return;
    renderOverviewResult(k,d);
  }catch(e){$('overviewSnapshot').innerHTML=`<span class="error-text">Unable to generate current prediction: ${esc(e.message)}</span>`;}
  scheduleOverviewRefresh();
}
function renderOverviewResult(k,d){
  const target=state.targets[k],row=d.rows[0];
  $('overviewSnapshot').innerHTML=`<b>${fmt(row.predicted)}</b><span>Current 15-minute forecast snapshot</span><p>Prediction time: ${esc(fmtLocal(row.timestamp))}</p><small>${esc(d.model||target.model)} · historical observations through ${esc(fmtLocal(d.source_latest))}. ${d.forecast_method==='direct_calendar'?'Direct calendar projection; no live weather.':d.recursively_extended?'Recursively extrapolated to this time; no live measurements.':''}</small>`;
}
function scheduleOverviewRefresh(){
  if(overviewRefreshTimer)clearTimeout(overviewRefreshTimer);
  const now=new Date();
  const next=new Date(currentPredictionTime(now).getTime()+15*60*1000);
  const delay=Math.max(1000,next.getTime()-now.getTime()+250);
  overviewRefreshTimer=setTimeout(()=>updateOverview(true),delay);
}

function modelCatalog(k){
  const d=state.targets[k];
  const deployed=['deployed',d.model,d.test_mae,d.test_rmse,d.improvement_pct,'DEPLOYED','Selected by validation MAE.'];
  const rows=[deployed,...d.comparison.filter(r=>r.kind!==d.selected_kind).map(r=>[
    r.kind,r.model,r.test_mae,r.test_rmse,r.improvement_pct,'EVALUATED','Same chronological split and causal features.'
  ])];
  if(d.long_range) rows.push(...d.long_range.comparison.map(r=>[
    'long_'+r.kind,r.model+' · direct long-range',r.test_mae,r.test_rmse,null,
    r.kind===d.long_range.selected_kind?'LONG-RANGE SELECTED':'LONG-RANGE TEST',d.long_range.evaluation
  ]));
  return rows;
}
function statText(v){return v==null?'—':Number(v).toFixed(2)+' MW'}
function efficiencyText(o){
  if(o[0]==='persistence')return 'Baseline';
  if(o[4]==null)return '—';
  const pct=Number(o[4]);
  return pct>=0?`${pct.toFixed(2)}% lower MAE`:`${Math.abs(pct).toFixed(2)}% higher MAE`;
}
function detailRow(k,o){return `<tr class="model-detail-row" data-parent="${esc(k)}"><td class="detail-model">↳ ${esc(o[1])}</td><td>${statText(o[2])}</td><td>${statText(o[3])}</td><td>${efficiencyText(o)}</td><td><span class="reference-badge">${esc(o[5])}</span></td></tr>`;}
function modelRow(k){
  const d=state.targets[k],catalog=modelCatalog(k),deployed=catalog[0];
  return `<tr class="model-main-row" data-target="${esc(k)}"><td class="target-name">${esc(d.title)}</td><td>${statText(deployed[2])}</td><td>${statText(deployed[3])}</td><td>${efficiencyText(deployed)}</td><td><button type="button" class="expand-model" data-target="${esc(k)}" aria-expanded="false"><span>${esc(deployed[1])}</span><span class="chevron">⌄</span></button><div class="model-status">DEPLOYED</div></td></tr>${catalog.slice(1).map(o=>detailRow(k,o)).join('')}`;
}
function renderModelTable(){
  $('modelTableBody').innerHTML=Object.keys(state.targets).map(modelRow).join('');
  document.querySelectorAll('.expand-model').forEach(btn=>btn.addEventListener('click',()=>toggleModelRows(btn)));
  updateModelNote();
}
function toggleModelRows(btn){
  const k=btn.dataset.target,open=btn.getAttribute('aria-expanded')==='true';
  btn.setAttribute('aria-expanded',String(!open));
  document.querySelectorAll(`.model-detail-row[data-parent="${CSS.escape(k)}"]`).forEach(row=>row.classList.toggle('is-open',!open));
}
function updateModelNote(){
  $('modelTableNote').textContent='The deployed short-term model stays visible. Six candidates share one-step evaluation within each target; validation MAE selects deployment. Separate Solar long-range rows use direct calendar predictions with calibration fixed before the test period. Their metrics are not directly comparable to one-step errors.';
}

let forecastRequestVersion=0;
function clearForecastResults(){
  for(const id of ['value','time','model','mae','rmse']) $(id).textContent='—';
  $('chartTitle').textContent=state?.targets[$('forecastTarget').value]?.title||'Forecast';
  $('rangeLabel').textContent='';
  lineChart([]);
}
function forecastInputsChanged(){
  ++forecastRequestVersion;
  clearForecastResults();
  $('forecastNotice').textContent='Choose Generate forecast to calculate the selected target, date and duration.';
}
async function runForecast(){
  const version=++forecastRequestVersion;
  clearForecastResults();
  try{
    $('forecastNotice').textContent='Generating the requested forecast… Distant dates may take longer.';
    const k=$('forecastTarget').value,steps=Number($('duration').value),iso=localControlsToISOString();
    if(!iso)throw new Error('Choose a valid date and a 00, 15, 30 or 45 minute time.');
    const d=await api(`/api/forecast/${k}?origin=${encodeURIComponent(iso)}&steps=${steps}`);
    if(version!==forecastRequestVersion)return;
    if(d.target!==k||new Date(d.rows[0].timestamp).getTime()!==new Date(iso).getTime())
      throw new Error('The returned target or timestamp does not match your selection.');
    const metaD=state.targets[k];
    $('value').textContent=fmt(d.rows[0].predicted);
    $('time').textContent=fmtLocal(d.rows[0].timestamp);
    $('model').textContent=(d.model||metaD.model).replace(' (direct long-range Solar)','');
    $('mae').textContent=Number(d.test_mae??metaD.test_mae).toFixed(2)+' MW';
    $('rmse').textContent=Number(d.test_rmse??metaD.test_rmse).toFixed(2)+' MW';
    $('chartTitle').textContent=metaD.title;
    $('rangeLabel').textContent=fmtLocal(d.rows[0].timestamp)+' → '+fmtLocal(d.rows.at(-1).timestamp);
    lineChart(d.rows,metaD.title);
    const explanation=d.forecast_method==='direct_calendar'
      ?'Calendar projection without future weather. The displayed errors belong to this long-range model.'
      :'Forecast extended from historical data. Displayed errors measure one-step predictions; uncertainty grows with distance.';
    $('forecastNotice').textContent=`${d.rows.length} points · ${metaD.title} · starts ${fmtLocal(d.rows[0].timestamp)}. Source data through ${fmtLocal(d.source_latest)}. ${explanation}`;
  }catch(e){
    if(version!==forecastRequestVersion)return;
    clearForecastResults();
    $('forecastNotice').textContent='Forecast error: '+e.message;
  }
}

async function start(){
  try{
    state=await api('/api/summary');
    $('apiStatus').textContent='Forecast engine online';
    $('apiDetail').textContent='FastAPI · trained models ready';
    targetOptions('overviewTarget');targetOptions('forecastTarget');
    populateHourOptions();
    renderMetrics();renderModels();renderFeatures();renderModelTable();
    syncTargetDate();
    await updateOverview(true);
  }catch(e){
    $('apiStatus').textContent='Backend offline';
    $('apiDetail').textContent='Run uvicorn backend.app:app --reload --port 8000';
  }
}

document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.page').forEach(x=>x.classList.remove('show'));
  b.classList.add('active');
  $(b.dataset.page).classList.add('show');
  if(b.dataset.page==='overview')updateOverview(false);
});
$('overviewTarget').onchange=()=>updateOverview(false);
$('runForecast').onclick=runForecast;
for(const id of ['forecastTarget','duration','forecastDate','forecastHour','forecastMinute','forecastAmPm'])
  for(const event of ['input','change']) $(id).addEventListener(event,forecastInputsChanged);
start();

function syncTargetDate(){
  if(!state)return;
  const d=state.targets[$('forecastTarget').value];
  setForecastControls(currentPredictionTime());
  clearForecastResults();
  $('forecastNotice').textContent=`Source observed through ${fmtLocal(d.latest_observed)}. ${d.limitation} Metrics are for one-step forecasts; recursive errors grow with horizon.`;
}

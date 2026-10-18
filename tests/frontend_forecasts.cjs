const fs=require('fs'),vm=require('vm'),assert=require('assert');
process.env.TZ='Asia/Calcutta';
const source=fs.readFileSync(require('path').join(__dirname,'../script.js'),'utf8');
const elements=Object.fromEntries(['value','time','model','mae','rmse','chartTitle','rangeLabel','forecastNotice','forecastTarget','duration','forecastDate','forecastHour','forecastMinute','forecastAmPm'].map(k=>[k,{textContent:'OLD',value:''}]));
Object.assign(elements.forecastTarget,{value:'load'});
elements.duration.value='672';elements.forecastDate.value='2026-10-20';
elements.forecastHour.value='3';elements.forecastMinute.value='30';elements.forecastAmPm.value='AM';
let requests=[],chart=[];
const context=vm.createContext({Date,Number,Error,console,
  $:id=>elements[id],state:{targets:{load:{title:'Electricity Load',model:'Load model',test_mae:1,test_rmse:2},solar:{title:'Solar Generation',model:'Solar model',test_mae:3,test_rmse:4}}},
  api:path=>new Promise((resolve,reject)=>requests.push({path,resolve,reject})),
  fmt:n=>n+' MW',fmtLocal:s=>new Date(s).toLocaleString('en-IN',{timeZone:'Asia/Calcutta'}),
  lineChart:rows=>{chart=rows;}});
vm.runInContext(source.slice(source.indexOf('function localControlsToISOString(){'),source.indexOf('async function api(')),context);
vm.runInContext(source.slice(source.indexOf('let forecastRequestVersion='),source.indexOf('async function start(){')),context);
(async()=>{
  let old=vm.runInContext('runForecast()',context);
  assert.equal(elements.value.textContent,'—');
  assert(requests[0].path.includes('2026-10-19T22%3A00%3A00.000Z'));
  elements.forecastTarget.value='solar';vm.runInContext('forecastInputsChanged()',context);
  requests[0].resolve({target:'load',rows:[{timestamp:'2026-10-19T22:00:00Z',predicted:99}]});await old;
  assert.equal(elements.value.textContent,'—');assert.equal(chart.length,0);
  let current=vm.runInContext('runForecast()',context);
  requests[1].resolve({target:'solar',rows:[{timestamp:'2026-10-19T22:00:00Z',predicted:123}],source_latest:'2026-08-28T22:00:00Z',limitation:'Extrapolation'});await current;
  assert.equal(elements.chartTitle.textContent,'Solar Generation');
  assert.equal(elements.value.textContent,'123 MW');assert(elements.time.textContent.includes('20/10/2026'));
  let failed=vm.runInContext('runForecast()',context);requests[2].reject(new Error('Test failure'));await failed;
  assert.equal(elements.value.textContent,'—');assert.equal(chart.length,0);assert(elements.forecastNotice.textContent.includes('Test failure'));
  let mismatched=vm.runInContext('runForecast()',context);requests[3].resolve({target:'load',rows:[{timestamp:'2026-08-21T05:00:00Z',predicted:456}]});await mismatched;
  assert.equal(elements.value.textContent,'—');assert(elements.forecastNotice.textContent.includes('does not match'));
  console.log('PASS: India date serialization, stale responses, input invalidation, selected target/date, errors and response mismatch.');
})().catch(e=>{console.error(e);process.exitCode=1;});

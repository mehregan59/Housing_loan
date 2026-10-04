import assert from 'node:assert/strict';
// Import the single-file Supabase function without opening a server or accessing secrets.
let handler;
const env={TELEGRAM_WEBHOOK_SECRET:'test-secret',ADMIN_USER_ID:'123',SUPABASE_URL:'https://db.test',
  BOT_DATABASE_KEY:'fake-key',TELEGRAM_BOT_TOKEN:'fake-token'};
globalThis.Deno={env:{get(k){return env[k];}},serve(fn){handler=fn;}};
const {parseEdit,settingsSummary,splitReport,reportPage,setupGuide}=await import('../supabase/functions/telegram/index.ts');
assert.equal(parseEdit('max_price_eur','€250,000'),250000);
assert.equal(parseEdit('max_loan_eur','250.000'),250000);
assert.equal(parseEdit('equity_eur','0'),0);
assert.equal(parseEdit('repayment_pct','2,5%'),2.5);
assert.equal(parseEdit('min_monthly_cashflow_eur','-150'),-150);
assert.equal(parseEdit('target_gross_yield_pct','none'),null);
assert.deepEqual(parseEdit('areas','Freiburg, Emmendingen'),['Freiburg','Emmendingen']);
assert.deepEqual(parseEdit('areas','none'),[]);
assert.throws(()=>parseEdit('max_price_eur','-1'));
assert.throws(()=>parseEdit('fixed_rate_years','2.5'));
assert.throws(()=>parseEdit('schedule_time','25:00'));
assert.throws(()=>parseEdit('timezone','Invalid/Timezone'));
assert.equal(parseEdit('schedule_time','18:30'),'18:30');
assert.equal(parseEdit('timezone','Europe/Berlin'),'Europe/Berlin');
const summary=settingsSummary({settings:{location:'Freiburg',radius_km:100,max_price_eur:250000,
  max_loan_eur:250000,equity_eur:0,min_size_m2:30,language:'en',fixed_rate_years:10,
  repayment_pct:2,areas:[],exclude:['Erbpacht','Zwangsversteigerung'],target_gross_yield_pct:null,
  min_monthly_cashflow_eur:null,max_price_per_m2:null,_edit:{field:'private_internal_state'}},
  weekly:false,schedule_day:0,schedule_time:'08:00',timezone:'Europe/Berlin',plan:'free'});
assert.match(summary,/€250,000/);
assert.match(summary,/No filter set/);
assert.match(summary,/Monday, 08:00/);
assert.match(summary,/Weekly reports: Off/);
assert.doesNotMatch(summary,/private_internal_state|null|"max_price_eur"/);
console.log('Settings display and input validation checks passed');

// Exercise actual webhook edit flow with fake storage and Telegram, no network/API calls.
let user={user_id:123,approved:true,accepted_at:'2026-10-04',weekly:false,schedule_day:0,
  schedule_time:'08:00',timezone:'Europe/Berlin',plan:'free',settings:{_guide_version:1,location:'Freiburg',country:'Germany',
  areas:[],exclude:[],radius_km:100,max_price_eur:250000,max_loan_eur:250000,equity_eur:0,
  min_size_m2:30,language:'en',fixed_rate_years:10,repayment_pct:2}};
const messages=[];
globalThis.fetch=async(url,options={})=>{
  if(url.startsWith('https://api.telegram.org/')) {
    if(url.endsWith('/sendMessage')) messages.push(JSON.parse(options.body));
    return Response.json({ok:true});
  }
  if(url.startsWith('https://db.test/rest/v1/bot_control')) return Response.json([{}]);
  assert.ok(url.startsWith('https://db.test/rest/v1/bot_users'), 'No paid or dispatch endpoint allowed');
  if(options.method==='PATCH') user={...user,...JSON.parse(options.body)};
  return Response.json([structuredClone(user)]);
};
async function send(text,callback=false){
  const message={chat:{id:123,type:'private'},from:{id:123},text};
  const payload=callback?{callback_query:{id:'cb',from:{id:123},message,data:text}}:{message};
  const response=await handler(new Request('https://webhook.test',{method:'POST',
    headers:{'X-Telegram-Bot-Api-Secret-Token':'test-secret'},body:JSON.stringify(payload)}));
  assert.equal(response.status,200);
}
await send('/settings');
assert.match(messages.at(-1).text,/Your property search/);
assert.ok(messages.at(-1).reply_markup.inline_keyboard.length>0);
await send('edit:max_price_eur',true);
await send('-10');
assert.equal(user.settings.max_price_eur,250000);
assert.ok(user.settings._edit,'Invalid value keeps edit active');
await send('€220,000');
assert.equal(user.settings.max_price_eur,220000);
assert.equal(user.settings._edit,undefined);
await send('edit:equity_eur',true);
await send('/cancel');
assert.equal(user.settings.equity_eur,0);
assert.equal(user.settings._edit,undefined);
await send('day:4',true);
assert.equal(user.schedule_day,4);
await send('weekly:on',true);
assert.equal(user.weekly,true);
await send('lang:de',true);
assert.equal(user.settings.language,'de');
await send('lang:fa',true);
assert.equal(user.settings.language,'fa');
await send('/settings');assert.match(messages.at(-1).text,/زبان گزارش: فارسی/);
await send('/help');assert.match(messages.at(-1).text,/راهنمای ربات/);
await send('lang:en',true);

console.log('Webhook button/input/cancel flow passed without external calls');

// Private access requests and admin decisions: no real messages, database, or API calls.
const users=new Map([[123,structuredClone(user)]]);
let control={id:1,admin_user_id:null};
let failAdminNotification=false;
globalThis.fetch=async(address,options={})=>{
  if(address.startsWith('https://api.telegram.org/')) {
    if(address.endsWith('/sendMessage')) {
      const body=JSON.parse(options.body);
      if(failAdminNotification&&body.chat_id===123&&body.text.startsWith('📩 Access request')) return Response.json({ok:false},{status:500});
      messages.push(body);
    }
    return Response.json({ok:true});
  }
  const parsed=new URL(address);
  if(parsed.pathname==='/rest/v1/bot_control') {
    if(options.method==='PATCH') control={...control,...JSON.parse(options.body)};
    return Response.json([structuredClone(control)]);
  }
  assert.equal(parsed.pathname,'/rest/v1/bot_users','Access must never dispatch paid work');
  const id=Number((parsed.searchParams.get('user_id')||'eq.0').slice(3));
  if(options.method==='GET') return Response.json(users.has(id)?[structuredClone(users.get(id))]:[]);
  const body=JSON.parse(options.body);
  if(options.method==='POST') {
    if(users.has(body.user_id)) return Response.json({}, {status:409});
    const created={...structuredClone(user),user_id:body.user_id,accepted_at:null,plan:'free',settings:{...structuredClone(user.settings)},...body};
    users.set(body.user_id,created);return Response.json([created]);
  }
  assert.equal(options.method,'PATCH');
  const target=users.get(id);if(!target) return Response.json([]);
  if(parsed.searchParams.get('approved')==='eq.false'&&target.approved) return Response.json([]);
  const access=target.settings._access;
  const nonce=parsed.searchParams.get('settings->_access->>nonce');
  const status=parsed.searchParams.get('settings->_access->>status');
  if(nonce&&access?.nonce!==nonce.slice(3)) return Response.json([]);
  if(status&&access?.status!==status.slice(3)) return Response.json([]);
  if(parsed.searchParams.get('settings->_access')==='is.null'&&access) return Response.json([]);
  const changed={...target,...body};users.set(id,changed);return Response.json([structuredClone(changed)]);
};
async function sendAs(id,text,callback=false){
  const message={chat:{id,type:'private'},from:{id,first_name:'Test applicant'},text};
  const payload=callback?{callback_query:{id:'access-cb',from:message.from,message,data:text}}:{message};
  const response=await handler(new Request('https://webhook.test',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':'test-secret'},body:JSON.stringify(payload)}));
  assert.equal(response.status,200);
}
await sendAs(456,'/start');
assert.equal(messages.at(-1).reply_markup.inline_keyboard[0][0].callback_data,'request_access');
assert.doesNotMatch(messages.at(-1).text,/123|Ask the operator/);
await sendAs(456,'request_access',true);
const request=messages.findLast(m=>m.chat_id===123&&m.text.startsWith('📩 Access request'));
assert.match(request.text,/456/);
const approve=request.reply_markup.inline_keyboard[0][0].callback_data;
assert.ok(approve.length<64);
assert.equal(users.get(456).approved,false);
const before=messages.filter(m=>m.chat_id===123&&m.text.startsWith('📩')).length;
await sendAs(456,'request_access',true);
assert.equal(messages.filter(m=>m.chat_id===123&&m.text.startsWith('📩')).length,before);
await sendAs(789,approve,true);
assert.equal(users.get(456).approved,false,'Other users cannot approve');
users.get(456).plan='paid'; // Approval must start free even if previously marked paid.
await sendAs(123,approve,true);
assert.equal(users.get(456).approved,true);assert.equal(users.get(456).plan,'free');
assert.equal(users.get(456).accepted_at,null,'Approval does not accept the notice');
assert.ok(messages.some(m=>m.chat_id===456&&m.text.startsWith('✅ Your access')));
await sendAs(123,approve.replace('approve','decline'),true);
assert.equal(users.get(456).approved,true,'Stale decline cannot revoke approved user');
await sendAs(800,'request_access',true);
const deniedRequest=messages.findLast(m=>m.chat_id===123&&m.text.includes('Telegram ID: 800'));
const decline=deniedRequest.reply_markup.inline_keyboard[0][1].callback_data;
await sendAs(123,decline,true);
assert.equal(users.get(800).approved,false);assert.equal(users.get(800).settings._access.status,'declined');
await sendAs(800,'request_access',true);
assert.match(messages.at(-1).text,/24 hours/);
users.get(800).settings._access.at-=25*60*60*1000;
await sendAs(800,'request_access',true);
const newNonce=users.get(800).settings._access.nonce;
await sendAs(123,decline,true);
assert.equal(users.get(800).settings._access.nonce,newNonce);
assert.equal(users.get(800).settings._access.status,'pending','Old buttons cannot decide replacement request');
failAdminNotification=true;
await sendAs(900,'request_access',true);
assert.equal(users.get(900).settings._access,undefined,'Notification failure permits a safe retry');
failAdminNotification=false;
await sendAs(900,'request_access',true);
assert.equal(users.get(900).settings._access.status,'pending');
console.log('Private requests, admin-only decisions, free defaults, cooldown and stale buttons passed');
assert.equal(control.admin_user_id,123,'Only configured administrator bound to quota exemption');
await sendAs(123,'/settings');
assert.match(messages.at(-1).text,/Administrator — no weekly report limit/);
await sendAs(456,'/start');
assert.equal(control.admin_user_id,123,'Applicant cannot change administrator quota identity');

// /run and /saved serve exact-setting cached reports before quotas/dispatch.
control={id:1,admin_user_id:123,research_v2:true,shared_reports_enabled:true};
users.get(456).accepted_at='2026-10-04';
let cachedReport='Shared property report';
const oldFetch=globalThis.fetch;
let queueCalls=0;
globalThis.fetch=async(address,options={})=>{
  if(address.includes('/rpc/bot_saved_report')) {
    assert.equal(JSON.parse(options.body).p_user,456);
    return Response.json(cachedReport?{report:cachedReport,urls:[]}:null);
  }
  if(address.includes('/rpc/bot_enqueue')) {queueCalls++;throw new Error('Cached retrieval must never enqueue');}
  return oldFetch(address,options);
};
await sendAs(456,'/run');assert.equal(queueCalls,0);assert.equal(messages.at(-1).text,cachedReport);
assert.match(messages.at(-2).text,/No quota used/);
await sendAs(456,'saved',true);assert.equal(queueCalls,0);assert.equal(messages.at(-1).text,cachedReport);
cachedReport=('🏠 Apartment\n📍 Freiburg\n'+'Details '.repeat(400)+'\n\n').repeat(12);
const messageStart=messages.length;
await sendAs(456,'/saved');
const reportParts=messages.slice(messageStart).filter(m=>m.chat_id===456).map(m=>m.text);
// The introductory notification is separate from the stored report.
const firstPart=reportParts.findIndex(t=>t.startsWith('🏠 Apartment'));
const chunks=reportParts.slice(firstPart);
assert.ok(chunks.length>2);
assert.equal(chunks.join(''),cachedReport);
assert.ok(chunks.every(t=>t.length<=3800 && !/[\uD800-\uDBFF]$/.test(t) && !/^[\uDC00-\uDFFF]/.test(t)));
assert.equal(queueCalls,0);
cachedReport='';
await sendAs(456,'/saved');assert.match(messages.at(-1).text,/No current shared report/);assert.equal(queueCalls,0);
control.research_v2=false;
await sendAs(456,'/run');assert.match(messages.at(-1).text,/No paid run started/);assert.equal(queueCalls,0);
console.log('Saved retrieval bypasses quotas and queues; inactive upgrade blocks paid runs');

// Refresh never bypasses administrator permission or the database budget gate.
control.research_v2=true;
await sendAs(456,'/refresh');
assert.match(messages.at(-1).text,/Only the administrator/);
assert.equal(queueCalls,0);
const refreshFetch=globalThis.fetch;
let refreshRequests=0;
globalThis.fetch=async(address,options={})=>{
  if(address.includes('/rpc/bot_enqueue')) {
    const request=JSON.parse(options.body);
    assert.equal(request.p_user,123);assert.match(request.p_key,/^refresh:/);
    refreshRequests++;
    return Response.json({error:'MonthlyBudgetExceeded'});
  }
  if(address.includes('/rpc/bot_saved_report')) throw new Error('Refresh must bypass saved reports');
  return refreshFetch(address,options);
};
await sendAs(123,'/refresh');
assert.equal(refreshRequests,1);
assert.match(messages.at(-1).text,/MonthlyBudgetExceeded/);
console.log('Persian settings/help and administrator refresh budget gate passed');

// The Python worker and webhook must show identical report indices.
const {readFileSync}=await import('node:fs');
const {execFileSync}=await import('node:child_process');
const cases=JSON.parse(execFileSync('python',['-c',`import json,sys
from report_pages import split_report,page
cases=json.load(sys.stdin)
for c in cases:
 v=split_report(c['report']);c['view']=v
 c['pages']=[{'text':page(v,'j00000000-0000-4000-8000-000000000001',i,c['language'])[0],'entities':page(v,'j00000000-0000-4000-8000-000000000001',i,c['language'])[1]} for i in range(2)]
print(json.dumps(cases))`],{input:readFileSync('tests/fixtures/report_views.json','utf8'),encoding:'utf8'}));
const reportJob='00000000-0000-4000-8000-000000000001';
for(const c of cases) {
  const view=splitReport(c.report);
  assert.deepEqual(view,c.view);
  for(let i=0;i<c.pages.length;i++) assert.deepEqual(reportPage(view,'j'+reportJob,i,c.language),c.pages[i]);
}
const navigationFetch=globalThis.fetch;
const edited=[];
globalThis.fetch=async(address,options={})=>{
  if(address.includes('/editMessageText')) {edited.push(JSON.parse(options.body));return Response.json({ok:true});}
  if(address.includes('/rest/v1/bot_jobs?')) {
    const q=new URL(address).searchParams;
    assert.equal(q.get('user_id'),'eq.456','Details must be scoped to requesting user');
    assert.equal(q.get('status'),'eq.complete');
    return Response.json(q.get('id')==='eq.'+reportJob?[{report:cases[0].report}]:[]);
  }
  if(address.includes('/rpc/bot_saved_report')) return Response.json({report:cases[0].report});
  return navigationFetch(address,options);
};
async function navigate(data) {
  const body={callback_query:{id:'nav',from:{id:456},message:{message_id:100,chat:{id:456,type:'private'}},data}};
  const r=await handler(new Request('https://webhook.test',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':'test-secret'},body:JSON.stringify(body)}));
  assert.equal(r.status,200);
}
await navigate('prop:j'+reportJob+':6');
assert.match(edited.at(-1).text,/Apartment 6/);
assert.match(edited.at(-1).text,/Owner building fees/);
assert.equal(edited.at(-1).entities.at(-1).url,'https://t.me/MeHousingLoanBot?start=list_j'+reportJob+'_0');
assert.deepEqual(edited.at(-1).reply_markup.inline_keyboard,[]);
await navigate('list:j'+reportJob+':0');assert.match(edited.at(-1).text,/Page 1\/2/);
await navigate('notes:j'+reportJob);assert.match(edited.at(-1).text,/MORTGAGE RATES/);
const editedBefore=edited.length;
await navigate('prop:j00000000-0000-4000-8000-000000000002:0');
assert.equal(edited.length,editedBefore);assert.match(messages.at(-1).text,/no longer available/);
const {createHash}=await import('node:crypto');
const savedHash=createHash('sha256').update(cases[0].report).digest('hex').slice(0,12);
await navigate('prop:s'+savedHash+':0');assert.match(edited.at(-1).text,/Apartment 0/);
await navigate('prop:s000000000000:0');assert.match(messages.at(-1).text,/no longer available/);
assert.equal(queueCalls,0,'Navigation never queues paid work');
console.log('Summary parity, private detail navigation, back button, notes and stale saved links passed');

// Text links enter via /start payload, with the same private access checks.
const beforeDeepLink=edited.length;
await sendAs(456,'/start prop_j'+reportJob+'_6');
assert.match(messages.at(-1).text,/Apartment 6/);
assert.equal(edited.length,beforeDeepLink,'Never edit a user /start message');
assert.equal(messages.at(-1).entities.at(-1).url,'https://t.me/MeHousingLoanBot?start=list_j'+reportJob+'_0');
assert.equal(messages.at(-1).reply_markup,undefined,'No table of buttons below details');
await sendAs(456,'/start list_j'+reportJob+'_0');
assert.match(messages.at(-1).text,/Gross rental yield:[^\n]+ · Details · Listing/);
assert.ok(messages.at(-1).entities.some(e=>e.url.includes('prop_j')));
assert.equal(messages.at(-1).reply_markup,undefined);
await sendAs(456,'/start prop_j00000000-0000-4000-8000-000000000002_0');
assert.match(messages.at(-1).text,/no longer available/);
assert.equal(queueCalls,0);
console.log('Inline text links, deep-link details/back navigation and owner access checks passed');

// Guide explains settings before offering the first run, and resumes after edits.
for(const language of ['en','de','fa']) {
  for(let step=0;step<7;step++) {
    const guide=setupGuide(step,language,users.get(456));
    const actions=guide.keyboard.inline_keyboard.flat().map(b=>b.callback_data);
    assert.equal(actions.includes('run'),false);
    assert.equal(actions.includes('guide:complete'),step===6);
    if(language==='fa') assert.match(guide.text,/راهنما|جستجو|تأمین|معیار|گزارش|زمان|تنظیمات/);
  }
}
delete users.get(456).settings._guide_version;
await sendAs(456,'/run');assert.match(messages.at(-1).text,/1\/7/);
assert.equal(queueCalls,0);
await sendAs(456,'guide:complete',true);assert.notEqual(users.get(456).settings._guide_version,1);
await sendAs(456,'/guide');assert.match(messages.at(-1).text,/1\/7/);
await sendAs(456,'guide:1',true);assert.equal(users.get(456).settings._guide_step,1);
await sendAs(456,'edit:max_price_eur',true);
await sendAs(456,'240000');assert.equal(users.get(456).settings.max_price_eur,240000);
await sendAs(456,'guide:resume',true);assert.match(messages.at(-1).text,/2\/7/);
assert.equal(users.get(456).settings._edit,undefined);
await sendAs(456,'guide:6',true);assert.equal(users.get(456).settings._guide_step,2,'Cannot skip unread steps');
for(let step=3;step<=6;step++) await sendAs(456,'guide:'+step,true);
assert.match(messages.at(-1).text,/Review, then start/);
assert.match(messages.at(-1).text,/240,000/);
assert.equal(queueCalls,0);assert.equal(refreshRequests,1,'Guide never requests extra paid work');
await sendAs(456,'guide:complete',true);assert.equal(users.get(456).settings._guide_version,1);
console.log('Guide translations, final review, edit/resume and no-analysis navigation passed');

control.pilot_locked=true;
await sendAs(456,'/settings');assert.match(messages.at(-1).text,/Pilot settings are fixed/);
const pilotOldPrice=users.get(456).settings.max_price_eur;
await sendAs(456,'/set max_price_eur 123456');assert.match(messages.at(-1).text,/Pilot settings and weekly schedule are fixed/);
assert.equal(users.get(456).settings.max_price_eur,pilotOldPrice);
await sendAs(456,'menu:search',true);assert.match(messages.at(-1).text,/Pilot settings and weekly schedule are fixed/);
await sendAs(456,'/schedule tue 20:00 Europe/Berlin');assert.match(messages.at(-1).text,/Pilot settings and weekly schedule are fixed/);
console.log('Pilot edit and schedule locks passed');

// Payment updates have no ordinary message; validate checkout and durable success.
const paymentCalls=[];
globalThis.fetch=async(url,options={})=>{
  const body=options.body?JSON.parse(options.body):{};
  paymentCalls.push({url,body});
  if(url.endsWith('/rpc/bot_order_checkout')) return Response.json(body.p_amount===50&&body.p_currency==='XTR'?{ok:true}:{error:'invalid_invoice'});
  if(url.endsWith('/rpc/bot_order_paid')) return Response.json({duplicate:true,state:'paid',product:'weekly30'});
  if(url.startsWith('https://api.telegram.org/')) return Response.json({ok:true});
  throw new Error('Unexpected payment endpoint');
};
async function paymentUpdate(payload) {
  const response=await handler(new Request('https://webhook.test',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':'test-secret'},body:JSON.stringify(payload)}));
  assert.equal(response.status,200);
}
const payload='housing:00000000-0000-4000-8000-000000000001';
await paymentUpdate({pre_checkout_query:{id:'checkout',from:{id:321},invoice_payload:payload,total_amount:50,currency:'XTR'}});
assert.equal(paymentCalls.at(-1).body.ok,true);
await paymentUpdate({pre_checkout_query:{id:'checkout-bad',from:{id:321},invoice_payload:payload,total_amount:49,currency:'XTR'}});
assert.equal(paymentCalls.at(-1).body.ok,false);
const count=paymentCalls.length;
await paymentUpdate({message:{chat:{id:321,type:'private'},from:{id:321},successful_payment:{invoice_payload:payload,total_amount:50,currency:'XTR',telegram_payment_charge_id:'charge'}}});
assert.equal(paymentCalls.length,count+1,'Duplicate payment must not send or dispatch again');
assert.ok(paymentCalls.at(-1).url.endsWith('/rpc/bot_order_paid'));
console.log('Stars checkout, wrong-price rejection and duplicate payment routing passed');

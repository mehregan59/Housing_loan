import assert from 'node:assert/strict';
// Import the single-file Supabase function without opening a server or accessing secrets.
let handler;
const env={TELEGRAM_WEBHOOK_SECRET:'test-secret',ADMIN_USER_ID:'123',SUPABASE_URL:'https://db.test',
  BOT_DATABASE_KEY:'fake-key',TELEGRAM_BOT_TOKEN:'fake-token'};
globalThis.Deno={env:{get(k){return env[k];}},serve(fn){handler=fn;}};
const {parseEdit,settingsSummary}=await import('../supabase/functions/telegram/index.ts');
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
  schedule_time:'08:00',timezone:'Europe/Berlin',plan:'free',settings:{location:'Freiburg',country:'Germany',
  areas:[],exclude:[],radius_km:100,max_price_eur:250000,max_loan_eur:250000,equity_eur:0,
  min_size_m2:30,language:'en',fixed_rate_years:10,repayment_pct:2}};
const messages=[];
globalThis.fetch=async(url,options={})=>{
  if(url.startsWith('https://api.telegram.org/')) {
    if(url.endsWith('/sendMessage')) messages.push(JSON.parse(options.body));
    return Response.json({ok:true});
  }
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
console.log('Webhook button/input/cancel flow passed without external calls');

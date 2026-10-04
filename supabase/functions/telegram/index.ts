// Short webhook only: long OpenAI work runs in GitHub Actions.
const env = (key: string) => { const v = Deno.env.get(key); if (!v) throw new Error('Missing configuration'); return v; };
const NOTICE = 'Estimates only; general information, not financial advice or a financing commitment. Verify independently before deciding. Listing data may be incomplete. Settings and reports are stored in Supabase; analysis uses OpenAI; Telegram delivers messages. API costs are reported to the administrator. Do not send bank credentials or identity documents. /support forwards your message and Telegram ID to the administrator. This is a private pilot, not a publicly launched service.';
const HELP = `Housing Loan Bot — Germany pilot
/start — read notice and accept
/settings — your investment settings; tap buttons to edit each field
/cancel — cancel the current edit
/set FIELD VALUE — change one setting
Example: /set max_price_eur 250000
/location Freiburg — choose a German city
/areas Freiburg, Emmendingen — preferred towns
/exclude Erbpacht, Zwangsversteigerung — exclusions; "none" clears
/schedule mon 08:00 Europe/Berlin — day, time, timezone
/weekly on or /weekly off — automatic report
/run — analysis using saved research where available
/refresh — administrator only: paid search for additional apartments within the spending cap
/quota — weekly allowance
/last — latest saved report
/saved — existing report for your exact settings; no quota or AI cost
/support YOUR QUESTION — contact the administrator
/disclaimer — notice and data use
Free: 1 report/week. Paid: up to 7. Scheduled reports count too. Reset Monday 00:00 Europe/Berlin. Manual membership during pilot. Delivery may be delayed; changing schedule does not add reports. If a report fails, use /support; repeated clicks cannot start parallel analyses.
Editable numeric fields: max_loan_eur, equity_eur, max_price_eur, min_size_m2, radius_km, max_price_per_m2, target_gross_yield_pct, min_monthly_cashflow_eur, fixed_rate_years, repayment_pct. Optional targets accept "none". /set language en, de or fa. Other countries will require country-specific rules in a future release.`;
const HELP_FA=`راهنمای ربات مسکن — آلمان
/settings — تنظیمات؛ برای تغییر هر مورد دکمه را بزنید
/set language fa — گزارش فارسی
/set language en — گزارش انگلیسی
/set language de — گزارش آلمانی
/location Freiburg — انتخاب شهر آلمان
/areas Freiburg, Emmendingen — شهرهای ترجیحی
/set max_price_eur 250000 — حداکثر قیمت خرید
/set max_loan_eur 250000 — سقف وام
/set equity_eur 0 — آورده نقدی
/set min_size_m2 30 — حداقل مساحت
/set radius_km 100 — شعاع جستجو
/run — بررسی با استفاده از داده‌های ذخیره‌شده در صورت موجود بودن
/saved — گزارش ذخیره‌شده بدون هزینه جدید
/last — آخرین گزارش
/weekly on یا /weekly off — گزارش هفتگی
/schedule mon 08:00 Europe/Berlin — زمان گزارش
/quota — سهمیه هفتگی
/support متن سؤال — ارسال سؤال به پشتیبانی
/cancel — لغو ویرایش
/refresh — فقط مدیر؛ جستجوی پولی برای آگهی‌های بیشتر در سقف بودجه
طرح رایگان یک گزارش و طرح پولی تا هفت گزارش در هفته دارد. گزارش‌ها فقط برآورد هستند، نه مشاوره مالی یا تأیید وام. عنوان آگهی و متن ریسک منبع ممکن است به زبان اصلی باقی بماند.`;
const MAX: Record<string, [number, number]> = {
  max_loan_eur:[0,10000000],equity_eur:[0,10000000],max_price_eur:[1,10000000],
  min_size_m2:[1,2000],radius_km:[1,500],max_price_per_m2:[1,100000],
  target_gross_yield_pct:[0,100],min_monthly_cashflow_eur:[-100000,100000],
  fixed_rate_years:[1,40],repayment_pct:[0,30]
};
const OPTIONAL = new Set(['max_price_per_m2','target_gross_yield_pct','min_monthly_cashflow_eur']);

const DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const LABELS: Record<string,string> = {
  location:'City', areas:'Preferred towns', radius_km:'Search radius',
  max_price_eur:'Maximum purchase price',max_loan_eur:'Maximum loan',equity_eur:'Available equity',
  min_size_m2:'Minimum size',language:'Report language',fixed_rate_years:'Fixed interest period',
  repayment_pct:'Initial annual repayment',max_price_per_m2:'Maximum price per m²',
  target_gross_yield_pct:'Target gross rental yield',min_monthly_cashflow_eur:'Minimum monthly cashflow',
  schedule_time:'Delivery time',timezone:'Timezone'
};
const GROUPS: Record<string,string[]> = {
  search:['location','areas','radius_km','max_price_eur','min_size_m2','language'],
  finance:['max_loan_eur','equity_eur','fixed_rate_years','repayment_pct'],
  targets:['max_price_per_m2','target_gross_yield_pct','min_monthly_cashflow_eur'],
  schedule:['schedule_time','timezone']
};
const button=(text:string,data:string)=>({text,callback_data:data});
const money=(v:unknown)=>new Intl.NumberFormat('en-GB',{style:'currency',currency:'EUR',maximumFractionDigits:2}).format(Number(v));
export function settingsSummary(u:any):string {
  const s=u.settings;
  if (s.language==='fa') {
    const option=(key:string,unit:string)=>s[key]==null?'بدون محدودیت':unit==='EUR'?money(s[key]):s[key]+unit;
    return `🏠 تنظیمات جستجوی ملک
📍 ${s.location}، آلمان · شعاع ${s.radius_km} کیلومتر
شهرهای ترجیحی: ${(s.areas||[]).join(', ')||'بدون ترجیح اضافی'}
💶 حداکثر قیمت خرید: ${money(s.max_price_eur)}
📐 حداقل مساحت: ${s.min_size_m2} متر مربع
🌐 زبان گزارش: فارسی

🏦 فرض‌های تأمین مالی
حداکثر وام: ${money(s.max_loan_eur)}
آورده نقدی: ${money(s.equity_eur)}
دوره نرخ ثابت: ${s.fixed_rate_years} سال
بازپرداخت اولیه سالانه: ${s.repayment_pct}%

🎯 معیارهای سرمایه‌گذاری
حداکثر قیمت هر متر مربع: ${option('max_price_per_m2','EUR')}
بازده ناخالص اجاره: ${option('target_gross_yield_pct','%')}
حداقل نتیجه ماهانه: ${option('min_monthly_cashflow_eur','EUR')}
🚫 موارد مستثنا: ${(s.exclude||[]).map((x:string)=>x==='Erbpacht'?'ملک با حق اجاره زمین':x==='Zwangsversteigerung'?'مزایده توقیفی':x).join('، ')||'هیچ‌کدام'}
📅 گزارش هفتگی: ${u.weekly?'روشن':'خاموش'}
زمان: ${DAYS[u.schedule_day]}، ${u.schedule_time} · ${u.timezone}
طرح: ${u.admin_unlimited?'مدیر؛ بدون سقف هفتگی':u.plan==='paid'?'اشتراک پولی؛ تا ۷ گزارش در هفته':'رایگان؛ یک گزارش در هفته'}
برای تغییر تنظیمات دکمه‌های زیر را بزنید. هزینه‌های خرید در محاسبه وام لحاظ می‌شود؛ این تنظیمات تأیید تأمین مالی نیست.`;
  }
  const optional=(key:string,unit:string)=>s[key]==null?'No filter set':unit==='EUR'?money(s[key]):s[key]+unit;
  const exclusions=(s.exclude||[]).map((x:string)=>x==='Erbpacht'?'Leasehold':x==='Zwangsversteigerung'?'Foreclosure auctions':x).join(', ')||'None';
  return `🏠 Your property search
📍 ${s.location}, Germany · within ${s.radius_km} km
Preferred towns: ${(s.areas||[]).join(', ')||'No additional preference'}
💶 Maximum purchase price: ${money(s.max_price_eur)}
📐 Minimum size: ${s.min_size_m2} m²
🌐 Report language: ${s.language==='fa'?'فارسی':s.language==='de'?'German':'English'}

🏦 Financing assumptions
Maximum loan: ${money(s.max_loan_eur)}
Available equity: ${money(s.equity_eur)}
Fixed interest period: ${s.fixed_rate_years} years
Initial annual repayment: ${s.repayment_pct}%

🎯 Investment targets
Maximum price per m²: ${optional('max_price_per_m2','EUR')}
Gross rental yield: ${optional('target_gross_yield_pct','%')}
Monthly cashflow: ${optional('min_monthly_cashflow_eur','EUR')}

🚫 Excluded: ${exclusions}

📅 Weekly reports: ${u.weekly?'On':'Off'}
Schedule: ${DAYS[u.schedule_day]}, ${u.schedule_time} · ${u.timezone}
Plan: ${u.admin_unlimited?'Administrator — no weekly report limit':u.plan==='paid'?'Paid — up to 7 reports/week':'Free — 1 report/week'}

Tap a button below to edit. Purchase costs count toward your loan limit. These are preferences, not a financing approval.`;
}
const settingsButtons={inline_keyboard:[
  [button('🔎 Edit search','menu:search'),button('🏦 Edit financing','menu:finance')],
  [button('🎯 Investment targets','menu:targets'),button('🚫 Exclusions','menu:exclude')],
  [button('📅 Change schedule','menu:schedule')],
  [button('🔎 Run analysis','run'),button('❓ Help','help')]
]};
export function parseEdit(field:string,input:string):unknown {
  let value=input.trim();
  if (['location','areas'].includes(field)) {
    if (!value || value.length>(field==='location'?100:500)) throw new Error('Enter a city name or a short list of towns.');
    return field==='location'?value:value.toLowerCase()==='none'?[]:value.split(',').map(x=>x.trim()).filter(Boolean).slice(0,15);
  }
  if (field==='language') { if (!['en','de','fa'].includes(value)) throw new Error('Choose English, German or Persian below.'); return value; }
  if (field==='timezone') { try { new Intl.DateTimeFormat('en',{timeZone:value}).format(); } catch { throw new Error('Enter a timezone such as Europe/Berlin.'); } return value; }
  if (field==='schedule_time') {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(value)) throw new Error('Enter a 24-hour time, for example 08:00 or 18:30.');
    return value;
  }
  if (OPTIONAL.has(field) && value.toLowerCase()==='none') return null;
  // Accept 250000, 250 000, 250,000, 250.000, €250,000 and decimal comma percentages.
  value=value.replace(/[€%\s]/g,'').replace(/(?:km|m²|m2|years?)$/i,'');
  if (/^-?\d{1,3}(?:[,.]\d{3})+$/.test(value)) value=value.replace(/[,.]/g,'');
  else if (/^-?\d+,\d{1,2}$/.test(value)) value=value.replace(',','.');
  if (!/^-?\d+(?:\.\d+)?$/.test(value)) throw new Error('Enter a number, for example 250000 or 2.5.');
  const n=Number(value), bounds=MAX[field];
  if (!bounds || !Number.isFinite(n) || n<bounds[0] || n>bounds[1] || (field==='fixed_rate_years'&&!Number.isInteger(n))) {
    throw new Error(bounds?`Enter a value from ${bounds[0]} to ${bounds[1]}${field==='fixed_rate_years'?' in whole years':''}.`:'Unknown setting.');
  }
  return n;
}
function editPrompt(field:string):string {
  const examples:Record<string,string>={location:'Freiburg (Germany only)',areas:'Freiburg, Emmendingen — or none',radius_km:'100',max_price_eur:'250000',
    max_loan_eur:'250000',equity_eur:'0',min_size_m2:'30',fixed_rate_years:'10',repayment_pct:'2',
    max_price_per_m2:'5000',target_gross_yield_pct:'4',min_monthly_cashflow_eur:'-150',schedule_time:'08:00',timezone:'Europe/Berlin'};
  return `${LABELS[field]}\nSend the new value in your next message.\nExample: ${examples[field]||'en or de'}${OPTIONAL.has(field)?'\nSend none to remove this filter.':''}\nUse /cancel to leave without changing it.`;
}

async function db(method: string, path: string, body?: unknown) {
  const key = Deno.env.get('BOT_DATABASE_KEY') || env('SUPABASE_SERVICE_ROLE_KEY');
  const r = await fetch(env('SUPABASE_URL')+'/rest/v1/'+path, {
    method, headers:{apikey:key,'Content-Type':'application/json',Prefer:'return=representation'},
    body:body === undefined ? undefined : JSON.stringify(body), signal:AbortSignal.timeout(10000)
  });
  if (!r.ok) throw new Error('Database operation failed');
  return r.status === 204 ? null : await r.json();
}
async function tg(method: string, body: unknown) {
  const r = await fetch('https://api.telegram.org/bot'+env('TELEGRAM_BOT_TOKEN')+'/'+method, {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)
  });
  if (!r.ok || !(await r.json()).ok) throw new Error('Telegram operation failed');
}
async function reply(id: number, text: string, keyboard?: unknown) {
  let first = true;
  while (text.length) {
    let cut = Math.min(text.length,3800);
    // JavaScript counts UTF-16 units: never cut between an emoji's surrogates.
    if (cut < text.length) {
      const before = text.charCodeAt(cut-1);
      if (before >= 0xD800 && before <= 0xDBFF) cut--;
      const boundary = text.lastIndexOf('\n',cut-1);
      if (boundary >= Math.floor(cut/2)) cut = boundary+1;
    }
    await tg('sendMessage',{chat_id:id,text:text.slice(0,cut),link_preview_options:{is_disabled:true},
      ...(keyboard && first ? {reply_markup:keyboard} : {})});
    first = false;
    text = text.slice(cut);
  }
}

const buttons = {inline_keyboard:[[{text:'⚙️ My settings',callback_data:'settings'},{text:'🔎 Run analysis',callback_data:'run'}],[{text:'📂 Saved report (free)',callback_data:'saved'},{text:'Help',callback_data:'help'}]]};
async function dispatch(job: string) {
  const repo = env('GITHUB_REPOSITORY');
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) throw new Error('Invalid repository');
  const r = await fetch('https://api.github.com/repos/'+repo+'/actions/workflows/analyse.yml/dispatches', {
    method:'POST',headers:{Authorization:'Bearer '+env('GITHUB_DISPATCH_TOKEN'),Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'},
    body:JSON.stringify({ref:'main',inputs:{job_id:job}}),signal:AbortSignal.timeout(10000)
  });
  if (!r.ok) throw new Error('Dispatch failed');
}

Deno.serve(async req => {
  let replyTo: number | undefined;
  if (req.method!=='POST') return new Response('Method not allowed',{status:405});
  if (req.headers.get('X-Telegram-Bot-Api-Secret-Token')!==env('TELEGRAM_WEBHOOK_SECRET')) return new Response('Forbidden',{status:403});
  if (Number(req.headers.get('content-length') || 0)>16000) return new Response('Too large',{status:413});
  try {
    const raw = await req.text();
    if (raw.length>16000) return new Response('Too large',{status:413});
    const update = JSON.parse(raw);
    const cb = update.callback_query;
    const message = update.message || cb?.message;
    const sender = cb?.from || message?.from;
    if (!sender || sender.is_bot || message?.chat?.type!=='private') return new Response('ok');
    const id = Number(sender.id);
    if (!Number.isSafeInteger(id) || message.chat.id!==id) return new Response('Forbidden',{status:403});
    replyTo=id;
    if (cb) await tg('answerCallbackQuery',{callback_query_id:cb.id});
    const admin = Number(env('ADMIN_USER_ID'));
    const action=cb?String(cb.data):'';
    let rows = await db('GET','bot_users?user_id=eq.'+id);
    if (!rows.length && id===admin) rows = await db('POST','bot_users',{user_id:id,approved:true});
    // Only the configured private administrator can bind the database quota exemption.
    let adminUnlimited=false;
    if (id===admin) {
      const control=(await db('GET','bot_control?id=eq.1'))[0];
      if (control&&Object.prototype.hasOwnProperty.call(control,'admin_user_id')) {
        if (Number(control.admin_user_id)!==admin) await db('PATCH','bot_control?id=eq.1',{admin_user_id:admin});
        adminUnlimited=true;
      }
    }
    // Decisions are private, admin-only, and bound to the latest pending request.
    if (action.startsWith('access:')) {
      if (id!==admin) { await reply(id,'Only the administrator can decide access requests.'); return new Response('ok'); }
      const match=/^access:(approve|decline):(\d+):([a-f0-9]{12})$/.exec(action);
      if (!match) throw new Error('Invalid access decision');
      const target=Number(match[2]);
      if (!Number.isSafeInteger(target)||target<=0||target===admin) throw new Error('Invalid user');
      const targets=await db('GET','bot_users?user_id=eq.'+target);
      const candidate=targets[0];
      if (!candidate||candidate.approved||candidate.settings?._access?.status!=='pending'||candidate.settings._access.nonce!==match[3]) {
        await reply(id,'This request has already been decided or replaced.'); return new Response('ok');
      }
      const approved=match[1]==='approve';
      const settings={...candidate.settings,_access:{...candidate.settings._access,status:approved?'approved':'declined'}};
      const changed=await db('PATCH','bot_users?user_id=eq.'+target+'&approved=eq.false&settings->_access->>nonce=eq.'+match[3]+'&settings->_access->>status=eq.pending',
        {approved,settings,...(approved?{plan:'free'}:{})});
      if (!changed.length) { await reply(id,'This request has already been decided or replaced.'); return new Response('ok'); }
      await reply(id,(approved?'✅ Approved':'Declined')+' access for Telegram ID '+target+(approved?'. Free plan: one report per week.':'.'));
      try { await reply(target,approved?'✅ Your access is approved. Your free plan allows one report per week. Send /start and accept the notice to continue.':'Your access request was declined. You can request again 24 hours after your previous request.'); }
      catch { await reply(id,'The decision was saved, but notification failed. The user can send /start to check access.'); }
      return new Response('ok');
    }
    if (!rows.length || !rows[0].approved) {
      if (action==='request_access') {
        if (!rows.length) rows=await db('POST','bot_users',{user_id:id,approved:false});
        const candidate=rows[0]; const previous=candidate.settings?._access;
        if (previous?.status==='pending') {
          await reply(id,'Your request is waiting for approval. The bot will notify you here.'); return new Response('ok');
        }
        if (previous?.at&&Date.now()-previous.at<24*60*60*1000) {
          await reply(id,'You can send another request 24 hours after your previous request.'); return new Response('ok');
        }
        const nonce=crypto.randomUUID().replaceAll('-','').slice(0,12);
        const settings={...candidate.settings,_access:{status:'pending',nonce,at:Date.now()}};
        // Conditional write also prevents duplicate webhook deliveries from notifying twice.
        const condition=previous?.nonce?'&settings->_access->>nonce=eq.'+previous.nonce:'&settings->_access=is.null';
        const changed=await db('PATCH','bot_users?user_id=eq.'+id+'&approved=eq.false'+condition,{settings});
        if (!changed.length) { await reply(id,'Your request is already recorded. Send /start to check access.'); return new Response('ok'); }
        const name=String(sender.first_name||'Telegram user').replace(/[\r\n]/g,' ').slice(0,80);
        try {
          await reply(admin,'📩 Access request\nName: '+name+'\nTelegram ID: '+id+'\nApproval grants the free plan: one report per week.',
            {inline_keyboard:[[{text:'✅ Approve',callback_data:'access:approve:'+id+':'+nonce},{text:'Decline',callback_data:'access:decline:'+id+':'+nonce}]]});
        } catch {
          const retrySettings={...candidate.settings}; delete retrySettings._access;
          await db('PATCH','bot_users?user_id=eq.'+id+'&approved=eq.false&settings->_access->>nonce=eq.'+nonce+'&settings->_access->>status=eq.pending',{settings:retrySettings});
          await reply(id,'Could not send your request. Please tap Request access again later.');
          return new Response('ok');
        }
        await reply(id,'✅ Access request sent. You will receive the decision here; you do not need to contact anyone privately.');
      } else {
        await reply(id,'This bot currently requires approval. Tap Request access to send your Telegram name and ID privately to the administrator. The decision will arrive here.',
          {inline_keyboard:[[{text:'Request access',callback_data:'request_access'}]]});
      }
      return new Response('ok');
    }
    const user = rows[0];
    user.admin_unlimited=adminUnlimited;
    const text = String(cb ? '/'+cb.data : message.text || '').slice(0,2500).trim();
    const [rawcmd, ...parts] = text.split(/\s+/);
    const cmd = rawcmd.split('@')[0].toLowerCase();
    const rest = parts.join(' ');
    const clearEdit=async()=>{
      const clean={...user.settings}; delete clean._edit;
      await db('PATCH','bot_users?user_id=eq.'+id,{settings:clean}); user.settings=clean;
    };
    if (user.accepted_at && (cmd==='/cancel'||action==='cancel')) {
      await clearEdit(); await reply(id,'Edit cancelled. Your settings are unchanged.',settingsButtons); return new Response('ok');
    }
    if (user.accepted_at && action.startsWith('menu:')) {
      await clearEdit(); const group=action.slice(5);
      let keyboard:any;
      if (group==='exclude') {
        keyboard={inline_keyboard:[...['Erbpacht','Zwangsversteigerung'].map(x=>[button((user.settings.exclude.includes(x)?'☑️ ':'⬜ ')+(x==='Erbpacht'?'Exclude leasehold':'Exclude foreclosure auctions'),'toggle:'+x)]),[button('← My settings','settings')]]};
        await reply(id,'🚫 Exclusions\nTap an item to turn its exclusion on or off.',keyboard);
      } else if (GROUPS[group]) {
        const rows=GROUPS[group].map(f=>[button(LABELS[f],'edit:'+f)]);
        if (group==='schedule') {
          rows.unshift([button('Change weekday','days')]);
          rows.push([button(user.weekly?'Turn weekly reports off':'Turn weekly reports on',user.weekly?'weekly:off':'weekly:on')]);
        }
        rows.push([button('← My settings','settings')]);
        await reply(id,'Choose the setting to change:',{inline_keyboard:rows});
      } else await reply(id,'Open /settings to choose a setting.',settingsButtons);
      return new Response('ok');
    }
    if (user.accepted_at && action==='days') {
      await clearEdit(); await reply(id,'Choose your delivery day:',{inline_keyboard:[...DAYS.map((d,i)=>[button(d,'day:'+i)]),[button('← My settings','settings')]]}); return new Response('ok');
    }
    if (user.accepted_at && /^(day:|weekly:|toggle:)/.test(action)) {
      await clearEdit();
      if (action.startsWith('day:')) {
        const day=Number(action.slice(4)); if (!Number.isInteger(day)||day<0||day>6) throw new Error('Invalid day');
        await db('PATCH','bot_users?user_id=eq.'+id,{schedule_day:day});
        await reply(id,'✅ Delivery day saved: '+DAYS[day],settingsButtons);
      } else if (action.startsWith('weekly:')) {
        if (!['weekly:on','weekly:off'].includes(action)) throw new Error('Invalid choice');
        await db('PATCH','bot_users?user_id=eq.'+id,{weekly:action==='weekly:on'});
        await reply(id,'✅ Weekly reports '+(action==='weekly:on'?'on':'off')+'. Scheduled reports count toward your weekly allowance.',settingsButtons);
      } else {
        const item=action.slice(7); if (!['Erbpacht','Zwangsversteigerung'].includes(item)) throw new Error('Invalid exclusion');
        const list=user.settings.exclude.includes(item)?user.settings.exclude.filter((x:string)=>x!==item):[...user.settings.exclude,item];
        await db('PATCH','bot_users?user_id=eq.'+id,{settings:{...user.settings,exclude:list}});
        await reply(id,'✅ Exclusions updated. Open Exclusions again to see current choices.',settingsButtons);
      }
      return new Response('ok');
    }
    if (user.accepted_at && action.startsWith('edit:')) {
      const field=action.slice(5); if (!LABELS[field]) throw new Error('Invalid edit field');
      if (field==='language') {
        await clearEdit(); await reply(id,'Choose your report language:',{inline_keyboard:[[button('English','lang:en'),button('Deutsch','lang:de'),button('فارسی','lang:fa')],[button('Cancel','cancel')]]});
      } else {
        await db('PATCH','bot_users?user_id=eq.'+id,{settings:{...user.settings,_edit:{field,at:Date.now()}}});
        await reply(id,editPrompt(field),{inline_keyboard:[[button('Cancel','cancel')]]});
      }
      return new Response('ok');
    }
    if (user.accepted_at && action.startsWith('lang:')) {
      const language=parseEdit('language',action.slice(5)); await clearEdit();
      await db('PATCH','bot_users?user_id=eq.'+id,{settings:{...user.settings,language}});
      await reply(id,'✅ Report language saved: '+(language==='fa'?'فارسی':language==='en'?'English':'German'),settingsButtons); return new Response('ok');
    }
    if (user.accepted_at && !cb && !text.startsWith('/') && user.settings._edit) {
      const pending=user.settings._edit;
      if (Date.now()-pending.at>15*60*1000 || !LABELS[pending.field]) {
        await clearEdit(); await reply(id,'This edit expired. Open /settings and choose the field again.',settingsButtons);
      } else {
        try {
          const value=parseEdit(pending.field,text);
          const clean={...user.settings}; delete clean._edit;
          if (['schedule_time','timezone'].includes(pending.field)) await db('PATCH','bot_users?user_id=eq.'+id,{settings:clean,[pending.field]:value});
          else {
            const settings={...clean,[pending.field]:value};
            if (pending.field==='location') { settings.areas=[]; settings.country='Germany'; }
            await db('PATCH','bot_users?user_id=eq.'+id,{settings});
          }
          await reply(id,'✅ '+LABELS[pending.field]+' saved: '+(value===null?'No filter':Array.isArray(value)?value.join(', ')||'None':value),settingsButtons);
        } catch(e) {
          await reply(id,e instanceof Error?e.message:'Could not save. Try again.',{inline_keyboard:[[button('Cancel','cancel')]]});
        }
      }
      return new Response('ok');
    }
    // A command exits a pending edit; plain text only changes the explicitly selected field.
    if (user.settings._edit && (cb || text.startsWith('/'))) await clearEdit();
    // /run uses an atomic unique request key in SQL. Other commands are idempotent,
    // except /support which gets a dedicated unique update record.
    if (cmd==='/start' || cmd==='/disclaimer') {
      await reply(id,NOTICE,{inline_keyboard:[[{text:'I understand — continue',callback_data:'accept'}]]});
    } else if (cmd==='/accept') {
      await db('PATCH','bot_users?user_id=eq.'+id,{accepted_at:new Date().toISOString()});
      await reply(id,'Welcome. Use /help to see commands. Weekly delivery is initially off; /weekly on enables it.',buttons);
    } else if (cmd==='/help') {
      await reply(id,user.settings.language==='fa'?HELP_FA:HELP,buttons);
    } else if (cmd==='/support') {
      if (!rest) await reply(id,'Send /support followed by your question. It is forwarded to the administrator; no AI charge. Response is manual.');
      else {
        const existing = await db('GET','bot_updates?update_id=eq.'+Number(update.update_id));
        if (!existing.length) {
          await reply(admin,'📩 Support from Telegram ID '+id+'\n'+rest);
          await db('POST','bot_updates',{update_id:Number(update.update_id)});
        }
        await reply(id,'Your question was sent to the administrator. Response is manual, not immediate.');
      }
    } else if (id===admin && cmd==='/channel') {
      if (!['on','off'].includes(rest)) throw new Error('Use /channel on|off');
      await db('PATCH','bot_control?id=eq.1',{channel_enabled:rest==='on'});
      await reply(id,'Channel posting '+rest+'. Only your reports are shared; configure CHANNEL_ID in GitHub secrets and grant the bot posting permission.');
    } else if (id===admin && cmd==='/cost') {
      const month=new Date().toISOString().slice(0,7)+'-01T00:00:00Z';
      const jobs=await db('GET','bot_jobs?created_at=gte.'+month+'&select=charged_usd,reserved_usd,status');
      const total=jobs.reduce((s:number,j:any)=>s+Number(j.charged_usd??j.reserved_usd),0);
      const control=(await db('GET','bot_control?id=eq.1'))[0];
      await reply(id,`Monthly estimates/reservations: $${total.toFixed(2)} / $${control.monthly_budget_usd}\nUnknown usage: ${jobs.filter((j:any)=>j.status==='uncertain').length}. Reconcile with OpenAI billing; taxes/FX/hosting separate.`);
    } else if (id===admin && ['/approve','/plan','/reply'].includes(cmd)) {
      const target = Number(parts[0]);
      if (!Number.isSafeInteger(target) || target<=0) throw new Error('Invalid user ID');
      if (cmd==='/approve') {
        const known = await db('GET','bot_users?user_id=eq.'+target);
        await db(known.length?'PATCH':'POST',known.length?'bot_users?user_id=eq.'+target:'bot_users',{user_id:target,approved:true});
        await reply(id,'User approved. They must /start and accept the notice.');
      } else if (cmd==='/plan') {
        if (!['free','paid'].includes(parts[1])) throw new Error('Use /plan ID free|paid');
        const result = await db('PATCH','bot_users?user_id=eq.'+target,{plan:parts[1]});
        await reply(id,result.length?'Membership updated.':'User not found.');
      } else {
        const known = await db('GET','bot_users?user_id=eq.'+target+'&approved=eq.true');
        if (!known.length || !parts.slice(1).join(' ')) throw new Error('Use /reply APPROVED_USER_ID MESSAGE');
        await reply(target,'Support reply:\n'+parts.slice(1).join(' '));
        await reply(id,'Reply sent.');
      }
    } else if (!user.accepted_at) {
      await reply(id,'Please /start and accept the notice first.');
    } else if (cmd==='/settings') {
      await reply(id,settingsSummary(user),settingsButtons);
    } else if (cmd==='/set' || cmd==='/location' || cmd==='/areas' || cmd==='/exclude') {
      const settings = {...user.settings};
      if (cmd==='/location') {
        if (!rest || rest.length>100) throw new Error('Use /location CITY, Germany only');
        settings.location=rest; settings.country='Germany'; settings.areas=[];
      } else if (cmd==='/areas' || cmd==='/exclude') {
        if (!rest || rest.length>500) throw new Error('Provide a comma-separated list, or none');
        settings[cmd.slice(1)] = rest==='none'?[]:rest.split(',').map((x:string)=>x.trim()).filter(Boolean).slice(0,15);
      } else {
        const field = parts[0], value = parts[1];
        if (parts.length!==2) throw new Error('Use /set FIELD VALUE');
        if (field==='language') {
          if (!['en','de','fa'].includes(value)) throw new Error('Language must be en, de or fa');
          settings[field]=value;
        } else if (OPTIONAL.has(field) && value==='none') settings[field]=null;
        else {
          const bounds=MAX[field], n=Number(value);
          if (!bounds || !Number.isFinite(n) || n<bounds[0] || n>bounds[1] || (field==='fixed_rate_years' && !Number.isInteger(n))) throw new Error('Unknown field or invalid value; see /help');
          settings[field]=n;
        }
      }
      await db('PATCH','bot_users?user_id=eq.'+id,{settings});
      await reply(id,'Settings saved. Germany only during pilot.');
    } else if (cmd==='/schedule') {
      const day=['mon','tue','wed','thu','fri','sat','sun'].indexOf(parts[0]?.toLowerCase());
      if (parts.length!==3 || day<0 || !/^([01]\d|2[0-3]):[0-5]\d$/.test(parts[1])) throw new Error('Use /schedule mon 08:00 Europe/Berlin');
      try { new Intl.DateTimeFormat('en',{timeZone:parts[2]}).format(); } catch { throw new Error('Invalid timezone'); }
      await db('PATCH','bot_users?user_id=eq.'+id,{schedule_day:day,schedule_time:parts[1],timezone:parts[2]});
      await reply(id,'Schedule saved. Delivery is checked hourly and may be delayed. Use /weekly on to enable.');
    } else if (cmd==='/weekly') {
      if (!['on','off'].includes(rest)) throw new Error('Use /weekly on|off');
      await db('PATCH','bot_users?user_id=eq.'+id,{weekly:rest==='on'});
      await reply(id,'Weekly reports '+rest+(adminUnlimited?'. Your administrator account has no weekly report limit.':'. They count toward your quota.'));
    } else if (cmd==='/quota') {
      // SQL uses server-side Berlin week reset. Fetch latest jobs, calculate with Berlin date.
      const local = new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
      const d=new Date(local+'T12:00:00Z'); d.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));
      const week=d.toISOString().slice(0,10);
      const jobs=await db('GET','bot_jobs?user_id=eq.'+id+'&week_start=eq.'+week+'&select=status,charged_usd,usage');
      const used=jobs.filter((j:any)=>j.usage?.shared_hit!==true&&(j.status!=='failed'||Number(j.charged_usd)>0)).length;
      await reply(id,adminUnlimited?`Administrator: no weekly report limit.\nReports this week: ${used}.\nMonthly spending cap and one active analysis at a time still apply.`:`Plan: ${user.plan}\nUsed: ${used} / ${user.plan==='paid'?7:1} this week. Reset Monday 00:00 Europe/Berlin.`);
    } else if (cmd==='/last') {
      const jobs=await db('GET','bot_jobs?user_id=eq.'+id+'&status=eq.complete&order=finished_at.desc&limit=1&select=report');
      await reply(id,jobs.length?jobs[0].report:'No completed report yet.');
    } else if (cmd==='/run'||cmd==='/saved'||cmd==='/refresh') {
      const refresh=cmd==='/refresh';
      if (refresh && id!==admin) { await reply(id,'Only the administrator can start additional paid research.'); return new Response('ok'); }
      const control=(await db('GET','bot_control?id=eq.1'))[0];
      if (control?.shared_reports_enabled && !refresh) {
        const saved=await db('POST','rpc/bot_saved_report',{p_user:id});
        if (saved?.report) {
          await reply(id,'📂 Saved report for your current settings. No quota used and no new AI research.');
          await reply(id,saved.report); return new Response('ok');
        }
      }
      if (cmd==='/saved') {
        await reply(id,'No current shared report matches your exact settings. /last shows your previous report for free; /run can create a new personalised report within your allowance.');
        return new Response('ok');
      }
      if (!control?.research_v2) {
        await reply(id,'Analysis paused until the cost-saving upgrade is activated. No paid run started. Use /last for your saved report.');
        return new Response('ok');
      }
      const result=await db('POST','rpc/bot_enqueue',{p_user:id,p_key:(refresh?'refresh:':'telegram:')+update.update_id});
      if (result.error) await reply(id,'Analysis not started: '+result.error+'. Use /support if you need help.');
      else if (result.duplicate) await reply(id,'This request is already recorded. Use /last for the latest report.');
      else {
        try { await dispatch(result.job_id); await reply(id,refresh?'Additional paid research queued within the monthly cap. Saved apartments will be retained.':'Analysis queued. Results will arrive here; GitHub may take a few minutes.'); }
        catch { await reply(id,'Request saved but immediate dispatch failed. The scheduled worker can recover it.'); await reply(admin,'⚠️ Dispatch failed. Job '+result.job_id); }
      }
    } else await reply(id,'Use /help for commands.',buttons);
    return new Response('ok');
  } catch {
    // No request payloads, secrets or financial settings in function logs.
    if (replyTo) {
      try {
        await reply(replyTo,'Could not process the request. Check syntax with /help, or /support your question. If already queued, do not repeatedly press Run.');
        return new Response('ok');
      } catch { /* Telegram retries only if even the error reply cannot be delivered. */ }
    }
    return new Response('Request could not be processed. Please check command syntax or contact operator.',{status:500});
  }
});

// Short webhook only: long OpenAI work runs in GitHub Actions.
const env = (key: string) => { const v = Deno.env.get(key); if (!v) throw new Error('Missing configuration'); return v; };
const NOTICE = 'Estimates only; general information, not financial advice or a financing commitment. Verify independently before deciding. Listing data may be incomplete. Settings and reports are stored in Supabase; analysis uses OpenAI; Telegram delivers messages. API costs are reported to the administrator. Do not send bank credentials or identity documents. /support forwards your message and Telegram ID to the administrator. This is a private pilot, not a publicly launched service.';
const HELP = `Housing Loan Bot — Germany pilot
/start — read notice and accept
/settings — your investment settings
/set FIELD VALUE — change one setting
Example: /set max_price_eur 250000
/location Freiburg — choose a German city
/areas Freiburg, Emmendingen — preferred towns
/exclude Erbpacht, Zwangsversteigerung — exclusions; "none" clears
/schedule mon 08:00 Europe/Berlin — day, time, timezone
/weekly on or /weekly off — automatic report
/run — new analysis (or use the button)
/quota — weekly allowance
/last — latest saved report
/support YOUR QUESTION — contact the administrator
/disclaimer — notice and data use
Free: 1 report/week. Paid: up to 7. Scheduled reports count too. Reset Monday 00:00 Europe/Berlin. Manual membership during pilot. Delivery may be delayed; changing schedule does not add reports. If a report fails, use /support; repeated clicks cannot start parallel analyses.
Editable numeric fields: max_loan_eur, equity_eur, max_price_eur, min_size_m2, radius_km, max_price_per_m2, target_gross_yield_pct, min_monthly_cashflow_eur, fixed_rate_years, repayment_pct. Optional targets accept "none". /set language en or de. Other countries will require country-specific rules in a future release.`;
const MAX: Record<string, [number, number]> = {
  max_loan_eur:[0,10000000],equity_eur:[0,10000000],max_price_eur:[1,10000000],
  min_size_m2:[1,2000],radius_km:[1,500],max_price_per_m2:[1,100000],
  target_gross_yield_pct:[0,100],min_monthly_cashflow_eur:[-100000,100000],
  fixed_rate_years:[1,40],repayment_pct:[0,30]
};
const OPTIONAL = new Set(['max_price_per_m2','target_gross_yield_pct','min_monthly_cashflow_eur']);

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
  for (let i=0; i<text.length; i+=3800) {
    await tg('sendMessage',{chat_id:id,text:text.slice(i,i+3800),link_preview_options:{is_disabled:true},
      ...(keyboard && i===0 ? {reply_markup:keyboard} : {})});
  }
}
const buttons = {inline_keyboard:[[{text:'🔎 Run analysis',callback_data:'run'},{text:'Help',callback_data:'help'}]]};
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
    let rows = await db('GET','bot_users?user_id=eq.'+id);
    if (!rows.length && id===admin) rows = await db('POST','bot_users',{user_id:id,approved:true});
    if (!rows.length || !rows[0].approved) {
      await reply(id,'Invite-only pilot. Your Telegram ID is '+id+'. Ask the operator for access.');
      return new Response('ok');
    }
    const user = rows[0];
    const text = String(cb ? '/'+cb.data : message.text || '').slice(0,2500).trim();
    const [rawcmd, ...parts] = text.split(/\s+/);
    const cmd = rawcmd.split('@')[0].toLowerCase();
    const rest = parts.join(' ');
    // /run uses an atomic unique request key in SQL. Other commands are idempotent,
    // except /support which gets a dedicated unique update record.
    if (cmd==='/start' || cmd==='/disclaimer') {
      await reply(id,NOTICE,{inline_keyboard:[[{text:'I understand — continue',callback_data:'accept'}]]});
    } else if (cmd==='/accept') {
      await db('PATCH','bot_users?user_id=eq.'+id,{accepted_at:new Date().toISOString()});
      await reply(id,'Welcome. Use /help to see commands. Weekly delivery is initially off; /weekly on enables it.',buttons);
    } else if (cmd==='/help') {
      await reply(id,HELP,buttons);
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
      await reply(id,JSON.stringify(user.settings,null,2)+'\nWeekly: '+user.weekly+'\nSchedule: '+['mon','tue','wed','thu','fri','sat','sun'][user.schedule_day]+' '+user.schedule_time+' '+user.timezone,buttons);
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
          if (!['en','de'].includes(value)) throw new Error('Language must be en or de');
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
      await reply(id,'Weekly reports '+rest+'. They count toward your quota.');
    } else if (cmd==='/quota') {
      // SQL uses server-side Berlin week reset. Fetch latest jobs, calculate with Berlin date.
      const local = new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
      const d=new Date(local+'T12:00:00Z'); d.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));
      const week=d.toISOString().slice(0,10);
      const jobs=await db('GET','bot_jobs?user_id=eq.'+id+'&week_start=eq.'+week+'&select=status,charged_usd');
      const used=jobs.filter((j:any)=>j.status!=='failed'||Number(j.charged_usd)>0).length;
      await reply(id,`Plan: ${user.plan}\nUsed: ${used} / ${user.plan==='paid'?7:1} this week. Reset Monday 00:00 Europe/Berlin.`);
    } else if (cmd==='/last') {
      const jobs=await db('GET','bot_jobs?user_id=eq.'+id+'&status=eq.complete&order=finished_at.desc&limit=1&select=report');
      await reply(id,jobs.length?jobs[0].report:'No completed report yet.');
    } else if (cmd==='/run') {
      const result=await db('POST','rpc/bot_enqueue',{p_user:id,p_key:'telegram:'+update.update_id});
      if (result.error) await reply(id,'Analysis not started: '+result.error+'. Use /support if you need help.');
      else if (result.duplicate) await reply(id,'This request is already recorded. Use /last for the latest report.');
      else {
        try { await dispatch(result.job_id); await reply(id,'Analysis queued. Results will arrive here; GitHub may take a few minutes.'); }
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

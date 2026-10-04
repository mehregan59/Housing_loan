"""Actions worker. No paid or scheduled work unless explicitly enabled in DB."""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, quote
from zoneinfo import ZoneInfo

import httpx

MODEL = os.getenv('OPENAI_MODEL', 'gpt-6-astra')
MAX_TOOLS = 12
MAX_OUTPUT = 4500
DISCLAIMER = 'Estimates only; general information, not financial advice or a financing commitment. Verify independently before deciding.'


def canonical(url):
    p = urlsplit(url.strip())
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Invalid source URL')
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/'), p.query, ''))


def parse_report(text, sources):
    if text.count('---URLS---') != 1:
        raise ValueError('Missing or repeated URL appendix')
    report, appendix = text.split('---URLS---')
    allowed = {canonical(u) for u in sources if u.startswith(('http://', 'https://'))}
    urls = []
    for line in appendix.splitlines():
        if not line.strip():
            continue
        url = canonical(line)
        if url not in allowed:
            raise ValueError('Listing URL absent from retrieved sources')
        if url not in urls:
            urls.append(url)
    if not report.strip() or len(urls) > 5 or len(report) > 6000:
        raise ValueError('Invalid report length or listing count')
    for url in re.findall(r'https?://[^\s<>]+', report):
        if canonical(url.rstrip('.,)')) not in allowed:
            raise ValueError('Report contains an unsupported source URL')
    if DISCLAIMER not in report:
        report = report.rstrip() + '\n\n' + DISCLAIMER
    return report.strip(), urls


def chunks(text, limit=3900):
    """Split conservatively by UTF-16 units, preserving all text and emojis."""
    if limit < 2:
        raise ValueError('Message limit must be at least two')
    while text:
        units = 0
        cut = 0
        for char in text:
            width = 2 if ord(char) > 0xFFFF else 1
            if units + width > limit:
                break
            units += width
            cut += 1
        if cut < len(text):
            boundary = text.rfind('\n', 0, cut)
            if boundary >= cut // 2:
                cut = boundary + 1
        yield text[:cut]
        text = text[cut:]


def due_slot(user, now):
    """Latest scheduled slot, catch up within 24 hours; DST via zoneinfo."""
    local = now.astimezone(ZoneInfo(user['timezone']))
    hour, minute = map(int, user['schedule_time'].split(':'))
    days = (local.weekday() - user['schedule_day']) % 7
    slot = (local - timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if slot > local:
        slot -= timedelta(days=7)
    delta = now - slot.astimezone(timezone.utc)
    return slot.strftime('%Y-%m-%d') if timedelta(0) <= delta < timedelta(hours=24) else None


def estimate_cost(response, model=None):
    """Standard USD prices checked 2026-10-04. Unknown models fail closed."""
    rates = {'gpt-6-astra': (10, 1, 50), 'gpt-6.1-sol': (2, .1, 10)}
    model = model or MODEL
    if model not in rates or not response.get('usage'):
        raise ValueError('Missing usage or unconfigured model pricing')
    usage = response['usage']
    inp, cached, out = rates[model]
    input_tokens = usage['input_tokens']
    output_tokens = usage['output_tokens']
    cached_tokens = (usage.get('input_tokens_details') or {}).get('cached_tokens', 0)
    # Conservative long-context input rates above 272k; buffers below cover estimation uncertainty.
    if input_tokens > 272000:
        inp *= 2
        cached *= 2
        out *= 1.5
    searches = sum(x.get('type') == 'web_search_call' for x in response.get('output', []))
    calls = [x for x in response.get('output', []) if x.get('type') == 'code_interpreter_call']
    containers = {x.get('container_id') or x['id'] for x in calls}
    cost = ((input_tokens-cached_tokens)*inp + cached_tokens*cached + output_tokens*out)/1_000_000
    cost += searches*.01 + len(containers)*.03
    return round(cost*1.1, 6), {**usage, 'model': model, 'search_calls': searches,
                                'containers': len(containers), 'estimate_buffer_pct': 10}


class DatabaseFailure(RuntimeError):
    """Safe diagnostic metadata only; never log request values or response bodies."""
    def __init__(self,method,path,status,code):
        table=path.split('?')[0]
        if not re.fullmatch(r'(?:rpc/)?[a-z_]+',table): table='database'
        if not isinstance(code,str) or not re.fullmatch(r'[A-Z0-9]{5,12}',code): code='unknown'
        self.safe_detail=f'{method} {table}; HTTP {status}; code {code}'
        super().__init__(self.safe_detail)


def timestamp_filter(value):
    return quote(value.isoformat(),safe='')


class Backend:
    def __init__(self):
        self.http = httpx.Client(timeout=30)
        self.base = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/'
        self.headers = {'apikey': os.environ['SUPABASE_SECRET_KEY'], 'Content-Type': 'application/json'}

    def request(self, method, path, data=None):
        r = self.http.request(method, self.base+path, headers=self.headers, json=data)
        if not r.is_success:
            try: code=r.json().get('code')
            except (ValueError,AttributeError): code=None
            raise DatabaseFailure(method,path,r.status_code,code)
        return r.json() if r.content else None

    def rpc(self, name, data):
        return self.request('POST', 'rpc/'+name, data)

    def telegram(self, user, text, keyboard=None, entities=None):
        offset=0
        for index,part in enumerate(chunks(text)):
            units=len(part.encode('utf-16-le'))//2
            local_entities=[]
            for entity in entities or []:
                start=max(offset,entity['offset']);end=min(offset+units,entity['offset']+entity['length'])
                if start<end: local_entities.append({**entity,'offset':start-offset,'length':end-start})
            if index: time.sleep(1.1)
            r = self.http.post('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/sendMessage',
                json={'chat_id': user, 'text': part, 'link_preview_options': {'is_disabled': True},**({'reply_markup':keyboard} if keyboard and index==0 else {}),**({'entities':local_entities} if local_entities else {})})
            if not r.is_success or not r.json().get('ok'):
                raise RuntimeError('Telegram delivery failed')
            offset+=units

    def report(self, user, text, job_id, language='en'):
        from report_pages import split_report,page,PAGE_SIZE
        view=split_report(text)
        if not view['cards']: return self.telegram(user,text)
        for index in range((len(view['cards'])+PAGE_SIZE-1)//PAGE_SIZE):
            if index: time.sleep(1.1)
            summary,entities=page(view,'j'+job_id,index,language,os.getenv('TELEGRAM_BOT_USERNAME','MeHousingLoanBot'))
            self.telegram(user,summary,entities=entities)

    def admin(self, text):
        self.telegram(os.environ['ADMIN_USER_ID'], text)


def sources_from(response):
    urls = set()
    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get('url'), str):
                urls.add(value['url'])
            for x in value.values():
                walk(x)
        elif isinstance(value, list):
            for x in value:
                walk(x)
    for item in response.get('output', []):
        if item.get('type') in ('web_search_call', 'message'):
            walk(item)
    return urls


def run_job(db, job_id):
    job = db.rpc('bot_claim', {'p_id': job_id})
    if not job:
        return
    cost = None
    usage = {}
    report = None
    urls = []
    status = 'failed'
    error = None
    meter = {'pending':False, 'cost':0, 'calls':[]}
    try:
        if job.get('research_v2'):
            if job['settings'].get('_guide_version') != 1:
                raise GuideRequired()
            from research import analyse
            request_rows=db.request('GET','bot_jobs?id=eq.'+job_id+'&select=request_key')
            job['force_refresh']=str(job['user_id'])==os.environ['ADMIN_USER_ID'] and bool(request_rows) and request_rows[0].get('request_key','').startswith('refresh:')
            report, urls, cache_hit = analyse(db, job, meter)
            cost = round(meter['cost'],6)
            usage = {'pipeline':2, 'cache_hit':cache_hit, 'research_calls':meter['calls'], 'report_signature':meter.get('report_signature'), 'shared_hit':meter.get('shared_hit',False), 'shared_publish_failed':meter.get('shared_publish_failed',False)}
            usage.update(partial=meter.get('partial',False),warnings=meter.get('warnings',[]),checkpoints=meter.get('checkpoints',[]),stage=meter.get('stage'))
            status = 'complete'
        else:
            raise ResearchUpgradeInactive()
    except Exception as exc:
        error = type(exc).__name__
        if job.get('research_v2'):
            from research import ResearchDataError
            if isinstance(exc,ResearchDataError): error=exc.code
            usage = {'pipeline':2, 'research_calls':meter['calls'],'stage':meter.get('stage'),'warnings':meter.get('warnings',[]),'checkpoints':meter.get('checkpoints',[])}
            if meter['pending']:
                status = 'uncertain'
            else:
                cost = round(meter['cost'],6)
        else:
            cost = 0
    finish_job(db,job,job_id,status,cost,usage,report,urls,error)


class GuideRequired(Exception):
    """Setup must be completed before any analysis, including scheduled work."""


class ResearchUpgradeInactive(Exception):
    """Never silently fall back to the expensive legacy research path."""


def finish_job(db,job,job_id,status,cost,usage,report,urls,error):
    db.rpc('bot_finish', {'p_id': job_id, 'p_status':status, 'p_cost':cost,
        'p_report':report if status=='complete' else None, 'p_usage':usage,
        'p_error':error, 'p_urls':urls if status=='complete' else []})
    if status == 'complete':
        try:
            db.report(job['user_id'], report,job_id,job['settings'].get('language','en'))
            db.request('PATCH', 'bot_jobs?id=eq.'+job_id, {'delivered':True})
            control = db.request('GET','bot_control?id=eq.1')[0]
            if control['channel_enabled'] and str(job['user_id']) == os.environ['ADMIN_USER_ID'] and os.getenv('CHANNEL_ID'):
                db.telegram(os.environ['CHANNEL_ID'], report)
        except Exception:
            db.admin('⚠️ Report saved, but delivery failed. Job '+job_id+'; use /last to retrieve it. No analysis retry.')
    else:
        try:
            if error=='GuideRequired':
                db.telegram(job['user_id'], '📖 Please complete /guide before starting an analysis. No API call was made.', {'inline_keyboard':[[{'text':'Open setup guide','callback_data':'guide:0'}]]})
            else:
                db.telegram(job['user_id'], 'Analysis paused until the cost-saving upgrade is activated. No API call was made. Use /last for your saved report.' if error=='ResearchUpgradeInactive' else '⚠️ Analysis failed. The administrator has been notified; no automatic paid retry.')
        except Exception:
            pass
    ledger = db.request('GET', 'bot_jobs?created_at=gte.'+datetime.now(timezone.utc).strftime('%Y-%m-01T00:00:00Z')+'&select=charged_usd,reserved_usd')
    total = sum(float(x['charged_usd'] if x['charged_usd'] is not None else x['reserved_usd']) for x in ledger)
    models=', '.join(sorted({x.get('model','unknown') for x in usage.get('research_calls',[])})) or usage.get('model','none (no API call)')
    shown_status='partial — see report limitations' if usage.get('partial') else status
    db.admin(f"💳 Administrator only — API spending\nAnalysis status: {shown_status}\nModel: {models}\n"+
        (f"Failure code: {error}\n" if error else '')+"Estimated cost of this report: "+
        (f"${cost:.4f}" if cost is not None else 'unknown; reservation retained and analyses paused for review')+
        f"\nThis month, including pending reports: ${total:.2f} / $8 budget\n"+
        f"Ordinary users do not receive this message.\nEstimate only; check OpenAI billing. Hosting, tax and currency conversion are separate.\nReference: {job_id}")


def sweep(db):
    control = db.request('GET', 'bot_control?id=eq.1')[0]
    if not control['enabled']:
        return
    now = datetime.now(timezone.utc)
    stale = db.request('GET', 'bot_jobs?status=eq.running&started_at=lt.'+timestamp_filter(now-timedelta(minutes=30)))
    for job in stale:
        db.rpc('bot_finish', {'p_id':job['id'],'p_status':'uncertain','p_cost':None,'p_report':None,
                             'p_usage':{},'p_error':'InterruptedWorker','p_urls':[]})
        db.admin('⚠️ Interrupted analysis; spending paused pending usage reconciliation. Job '+job['id'])
    for user in db.request('GET', 'bot_users?approved=eq.true&weekly=eq.true'):
        if user.get('settings',{}).get('_guide_version') != 1:
            continue
        slot = due_slot(user, now)
        if slot:
            db.rpc('bot_enqueue', {'p_user':user['user_id'], 'p_key':f"schedule:{user['user_id']}:{slot}"})
    for job in db.request('GET', 'bot_jobs?status=eq.queued&order=created_at&limit=3'):
        run_job(db, job['id'])


def notify_guide_users(db):
    """Explicit, private broadcast. No OpenAI calls or report allowance used."""
    delivered=skipped=failed=0
    offset=0
    while True:
        users=db.request('GET',f'bot_users?select=user_id,settings,approved,accepted_at&order=user_id&limit=100&offset={offset}')
        if not users: break
        for user in users:
            marker=-(int(user['user_id'])*100+1)
            if user.get('settings',{}).get('_guide_version')==1 or db.request('GET',f'bot_updates?update_id=eq.{marker}'):
                skipped+=1
                continue
            language=user.get('settings',{}).get('language','en')
            text={
                'en':'📖 Please complete the updated setup guide before your next analysis. It explains settings, calculations, missing data and costs. Weekly reports wait until you finish. Reading the guide is free and does not start a search. Tap below or send /guide.',
                'de':'📖 Bitte die neue Einrichtungsanleitung vor der nächsten Analyse abschließen. Sie erklärt Einstellungen, Berechnungen, fehlende Daten und Kosten. Wochenberichte warten bis zum Abschluss. Die Anleitung ist kostenlos und startet keine Suche. Unten tippen oder /guide senden.',
                'fa':'📖 لطفاً پیش از تحلیل بعدی راهنمای تنظیمات را تکمیل کنید. راهنما تنظیمات، محاسبات، داده‌های ناقص و هزینه‌ها را توضیح می‌دهد. گزارش هفتگی تا پایان راهنما منتظر می‌ماند. خواندن راهنما رایگان است و جستجو را آغاز نمی‌کند. دکمه زیر را بزنید یا /guide بفرستید.'
            }.get(language)
            if text is None: text='📖 Please complete /guide before your next analysis. Reading the guide is free and does not start a search.'
            action='guide:0' if user.get('approved') and user.get('accepted_at') else 'start'
            try:
                db.telegram(user['user_id'],text,{'inline_keyboard':[[{'text':{'en':'Open guide','de':'Anleitung öffnen','fa':'باز کردن راهنما'}.get(language,'Open guide'),'callback_data':action}]]})
                db.request('POST','bot_updates',{'update_id':marker})
                delivered+=1
            except Exception:
                failed+=1
            time.sleep(1.1)
        offset+=len(users)
    db.admin(f'📖 Setup guide notice: {delivered} delivered, {skipped} already completed/notified, {failed} failed. No AI calls were made.')
    return {'delivered':delivered,'skipped':skipped,'failed':failed}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['sweep','job','health','guide-all'])
    p.add_argument('--job-id')
    args = p.parse_args()
    db = Backend()
    try:
        if args.mode == 'guide-all':
            notify_guide_users(db)
        elif args.mode == 'health':
            # PATCH then insert avoids repeated PK conflicts and keeps only one health row.
            rows = db.request('GET', 'bot_health?id=eq.1')
            db.request('PATCH' if rows else 'POST', 'bot_health?id=eq.1' if rows else 'bot_health',
                       {'checked_at':datetime.now(timezone.utc).isoformat()} if rows else {'id':1})
            stale = db.request('GET','bot_jobs?status=eq.queued&created_at=lt.'+timestamp_filter(datetime.now(timezone.utc)-timedelta(hours=24))+'&select=id')
            if stale:
                db.admin('⚠️ '+str(len(stale))+' analysis jobs overdue. Check GitHub Actions; no paid retry started.')
            db.request('DELETE','bot_updates?created_at=lt.'+timestamp_filter(datetime.now(timezone.utc)-timedelta(days=30)))
            control = db.request('GET','bot_control?id=eq.1')[0]
            if control.get('research_v2'):
                db.request('DELETE','bot_market_cache?expires_at=lt.'+timestamp_filter(datetime.now(timezone.utc)-timedelta(days=30)))
            if control.get('shared_reports_enabled'):
                db.request('DELETE','bot_shared_reports?expires_at=lt.'+timestamp_filter(datetime.now(timezone.utc)))
        elif args.mode == 'job':
            import uuid
            run_job(db, str(uuid.UUID(args.job_id)))
        else:
            sweep(db)
    except Exception as exc:
        detail=' — '+exc.safe_detail if isinstance(exc,DatabaseFailure) else ''
        try:
            db.admin('⚠️ Bot worker/health check failed: '+type(exc).__name__+detail+'. Check Actions. No automatic paid retry.')
        except Exception:
            pass
        print('Worker failed: '+type(exc).__name__+detail, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

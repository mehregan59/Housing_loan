"""Actions worker. No paid or scheduled work unless explicitly enabled in DB."""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
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
    while text:
        cut = min(len(text), limit)
        if cut < len(text):
            cut = text.rfind('\n', 0, cut) or cut
            if cut <= 0:
                cut = limit
        yield text[:cut]
        text = text[cut:].lstrip('\n')


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


def estimate_cost(response):
    """Standard USD prices checked 2026-10-04. Unknown models fail closed."""
    rates = {'gpt-6-astra': (10, 1, 50), 'gpt-6.1-sol': (2, .1, 10)}
    if MODEL not in rates or not response.get('usage'):
        raise ValueError('Missing usage or unconfigured model pricing')
    usage = response['usage']
    inp, cached, out = rates[MODEL]
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
    return round(cost*1.1, 6), {**usage, 'model': MODEL, 'search_calls': searches,
                                'containers': len(containers), 'estimate_buffer_pct': 10}


class Backend:
    def __init__(self):
        self.http = httpx.Client(timeout=30)
        self.base = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/'
        self.headers = {'apikey': os.environ['SUPABASE_SECRET_KEY'], 'Content-Type': 'application/json'}

    def request(self, method, path, data=None):
        r = self.http.request(method, self.base+path, headers=self.headers, json=data)
        if not r.is_success:
            raise RuntimeError(f'Database request failed ({r.status_code})')
        return r.json() if r.content else None

    def rpc(self, name, data):
        return self.request('POST', 'rpc/'+name, data)

    def telegram(self, user, text):
        for part in chunks(text):
            r = self.http.post('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/sendMessage',
                json={'chat_id': user, 'text': part, 'link_preview_options': {'is_disabled': True}})
            if not r.is_success or not r.json().get('ok'):
                raise RuntimeError('Telegram delivery failed')

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
    from openai import OpenAI
    job = db.rpc('bot_claim', {'p_id': job_id})
    if not job:
        return
    sent = False
    cost = None
    usage = {}
    report = None
    urls = []
    status = 'failed'
    error = None
    try:
        if MODEL not in ('gpt-6-astra', 'gpt-6.1-sol'):
            raise ValueError('Unpriced model')
        settings = job['settings']
        settings['already_seen_urls'] = [x['url'] for x in db.request('GET',
            f"bot_seen?user_id=eq.{job['user_id']}&order=evaluated_at.desc&limit=200")]
        if len(json.dumps(settings)) > 40000:
            raise ValueError('Settings too large')
        prompt = Path('prompt.txt').read_text().replace('{date}', datetime.now(timezone.utc).date().isoformat()).replace('{settings}', json.dumps(settings))
        client = OpenAI(timeout=600, max_retries=0)
        # No automatic retries: timeout/network failures may already have incurred charges.
        sent = True
        response = client.responses.create(model=MODEL, instructions=prompt,
            input='Find and evaluate current apartments matching these settings.',
            tools=[{'type':'web_search'}, {'type':'code_interpreter', 'container':{'type':'auto','memory_limit':'1g'}}],
            max_tool_calls=MAX_TOOLS, max_output_tokens=MAX_OUTPUT,
            include=['web_search_call.action.sources'], store=False)
        data = response.model_dump()
        cost, usage = estimate_cost(data)
        if data.get('status') != 'completed':
            raise ValueError('Incomplete model response')
        report, urls = parse_report(response.output_text, sources_from(data))
        if urls and not any(x.get('type') == 'code_interpreter_call' and x.get('status') == 'completed' for x in data.get('output', [])):
            raise ValueError('Missing successful calculation tool')
        status = 'complete'
    except Exception as exc:
        # Do not log exception messages: SDK/HTTP exceptions can include credentials or user data.
        error = type(exc).__name__
        if sent and cost is None:
            status = 'uncertain'
        elif not sent:
            cost = 0
    db.rpc('bot_finish', {'p_id': job_id, 'p_status':status, 'p_cost':cost,
        'p_report':report if status=='complete' else None, 'p_usage':usage,
        'p_error':error, 'p_urls':urls if status=='complete' else []})
    if status == 'complete':
        try:
            db.telegram(job['user_id'], report)
            db.request('PATCH', 'bot_jobs?id=eq.'+job_id, {'delivered':True})
            control = db.request('GET','bot_control?id=eq.1')[0]
            if control['channel_enabled'] and str(job['user_id']) == os.environ['ADMIN_USER_ID'] and os.getenv('CHANNEL_ID'):
                db.telegram(os.environ['CHANNEL_ID'], report)
        except Exception:
            db.admin('⚠️ Report saved, but delivery failed. Job '+job_id+'; use /last to retrieve it. No analysis retry.')
    else:
        try:
            db.telegram(job['user_id'], '⚠️ Analysis failed. The administrator has been notified; no automatic paid retry.')
        except Exception:
            pass
    ledger = db.request('GET', 'bot_jobs?created_at=gte.'+datetime.now(timezone.utc).strftime('%Y-%m-01T00:00:00Z')+'&select=charged_usd,reserved_usd')
    total = sum(float(x['charged_usd'] if x['charged_usd'] is not None else x['reserved_usd']) for x in ledger)
    db.admin(f"💳 Job {job_id}\nStatus: {status}\nEstimated API cost: "+
        (f"${cost:.4f}" if cost is not None else 'unknown; reservation retained and analyses paused for review')+
        f"\nMonthly estimate/reservations: ${total:.2f} / $8 configured cap\n"+
        f"Searches: {usage.get('search_calls','unknown')} | Input/output tokens: {usage.get('input_tokens','unknown')}/{usage.get('output_tokens','unknown')}\nHosting/tax/FX are separate; reconcile with OpenAI billing.")


def sweep(db):
    control = db.request('GET', 'bot_control?id=eq.1')[0]
    if not control['enabled']:
        return
    now = datetime.now(timezone.utc)
    stale = db.request('GET', 'bot_jobs?status=eq.running&started_at=lt.'+(now-timedelta(minutes=30)).isoformat())
    for job in stale:
        db.rpc('bot_finish', {'p_id':job['id'],'p_status':'uncertain','p_cost':None,'p_report':None,
                             'p_usage':{},'p_error':'InterruptedWorker','p_urls':[]})
        db.admin('⚠️ Interrupted analysis; spending paused pending usage reconciliation. Job '+job['id'])
    for user in db.request('GET', 'bot_users?approved=eq.true&weekly=eq.true'):
        slot = due_slot(user, now)
        if slot:
            db.rpc('bot_enqueue', {'p_user':user['user_id'], 'p_key':f"schedule:{user['user_id']}:{slot}"})
    for job in db.request('GET', 'bot_jobs?status=eq.queued&order=created_at&limit=3'):
        run_job(db, job['id'])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['sweep','job','health'])
    p.add_argument('--job-id')
    args = p.parse_args()
    db = Backend()
    try:
        if args.mode == 'health':
            # PATCH then insert avoids repeated PK conflicts and keeps only one health row.
            rows = db.request('GET', 'bot_health?id=eq.1')
            db.request('PATCH' if rows else 'POST', 'bot_health?id=eq.1' if rows else 'bot_health',
                       {'checked_at':datetime.now(timezone.utc).isoformat()} if rows else {'id':1})
            stale = db.request('GET','bot_jobs?status=eq.queued&created_at=lt.'+(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()+'&select=id')
            if stale:
                db.admin('⚠️ '+str(len(stale))+' analysis jobs overdue. Check GitHub Actions; no paid retry started.')
            db.request('DELETE','bot_updates?created_at=lt.'+(datetime.now(timezone.utc)-timedelta(days=30)).isoformat())
        elif args.mode == 'job':
            import uuid
            run_job(db, str(uuid.UUID(args.job_id)))
        else:
            sweep(db)
    except Exception as exc:
        try:
            db.admin('⚠️ Bot worker/health check failed: '+type(exc).__name__+'. Check Actions. No automatic paid retry.')
        except Exception:
            pass
        print('Worker failed: '+type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

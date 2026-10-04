"""Two bounded research calls on cache misses; none on a complete cache hit."""
import json
import hashlib
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
import market

MODEL = os.getenv('RESEARCH_MODEL','gpt-6.1-sol')


def retrieved_sources(data):
    urls=set()
    def walk(v):
        if isinstance(v,dict):
            if isinstance(v.get('url'),str): urls.add(v['url'])
            for x in v.values(): walk(x)
        elif isinstance(v,list):
            for x in v: walk(x)
    # The model's final message is not independent proof of retrieval.
    for item in data.get('output',[]):
        if item.get('type')=='web_search_call': walk(item)
    return urls


def analyse(db,job,meter):
    from openai import OpenAI
    from agent import estimate_cost
    s={k:v for k,v in job['settings'].items() if not k.startswith('_')}
    if s.get('country','Germany')!='Germany': raise ValueError('Unsupported country')
    if MODEL not in ('gpt-6.1-sol','gpt-6-astra'): raise ValueError('Unpriced research model')
    now=datetime.now(timezone.utc)
    if job.get('shared_reports_enabled'):
        saved=db.rpc('bot_shared_get',{'p_settings':s})
        if saved:
            meter['shared_hit']=True
            return saved['report'],saved['urls'],True
    # A single control lock reserves a fresh research budget; Actions serializes workers.
    reserved=False
    def extract(kind,prompt,schema,max_tools,max_output):
        nonlocal reserved
        if not reserved:
            if not db.rpc('bot_research_reserve',{'p_id':job['id']}): return None
            reserved=True
        meter['pending']=True
        response=OpenAI(timeout=480,max_retries=0).responses.create(
            model=MODEL,instructions=Path('research_prompt.txt').read_text(),input=prompt,
            tools=[{'type':'web_search','search_context_size':'low'}],
            text={'format':{'type':'json_schema','name':kind,'strict':True,'schema':schema}},
            max_tool_calls=max_tools,max_output_tokens=max_output,
            include=['web_search_call.action.sources'],store=False)
        data=response.model_dump()
        cost,usage=estimate_cost(data,MODEL)
        meter['cost']+=cost;meter['calls'].append(usage);meter['pending']=False
        if data.get('status')!='completed': raise ValueError('Incomplete extraction')
        extracted=json.loads(response.output_text)
        sources=retrieved_sources(data)
        if not sources: raise ValueError('No retrieved source evidence')
        opened={item['action']['url'] for item in data.get('output',[]) if item.get('type')=='web_search_call' and item.get('action',{}).get('type')=='open_page' and item['action'].get('url')}
        return (market.validate_rates(extracted,sources,now) if kind=='rates' else market.validate_pool(extracted,sources,opened))
    def save(key,kind,payload,radius=None):
        # Service-only cache contains public property data, never investor settings/IDs.
        db.request('DELETE','bot_market_cache?cache_key=eq.'+quote(key,safe=''))
        row={'cache_key':key,'kind':kind,'version':market.VERSION,'payload':payload,
             'created_at':now.isoformat(),'expires_at':(now+timedelta(days=market.TTL_DAYS)).isoformat(),
             'radius_km':radius}
        db.request('POST','bot_market_cache',row)
        return row
    rate_key=market.cache_key('rates',s)
    rate_rows=db.request('GET','bot_market_cache?cache_key=eq.'+quote(rate_key,safe=''))
    rates=None
    if rate_rows and market.fresh(rate_rows[0],now):
        rates=rate_rows[0]['payload']
        if any((now.date()-datetime.fromisoformat(x['date']).date()).days>14 for x in rates['rates']): rates=None
    if rates is None:
        rates=extract('rates',f'Today {now.date()}. Find nominal German mortgage rates for {s["fixed_rate_years"]}-year fixation from at least two independent providers, e.g. Interhyp, Dr. Klein, FMH. Source dates required. Effective APR must not be labelled nominal. Return no rates if unavailable.',market.RATE_SCHEMA,4,1500)
        if rates is not None: save(rate_key,'rates',rates)
    rates=rates or {'rates':[]}
    pool_rows=db.request('GET','bot_market_cache?kind=eq.pool&version=eq.2&expires_at=gt.'+quote(now.isoformat(),safe='')+'&order=created_at.desc&limit=500')
    row,center=market.choose_pool(pool_rows,s,now)
    hit=row is not None
    if row is None:
        key=market.cache_key('pool',s); radius=math.ceil(float(s['radius_km'])/25)*25+5
        previous=db.request('GET','bot_market_cache?cache_key=eq.'+quote(key,safe=''))
        old_urls=[x['url'] for x in previous[0]['payload']['listings'][:20]] if previous else []
        prompt=json.dumps({'today':str(now.date()),'location':s['location'],'country':'Germany','search_radius_km':radius,
            'target_distinct_listings':market.TARGET_LISTINGS,'refresh_these_urls_first':old_urls})
        prompt+='\nCollect a broad shared pool of apartments for sale, independent of investor price/loan/rent limits. Search ImmoScout24, Immowelt, Kleinanzeigen and local agents. Aim for 20, maximum 30 distinct individual apartments; never pad. Find sourced municipality coordinates for the center and listing towns. Open individual pages; reject snippet-only or removed listings. State transfer tax must have an official state source. Estimate missing rent or owner costs only with relevant cited comparable evidence; otherwise null. Owner costs exclude building reserve contributions to avoid double counting. Do not use total Hausgeld as owner-only fees. Give concise factual risks in English and German. Include municipality points to permit nearby users to reuse the pool. No analysis, scores or financial calculations.'
        pool=extract('pool',prompt,market.POOL_SCHEMA,24,14000)
        if pool is None:
            message='Suchbudget nicht verfügbar. Kein aktueller gemeinsamer Bestand deckt Ihren Standort ab. Ihre Grenzen wurden nicht geändert. Mit /last können Sie einen gespeicherten Bericht abrufen.' if s.get('language')=='de' else 'Search budget unavailable. No fresh shared listing pool covers your location. Your limits have not been changed. Try /last for a saved report.'
            return (message+'\n\n'+market.DISCLAIMER,[],False)
        if market.norm(pool['center']['name'])!=market.norm(s['location']): raise ValueError('Ambiguous location')
        row=save(key,'pool',pool,radius);center=market.point(pool['center'])
    # Re-sort previously seen homes after new homes; keep them rather than inventing replacements.
    signature=hashlib.sha256(json.dumps({'settings':s,'pool':row['payload'],'checked':row['created_at'],'rates':rates},sort_keys=True).encode()).hexdigest()
    meter['report_signature']=signature
    previous_reports=db.request('GET',f'bot_jobs?user_id=eq.{job["user_id"]}&status=eq.complete&order=finished_at.desc&limit=1&select=report,usage')
    if previous_reports and (previous_reports[0].get('usage') or {}).get('report_signature')==signature and previous_reports[0].get('report'):
        meter['shared_hit']=True
        return previous_reports[0]['report'],[],True
    seen={market.url(x['url']) for x in db.request('GET',f'bot_seen?user_id=eq.{job["user_id"]}&select=url&limit=1000')}
    settings=dict(s,_seen=seen)
    report,urls=market.render(row['payload'],settings,rates,center,row['created_at'],hit and not meter['calls'])
    if job.get('shared_reports_enabled'):
        # Shared version has no investor identity or previous-view history.
        shared_report,shared_urls=market.render(row['payload'],s,rates,center,row['created_at'],True)
        expiry=datetime.fromisoformat(row['expires_at'].replace('Z','+00:00'))
        for rate in rates['rates']:
            expiry=min(expiry,datetime.fromisoformat(rate['date']).replace(tzinfo=timezone.utc)+timedelta(days=15))
        try:
            db.rpc('bot_shared_publish',{'p_settings':s,'p_report':shared_report,'p_urls':shared_urls,'p_expires':expiry.isoformat()})
        except Exception:
            # An auxiliary cache failure must not discard an already paid, valid report.
            meter['shared_publish_failed']=True
    return report,urls,hit

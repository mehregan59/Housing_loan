"""Shared research with three small, bounded listing batches; free cache hits."""
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


class ResearchDataError(Exception):
    def __init__(self,code):
        self.code=code


def recover_complete_fields(text):
    """Keep only fully decoded root fields/array items; never repair numeric strings."""
    decoder=json.JSONDecoder(); result={}; i=0
    def whitespace(index):
        while index<len(text) and text[index].isspace(): index+=1
        return index
    i=whitespace(i)
    if i>=len(text) or text[i]!='{': return result
    i+=1
    try:
        while True:
            i=whitespace(i)
            if i>=len(text) or text[i]=='}': break
            key,i=decoder.raw_decode(text,i)
            if not isinstance(key,str): break
            i=whitespace(i)
            if i>=len(text) or text[i]!=':': break
            i=whitespace(i+1)
            if i<len(text) and text[i]=='[':
                items=[];result[key]=items;i+=1
                while True:
                    i=whitespace(i)
                    if i>=len(text): return result
                    if text[i]==']': i+=1;break
                    item,i=decoder.raw_decode(text,i);items.append(item);i=whitespace(i)
                    if i<len(text) and text[i]==',': i+=1
                    elif i<len(text) and text[i]==']': i+=1;break
                    else: return result
            else:
                value,i=decoder.raw_decode(text,i);result[key]=value
            i=whitespace(i)
            if i<len(text) and text[i]==',': i+=1
            else: break
    except (json.JSONDecodeError,ValueError): pass
    return result


def partial_report(pool,s,checked):
    de=s.get('language')=='de'
    def t(en,ger): return market.fa(en) if s.get('language')=='fa' else ger if de else en
    lines=[t('⚠️ Partial research — no confirmed investment recommendations','⚠️ Recherche unvollständig — keine bestätigten Anlageempfehlungen'),
           t('Last researched: ','Zuletzt recherchiert: ')+checked[:10],
           t('Location/radius could not be fully verified. Your limits have not been changed.','Standort/Radius nicht ausreichend verifiziert. Grenzen wurden nicht geändert.')]
    for x in pool.get('listings',[]):
        lines.extend(['\n📍 '+x['town']+' · '+x['title'][:90],f'🏷 €{x["price_eur"]:,.0f} · {x["size_m2"]:g} m²',
                      t('🔎 Research lead only; eligibility and financing are not verified.','🔎 Nur Recherchehinweis; Eignung und Finanzierung ungeprüft.'),'🔗 '+x['url']])
    lines.append(t(market.DISCLAIMER,'Nur Schätzungen; keine Finanzberatung oder Finanzierungszusage. Vor Entscheidungen selbst prüfen.'))
    return '\n'.join(lines),[]


# Coordinates are stored once per municipality, rather than in every apartment.
# Area benchmarks are optional enrichment, not a prerequisite for discovery.
COMPACT_FIELDS = ('url','title','town','state','country','price_eur','size_m2',
                  'rent_monthly','owner_cost_monthly','broker_pct','tax_pct',
                  'tax_source_url','year_built','energy_class','tenure','auction',
                  'risk_en','risk_de')
DISCOVERY_SCHEMA = market.obj({'center':market.POINT,'places':market.arr(market.POINT),
    'listings':market.arr(market.obj({k:market.LISTING['properties'][k] for k in COMPACT_FIELDS})),
    'search_note_en':market.S,'search_note_de':market.S})


def expand_discovery(data):
    """Supply unknown optional fields, never fabricated financial amounts."""
    unknown={'value':None,'kind':'unknown','basis':'','source_url':''}
    listings=[]
    for item in data.get('listings',[]):
        listings.append({'opened':True,'lat':None,'lon':None,'location_source_url':'',
                         'area_price_per_m2':dict(unknown),**item})
    return {**data,'listings':listings}


PORTAL_GROUPS = (
    ['immobilienscout24.de','immowelt.de'],
    ['kleinanzeigen.de','ohne-makler.net'],
    ['local estate agents','immobilienscout24.de','immowelt.de'],
)


def listing_batch_prompt(settings,radius,now,batch,known_urls,pool=None):
    """Different explicit portal/town tasks, without private financial settings."""
    center=market.point(pool['center']) if pool else None
    towns=[]
    for place in (pool or {}).get('places',[]):
        point=market.point(place)
        if center and point and market.distance(center,point)<=radius and market.location_norm(place['name'])!=market.location_norm(settings['location']):
            if place['name'] not in towns: towns.append(place['name'])
    task={
        'today':str(now.date()),'location':settings['location'],'country':'Germany',
        'search_radius_km':radius,'batch':batch+1,'priority_sites':PORTAL_GROUPS[batch],
        'priority_towns':towns[batch-1::2][:6] if batch else [],
        'already_collected_urls':known_urls,'target_distinct_listings':8,
        'required_searches':[
            f'site:{site} Eigentumswohnung kaufen {town}'
            for town in ((towns[batch-1::2][:3] if batch else []) or [settings['location']])
            for site in PORTAL_GROUPS[batch] if '.' in site
        ],
    }
    prompt=json.dumps(task,ensure_ascii=False)
    prompt+='\nSearch the specified portals separately and several municipalities within the radius. For batch 1 also identify and source at least six nearby municipality points across the radius where available; later batches prioritise other towns and local agents. Do not only search the city centre. Include different price bands, prioritising affordable apartments. Collect NEW distinct apartments independently of investor financial limits. Search result category pages are discovery only: open individual listing pages to verify price and size. Do not reopen already_collected_urls. If a portal blocks access, switch to another portal or accessible local agents. Aim for 8 verified apartments in this small batch; never pad. Finish valid JSON before the output limit. Optional missing fields do not disqualify an apartment; use null. Use only fields in the compact schema. Keep risk strings under 80 characters and estimate basis under 100 characters. Do not research area purchase-price benchmarks. Collect sourced municipality coordinates once in places, not per apartment; reuse points for the same municipality. Tax requires an official source. Estimates require relevant cited evidence; otherwise unknown. No calculations or narrative report.'
    if pool:
        prompt+='\nPreviously verified public municipality points (reuse with their source URLs): '+json.dumps(pool.get('places',[])[:30],ensure_ascii=False)
    return prompt


def merge_listing_batches(old,new):
    merged={market.url(x['url']):x for x in old.get('listings',[])}
    merged.update({market.url(x['url']):x for x in new.get('listings',[])})
    places={market.location_norm(x['name']):x for x in old.get('places',[])}
    places.update({market.location_norm(x['name']):x for x in new.get('places',[])})
    center=new['center'] if market.point(new['center']) else old['center']
    return {**old,**new,'center':center,'listings':list(merged.values()),'places':list(places.values()),
            'research_partial':old.get('research_partial',False) or new.get('research_partial',False)}


def analyse(db,job,meter):
    from openai import OpenAI
    from agent import estimate_cost
    s={k:v for k,v in job['settings'].items() if not k.startswith('_')}
    if s.get('country','Germany')!='Germany': raise ResearchDataError('UnsupportedCountry')
    if MODEL not in ('gpt-6.1-sol','gpt-6-astra'): raise ResearchDataError('UnpricedModel')
    now=datetime.now(timezone.utc)
    force_refresh=job.get('force_refresh',False)
    if job.get('shared_reports_enabled') and not force_refresh:
        saved=db.rpc('bot_shared_get',{'p_settings':s})
        if saved:
            meter['shared_hit']=True
            meter['partial']=saved['report'].startswith(('⚠️ Partial research','⚠️ Teilrecherche'))
            return saved['report'],saved['urls'],True
    # A single control lock reserves a fresh research budget; Actions serializes workers.
    reserved=False
    def extract(kind,prompt,schema,max_tools,max_output,verified_pool=None):
        nonlocal reserved
        if not reserved:
            if not db.rpc('bot_research_reserve',{'p_id':job['id']}): return None
            reserved=True
        meter['stage']=kind
        meter['pending']=True
        response=OpenAI(timeout=480,max_retries=0).responses.create(
            model=MODEL,instructions=Path('research_prompt.txt').read_text(),input=prompt,
            tools=[{'type':'web_search','search_context_size':'low'}],
            text={'format':{'type':'json_schema','name':kind,'strict':True,'schema':schema}},
            max_tool_calls=max_tools,max_output_tokens=max_output,
            include=['web_search_call.action.sources'],store=False)
        data=response.model_dump()
        cost,usage=estimate_cost(data,MODEL)
        completion=data.get('status','unknown')
        reason=(data.get('incomplete_details') or {}).get('reason')
        text=response.output_text or ''
        usage.update(stage=kind,completion_status=completion,incomplete_reason=reason,max_output_tokens=max_output,output_text_chars=len(text))
        meter['cost']+=cost;meter['calls'].append(usage);meter['pending']=False
        sources=retrieved_sources(data)
        opened={item['action']['url'] for item in data.get('output',[]) if item.get('type')=='web_search_call' and item.get('action',{}).get('type')=='open_page' and item['action'].get('url') and item.get('status','completed')=='completed'}
        truncated=completion=='incomplete' and reason=='max_output_tokens'
        if completion not in ('completed','incomplete'): raise ResearchDataError(kind.title()+'ResponseNotCompleted')
        if completion=='incomplete' and not truncated: raise ResearchDataError(kind.title()+'ResponseIncomplete')
        try: extracted=json.loads(text)
        except json.JSONDecodeError:
            if not truncated: raise ResearchDataError(kind.title()+'InvalidJSON') from None
            extracted=recover_complete_fields(text)
        if not isinstance(extracted,dict): raise ResearchDataError(kind.title()+'InvalidRoot')
        checkpoint={'stage':kind,'completion_status':completion,'sources':sorted(market.source_set(sources))[:160],'opened_urls':sorted(market.source_set(opened))[:60],'extracted':extracted}
        if len(json.dumps(checkpoint))<=180000: meter.setdefault('checkpoints',[]).append(checkpoint)
        # Persist usable public evidence before later checks; no keys or private finances.
        try: db.request('PATCH','bot_jobs?id=eq.'+job['id'],{'usage':{'pipeline':2,'research_calls':meter['calls'],'checkpoints':meter.get('checkpoints',[])}})
        except Exception: meter['checkpoint_save_failed']=True
        if not sources: raise ResearchDataError(kind.title()+'NoRetrievedSources')
        if truncated: meter.setdefault('warnings',[]).append(kind.title()+'OutputLimitPartial')
        if kind=='rates':
            return market.validate_rates(extracted,sources,now)
        validated=market.validate_pool(expand_discovery(extracted),sources,opened)
        # These points were source-validated when the fresh public cache was
        # created. Reuse exact saved points, never model-asserted new coordinates.
        if verified_pool:
            inherited={market.location_norm(p['name']):p for p in [verified_pool['center']]+verified_pool.get('places',[]) if market.point(p)}
            current={market.location_norm(p['name']):p for p in validated['places']}
            validated['places']=list({**inherited,**current}.values())

        # Use only independently sourced points for the requested municipality.
        candidates=validated['places']+[{'name':x['town'],'lat':x['lat'],'lon':x['lon'],'source_url':x['location_source_url']} for x in validated['listings'] if market.point(x)]
        center=next((p for p in candidates if market.location_norm(p['name'])==market.location_norm(s['location']) and market.point(p)),None)
        if center is not None:
            validated['center']=center
            if center not in validated['places']: validated['places'].append(center)
        else:
            validated['center']={'name':s['location'],'lat':None,'lon':None,'source_url':''}
            meter.setdefault('warnings',[]).append('SearchCenterUnverified')
        validated['research_partial']=truncated or center is None
        return validated
    def save(key,kind,payload,radius=None):
        # Service-only cache contains public property data, never investor settings/IDs.
        db.request('DELETE','bot_market_cache?cache_key=eq.'+quote(key,safe=''))
        row={'cache_key':key,'kind':kind,'version':market.VERSION,'payload':payload,
             'created_at':now.isoformat(),'expires_at':(now+timedelta(days=market.TTL_DAYS)).isoformat(),
             'radius_km':radius}
        if kind=='pool' and payload.get('retained_expires_at'):
            row['expires_at']=min(row['expires_at'],payload['retained_expires_at'])
            row['created_at']=min(row['created_at'],payload['oldest_researched_at'])
        db.request('POST','bot_market_cache',row)
        return row
    rate_key=market.cache_key('rates',s)
    rate_rows=db.request('GET','bot_market_cache?cache_key=eq.'+quote(rate_key,safe=''))
    rates=None
    if rate_rows and market.fresh(rate_rows[0],now):
        rates=rate_rows[0]['payload']
        if any((now.date()-datetime.fromisoformat(x['date']).date()).days>14 for x in rates['rates']): rates=None
    if rates is None:
        rates=extract('rates',f'Today {now.date()}. Find nominal German mortgage rates for {s["fixed_rate_years"]}-year fixation from at least two independent providers, e.g. Interhyp, Dr. Klein, FMH. Source dates required. Effective APR must not be labelled nominal. Return no rates if unavailable.',market.RATE_SCHEMA,4,4000)
        if rates is not None: save(rate_key,'rates',rates)
    rates=rates or {'rates':[]}
    pool_rows=db.request('GET','bot_market_cache?kind=eq.pool&version=eq.2&expires_at=gt.'+quote(now.isoformat(),safe='')+'&order=created_at.desc&limit=500')
    row,center=market.choose_pool(pool_rows,s,now)
    hit=row is not None
    supplement=row if force_refresh else None
    if force_refresh: row=None;hit=False
    if row is None:
        key=market.cache_key('pool',s); radius=math.ceil(float(s['radius_km'])/25)*25+5
        previous=db.request('GET','bot_market_cache?cache_key=eq.'+quote(key,safe=''))
        if not force_refresh and previous and market.fresh(previous[0],now) and market.point(previous[0]['payload']['center']) is None:
            meter['partial']=True
            report,urls=partial_report(previous[0]['payload'],s,previous[0]['created_at'])
            return report,urls,True
        old_urls=[x['url'] for x in supplement['payload']['listings']] if supplement else [x['url'] for x in previous[0]['payload']['listings'][:20]] if previous else []
        pool=None
        completed_batches=0
        attempted_batches=0
        for batch in range(3):
            # Spend at most the previous 24 listing tool calls, in three smaller
            # contexts. Stop optional expansion before costs grow; reservations
            # remain the authoritative monthly gate. This is not a hard API price cap.
            if batch and meter['cost']>=0.80:
                meter.setdefault('warnings',[]).append('ExpansionStoppedAtCostGuard')
                break
            known=old_urls+[x['url'] for x in (pool or {}).get('listings',[])]
            verified_pool=pool or (supplement or {}).get('payload')
            prompt=listing_batch_prompt(s,radius,now,batch,known,verified_pool)
            try:
                attempted_batches+=1
                extra=extract('pool',prompt,DISCOVERY_SCHEMA,8,5000,verified_pool)
            except ResearchDataError as exc:
                if pool is None or meter['pending']: raise
                meter.setdefault('warnings',[]).append('Expansion'+exc.code)
                pool['research_partial']=True
                break
            if extra is None: break
            if not extra.get('research_partial'): completed_batches+=1
            pool=extra if pool is None else merge_listing_batches(pool,extra)
            # No arbitrary result cap: every verified item in all batches survives.
            # An output-truncated batch retains complete items and does NOT
            # cancel the other discovery batches. Each uses a fresh context.
        if pool is None:
            message='Suchbudget nicht verfügbar. Kein aktueller gemeinsamer Bestand deckt Ihren Standort ab. Ihre Grenzen wurden nicht geändert. Mit /last können Sie einen gespeicherten Bericht abrufen.' if s.get('language')=='de' else 'Search budget unavailable. No fresh shared listing pool covers your location. Your limits have not been changed. Try /last for a saved report.'
            return (message+'\n\n'+market.DISCLAIMER,[],False)
        if supplement:
            pool={**merge_listing_batches(supplement['payload'],pool),'retained_expires_at':supplement['expires_at'],'oldest_researched_at':supplement['created_at']}
            if market.point(pool['center']) is None: pool['center']=supplement['payload']['center']
        pool['discovery_batches']={'planned':3,'attempted':attempted_batches,'completed':completed_batches}
        row=save(key,'pool',pool,radius);center=market.point(pool['center'])
        if center is None:
            meter['partial']=True
            report,urls=partial_report(pool,s,row['created_at'])
            return report,urls,False
    # Re-sort previously seen homes after new homes; keep them rather than inventing replacements.
    signature=hashlib.sha256(json.dumps({'renderer_version':9,'settings':s,'pool':row['payload'],'checked':row['created_at'],'rates':rates},sort_keys=True).encode()).hexdigest()
    meter['report_signature']=signature
    previous_reports=db.request('GET',f'bot_jobs?user_id=eq.{job["user_id"]}&status=eq.complete&order=finished_at.desc&limit=1&select=report,usage')
    if previous_reports and (previous_reports[0].get('usage') or {}).get('report_signature')==signature and previous_reports[0].get('report'):
        meter['shared_hit']=True
        return previous_reports[0]['report'],[],True
    seen={market.url(x['url']) for x in db.request('GET',f'bot_seen?user_id=eq.{job["user_id"]}&select=url&limit=1000')}
    settings=dict(s,_seen=seen)
    report,urls=market.render(row['payload'],settings,rates,center,row['created_at'],hit and not meter['calls'])
    if row['payload'].get('research_partial'):
        meter['partial']=True
        notice='⚠️ Teilrecherche: Nur vollständig erfasste und verifizierte Daten wurden übernommen.\n\n' if s.get('language')=='de' else '⚠️ Partial research: only fully extracted, verified data was retained.\n\n'
        if s.get('language')=='fa': notice=market.fa(notice)
        report=notice+report
    if job.get('shared_reports_enabled'):
        # Shared version has no investor identity or previous-view history.
        shared_report,shared_urls=market.render(row['payload'],s,rates,center,row['created_at'],True)
        if row['payload'].get('research_partial'): shared_report=notice+shared_report
        expiry=datetime.fromisoformat(row['expires_at'].replace('Z','+00:00'))
        for rate in rates['rates']:
            expiry=min(expiry,datetime.fromisoformat(rate['date']).replace(tzinfo=timezone.utc)+timedelta(days=15))
        try:
            db.rpc('bot_shared_publish',{'p_settings':s,'p_report':shared_report,'p_urls':shared_urls,'p_expires':expiry.isoformat()})
        except Exception:
            # An auxiliary cache failure must not discard an already paid, valid report.
            meter['shared_publish_failed']=True
    return report,urls,hit

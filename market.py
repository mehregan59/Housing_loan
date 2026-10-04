"""Shared source-backed research; deterministic screening and bilingual reports."""
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone, date
from urllib.parse import urlsplit, urlunsplit

VERSION = 2
TARGET_LISTINGS = 12
MAX_LISTINGS = 30
TTL_DAYS = 7
DISCLAIMER = 'Estimates only; general information, not financial advice or a financing commitment. Verify independently before deciding.'


def norm(s):
    return ' '.join(str(s).casefold().split())


def location_norm(s):
    name=norm(s)
    return 'freiburg' if name in ('freiburg','freiburg im breisgau','freiburg i. br.') else name


def source_set(sources):
    valid=set()
    for source in sources:
        try: valid.add(url(source))
        except (ValueError,TypeError,AttributeError): pass
    return valid


def url(s):
    p = urlsplit(s.strip())
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Invalid URL')
    # Tracking differences must not make one apartment appear new.
    q = '&'.join(x for x in p.query.split('&') if x and not x.lower().startswith(('utm_', 'gclid=', 'fbclid=')))
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/'), q, ''))


def obj(props):
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}


def arr(item):
    return {'type':'array','items':item}


S = {'type':'string'}
N = {'type':['number','null']}
B = {'type':'boolean'}
POINT = obj({'name':S,'lat':N,'lon':N,'source_url':S})
VALUE = obj({'value':N,'kind':{'type':'string','enum':['actual','estimate','unknown']},'basis':S,'source_url':S})
LISTING = obj({'url':S,'title':S,'town':S,'state':S,'country':S,'lat':N,'lon':N,
    'location_source_url':S,'opened':B,'price_eur':N,'size_m2':N,'rent_monthly':VALUE,
    'owner_cost_monthly':VALUE,'area_price_per_m2':VALUE,'broker_pct':N,'tax_pct':N,'tax_source_url':S,
    'year_built':N,'energy_class':S,'tenure':S,'auction':{'type':['boolean','null']},
    'risk_en':S,'risk_de':S})
POOL_SCHEMA = obj({'center':POINT,'places':arr(POINT),'listings':arr(LISTING),'search_note_en':S,'search_note_de':S})
RATE_SCHEMA = obj({'rates':arr(obj({'source_url':S,'date':S,'rate_pct':N,'rate_type':{'type':'string','enum':['nominal','effective']}}))})


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a,*b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371 * 2 * math.asin(math.sqrt(min(1,h)))


def point(p):
    a,b = p.get('lat'),p.get('lon')
    if type(a) not in (int,float) or type(b) not in (int,float) or not math.isfinite(a+b):
        return None
    return (a,b) if 47 <= a <= 55.2 and 5.5 <= b <= 15.6 else None


def number(x, low=0, high=100000000):
    return type(x) in (int,float) and math.isfinite(x) and low <= x <= high


def official_tax_source(source):
    host=urlsplit(source).hostname or ''
    domains=('baden-wuerttemberg.de','fv-bwl.de','bayern.de','bayernportal.de','brandenburg.de',
             'berlin.de','bremen.de','hamburg.de','hessen.de','mv-regierung.de','regierung-mv.de',
             'mecklenburg-vorpommern.de','niedersachsen.de','nrw.de','finanzverwaltung.nrw.de',
             'rlp.de','saarland.de','sachsen.de','sachsen-anhalt.de','schleswig-holstein.de','thueringen.de')
    return any(host==d or host.endswith('.'+d) for d in domains)


def validate_value(v, allowed):
    if not isinstance(v,dict) or v.get('kind') not in ('actual','estimate','unknown'):
        raise ValueError('Invalid extracted value')
    if v['value'] is None:
        return {'value':None,'kind':'unknown','basis':'','source_url':''}
    if not number(v['value']) or v['kind']=='unknown' or url(v['source_url']) not in allowed:
        raise ValueError('Unsupported extracted value')
    if v['kind']=='estimate' and not v['basis'].strip():
        raise ValueError('Missing estimate basis')
    return v


def validate_pool(data, sources, opened_urls):
    allowed=source_set(sources); opened=source_set(opened_urls)
    center=data.get('center') or {'name':'','lat':None,'lon':None,'source_url':''}
    places=[]
    for p in [center]+data.get('places',[])[:60]:
        try:
            if point(p) and url(p['source_url']) in allowed: places.append(p)
        except (ValueError,KeyError,TypeError): pass
    if not places or center not in places:
        center={**center,'lat':None,'lon':None}
    listings=[]; seen=set(); rejected=0
    optional_unknown=0
    for x in data.get('listings',[])[:MAX_LISTINGS]:
        try:
            u=url(x['url'])
            if u in seen: continue
            if u not in allowed or u not in opened or not x['opened'] or x['country']!='Germany': raise ValueError()
            x=dict(x)
            try: located=point(x) and url(x['location_source_url']) in allowed
            except (ValueError,KeyError,TypeError): located=False
            if not located: x.update(lat=None,lon=None)
            if not number(x['price_eur'],1) or not number(x['size_m2'],1,2000): raise ValueError()
            if x['broker_pct'] is not None and not number(x['broker_pct'],0,15): raise ValueError()
            try: tax_ok=x['tax_pct'] is None or (number(x['tax_pct'],3.5,6.5) and url(x['tax_source_url']) in allowed and official_tax_source(x['tax_source_url']))
            except (ValueError,KeyError,TypeError): tax_ok=False
            if not tax_ok: x['tax_pct']=None;optional_unknown+=1
            x['url']=u
            for field in ('rent_monthly','owner_cost_monthly','area_price_per_m2'):
                try: x[field]=validate_value(x[field],allowed)
                except (ValueError,KeyError,TypeError):
                    x[field]={'value':None,'kind':'unknown','basis':'','source_url':''};optional_unknown+=1
            seen.add(u); listings.append(x)
        except (ValueError,KeyError,TypeError):
            rejected+=1
    return {**data,'center':center,'places':places,'listings':listings,'rejected_unverified':rejected,'optional_fields_unknown':optional_unknown}


def validate_rates(data,sources,now):
    allowed=source_set(sources); rates=[]
    for x in data.get('rates',[]):
        try:
            d=date.fromisoformat(x['date']); u=url(x['source_url'])
            if u not in allowed or not number(x['rate_pct'],0.1,20) or not 0 <= (now.date()-d).days <= 14: continue
            if x['rate_type'] not in ('nominal','effective'): continue
            rates.append(x)
        except (ValueError,KeyError,TypeError): continue
    # Never mix nominal and effective rates in an annuity formula.
    nominal=[x for x in rates if x['rate_type']=='nominal']
    return {'rates':nominal if len({'.'.join(urlsplit(x['source_url']).hostname.split('.')[-2:]) for x in nominal})>=2 else [],
            'note':'Two recent nominal-rate sources required; effective APR is not a contractual interest rate.'}


def cache_key(kind,s):
    v={'version':VERSION,'country':s.get('country','Germany')}
    if kind=='rates': v['years']=s['fixed_rate_years']
    else:
        v.update(location=norm(s['location']),radius=math.ceil(float(s['radius_km'])/25)*25+5)
    return kind+':'+hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest()


def fresh(row,now):
    try: return row['version']==VERSION and now < datetime.fromisoformat(row['expires_at'].replace('Z','+00:00'))
    except (KeyError,ValueError): return False


def choose_pool(rows,s,now):
    """Reuse nearby centers only when sourced coordinates prove radius coverage."""
    candidates=[]
    for r in rows:
        if not fresh(r,now): continue
        p=r['payload']; center=point(p['center'])
        if center is None: continue
        for place in p['places']:
            if location_norm(place['name'])!=location_norm(s['location']) or not point(place): continue
            gap=distance(center,point(place))
            if gap<=5 and gap+float(s['radius_km'])+1<=r['radius_km']:
                candidates.append((r['radius_km'],r,point(place)))
    return min(candidates,key=lambda x:x[0])[1:] if candidates else (None,None)


# Official rate verified 2026-10-04; time-bounded fallback for missing extraction.
BW_TAX_SOURCE='https://finanzamt-bw.fv-bwl.de/%2CLde_DE/Startseite/Service/Wann%2Bmuss%2Bich%2BGrunderwerbsteuer%2Bzahlen%2Bund%2Bwie%2Bhoch%2Bist%2Bdiese_'
def with_verified_tax(x):
    if x['tax_pct'] is None and norm(x['state'])==norm('Baden-Württemberg') and 0 <= (date.today()-date(2026,10,4)).days <= 90:
        return dict(x,tax_pct=5,tax_source_url=BW_TAX_SOURCE,tax_lookup=True)
    return x


def calculate(x,s,rates):
    r=[z['rate_pct'] for z in rates['rates']]
    midpoint=(min(r)+max(r))/2 if r else None
    stress=max(r)+1 if r else None
    loan=None if x['broker_pct'] is None or x['tax_pct'] is None else max(0,x['price_eur']*(1+(x['tax_pct']+2+x['broker_pct'])/100)-s['equity_eur'])
    pay=None if loan is None or midpoint is None else loan*(midpoint+s['repayment_pct'])/1200
    stressed=None if loan is None or stress is None else loan*(stress+s['repayment_pct'])/1200
    rent=x['rent_monthly']['value']; owner=x['owner_cost_monthly']['value']
    yield_pct=None if rent is None else rent*1200/x['price_eur']
    cash=None if rent is None or owner is None or pay is None else rent-pay-owner-x['size_m2']
    stress_cash=None if cash is None else rent-stressed-owner-x['size_m2']
    return {'loan':loan,'payment':pay,'stress_payment':stressed,'yield':yield_pct,'cash':cash,'stress_cash':stress_cash,'ppm':x['price_eur']/x['size_m2']}


def screen(pool,s,rates,center):
    matches=[]; flexible=[]; blockers={}
    for original in pool['listings']:
        x=with_verified_tax(original)
        if point(x) is None:
            # Cached pools already contain source-validated municipality points.
            candidates=[p for p in pool.get('places',[]) if location_norm(p['name'])==location_norm(x['town']) and point(p)]
            if candidates and all(distance(point(candidates[0]),point(p))<1 for p in candidates):
                x=dict(x,lat=candidates[0]['lat'],lon=candidates[0]['lon'],location_source_url=candidates[0]['source_url'])
        if point(x) is None:
            blockers['location unverified']=blockers.get('location unverified',0)+1;continue
        if 'Erbpacht' in s.get('exclude',[]) and any(word in norm(x['tenure']) for word in ('erbpacht','erbbaurecht','leasehold')): continue
        if any(norm(e) in norm(x['tenure']) for e in s.get('exclude',[])) or ('Zwangsversteigerung' in s.get('exclude',[]) and x['auction'] is True): continue
        checks_pending=[]
        if 'Erbpacht' in s.get('exclude',[]) and not x['tenure']: checks_pending.append('tenure')
        if 'Zwangsversteigerung' in s.get('exclude',[]) and x['auction'] is None: checks_pending.append('auction')
        d=distance(center,point(x)); c=calculate(x,s,rates)
        fail=[]; mild=[]
        checks=[('max_price_eur',x['price_eur'],s['max_price_eur'],False,1.10),
                ('min_size_m2',x['size_m2'],s['min_size_m2'],True,.90),
                ('radius_km',d,s['radius_km'],False,1.10),
                ('max_loan_eur',c['loan'],s['max_loan_eur'],False,1.10),
                ('max_price_per_m2',c['ppm'],s.get('max_price_per_m2'),False,1.10),
                ('target_gross_yield_pct',c['yield'],s.get('target_gross_yield_pct'),True,.90),
                ('min_monthly_cashflow_eur',c['cash'],s.get('min_monthly_cashflow_eur'),True,None)]
        for field,value,limit,minimum,tolerance in checks:
            if limit is None: continue
            if value is None:
                fail.append((field,None)); continue
            if (value<limit if minimum else value>limit):
                fail.append((field,value))
                nearby=(value>=limit-50) if field=='min_monthly_cashflow_eur' else (value>=limit*tolerance if minimum else value<=limit*tolerance)
                if nearby: mild.append((field,value))
        for f,v in fail:
            label='financing data missing' if f=='max_loan_eur' and v is None else f
            blockers[label]=blockers.get(label,0)+1
        # Scores are an explicit screening rubric, with uncertainty/risk penalties.
        score=2 + (min(4,c['yield']/2) if c['yield'] is not None else 0)
        score+=2 if c['cash'] is not None and c['cash']>=0 else 0
        score+=1 if c['stress_cash'] is not None and c['stress_cash']>=0 else 0
        score-=1 if x['energy_class'].upper() in ('E','F','G','H') else 0
        score-=1 if x['owner_cost_monthly']['kind']!='actual' else 0
        score-=1 if checks_pending else 0
        item={'checks_pending':checks_pending,'listing':x,'calc':c,'distance':d,'score':round(max(0,min(10,score)),1),'changes':fail}
        if not fail: matches.append(item)
        elif len(fail)<=2 and len(mild)==len(fail): flexible.append(item)
    preferred={norm(a) for a in s.get('areas',[])}
    key=lambda x:(x['listing']['url'] not in s.get('_seen',set()),norm(x['listing']['town']) in preferred,x['score'],x['calc']['cash'] if x['calc']['cash'] is not None else -1e9)
    return sorted(matches,key=key,reverse=True),sorted(flexible,key=key,reverse=True),blockers


def render(pool,s,rates,center,checked_at,cache_hit):
    de=s.get('language')=='de'
    def t(en,ger): return ger if de else en
    labels={'max_price_eur':t('purchase price','Kaufpreis'),'min_size_m2':t('minimum size','Mindestgröße'),
            'radius_km':t('search radius','Suchradius'),'max_loan_eur':t('loan limit','Kreditgrenze'),
            'max_price_per_m2':t('price per m²','Preis pro m²'),'target_gross_yield_pct':t('rental yield','Mietrendite'),
            'min_monthly_cashflow_eur':t('monthly result','Monatsergebnis'),
            'financing data missing':t('financing data missing','Finanzierungsdaten fehlen'),
            'location unverified':t('location unverified','Standort ungeprüft'),
            'unverified tenure/auction status':t('ownership or auction status unknown','Eigentums- oder Auktionsstatus unbekannt')}
    def money(v): return t('unknown','unbekannt') if v is None else f'€{v:,.0f}'
    def result(v):
        if v is None: return t('unknown: rent, financing or owner costs missing','unbekannt: Miete, Finanzierung oder Eigentümerkosten fehlen')
        return money(abs(v))+t('/month '+('left' if v>=0 else 'extra needed'),'/Monat '+('übrig' if v>=0 else 'zuzuzahlen'))
    m,f,blockers=screen(pool,s,rates,center)
    lines=[t('🏠 Apartment screening','🏠 Wohnungssuche')+' — '+s['location'],
           t('Data last researched: ','Daten zuletzt recherchiert: ')+checked_at[:10],
           t('Gross rental yield is before costs, not profit.', 'Bruttomietrendite ist vor Kosten, kein Gewinn.'),
           t(f'{len(m)} meet numerical limits; {len(f)} nearby alternatives.',f'{len(m)} erfüllen die Zahlengrenzen; {len(f)} ähnliche Alternativen.')]
    if not m:
        lines.append(t('No confirmed matches. Main blockers: ','Keine bestätigten Treffer. Hauptgrenzen: ')+(', '.join(labels[k] for k in sorted(blockers,key=blockers.get,reverse=True)[:3]) or t('insufficient verified listings','zu wenige verifizierte Angebote')))
    def block(item,alternative=False):
        x=item['listing']; c=item['calc']
        title='\n'+t('🔄 If you are flexible','🔄 Bei etwas Flexibilität') if alternative else '\n🏠'
        rent_kind=t({'actual':'advertised','estimate':'estimated','unknown':'unknown'}[x['rent_monthly']['kind']],{'actual':'angegeben','estimate':'geschätzt','unknown':'unbekannt'}[x['rent_monthly']['kind']])
        owner_kind=t(x['owner_cost_monthly']['kind'],{'actual':'angegeben','estimate':'geschätzt','unknown':'unbekannt'}[x['owner_cost_monthly']['kind']])
        out=[title+' — '+x['title'][:90],
             '📍 '+x['town']+', '+x['state']+' · ~'+f'{item["distance"]:.1f} km '+t('from ','von ')+s['location'],
             t('📈 Gross rental yield: ','📈 Bruttomietrendite: ')+(f'{c["yield"]:.2f}%' if c['yield'] is not None else t('unknown','unbekannt'))+t(' before costs',' vor Kosten'),
             t('🏦 Estimated loan needed: ','🏦 Geschätzter Kreditbedarf: ')+money(c['loan']),
             t('💵 Cold rent: ','💵 Kaltmiete: ')+money(x['rent_monthly']['value'])+t('/month','/Monat')+' · '+rent_kind,
             t('🗓 Annual rental income: ','🗓 Jährliche Mieteinnahmen: ')+money(None if x['rent_monthly']['value'] is None else x['rent_monthly']['value']*12)+t(' before costs',' vor Kosten'),
             t('🏷 Purchase price: ','🏷 Kaufpreis: ')+money(x['price_eur']),
             f'📐 {x["size_m2"]:g} m² · {money(c["ppm"])}/m²',
             t('💳 Estimated mortgage payment: ','💳 Geschätzte Kreditrate: ')+money(c['payment'])+t('/month','/Monat'),
             t('💰 Estimated monthly result: ','💰 Geschätztes Monatsergebnis: ')+result(c['cash']),
             t('🌧 If interest rates rise: ','🌧 Bei höheren Zinsen: ')+result(c['stress_cash']),
             t('🏢 Owner building fees: ','🏢 Eigentümerkosten: ')+money(x['owner_cost_monthly']['value'])+t('/month','/Monat')+' · '+owner_kind+t(' (reserve contributions excluded)',' (ohne Rücklagen)'),
             t('🛠 Maintenance allowance: ','🛠 Instandhaltungsansatz: ')+money(x['size_m2'])+t('/month','/Monat'),
             t('🏗 Built: ','🏗 Baujahr: ')+(f'{x["year_built"]:.0f}' if x['year_built'] is not None else t('unknown','unbekannt'))+' · '+t('Energy: ','Energieklasse: ')+(x['energy_class'] or t('unknown','unbekannt')),
             t('⭐ Screening score: ','⭐ Suchbewertung: ')+f'{item["score"]}/10',
             t('💬 Verdict: ','💬 Einschätzung: ')+t('Rent covers estimated costs.' if c['cash'] is not None and c['cash']>=0 else 'Needs extra money or cost clarification.','Miete deckt geschätzte Kosten.' if c['cash'] is not None and c['cash']>=0 else 'Zuzahlung oder Kostenklärung nötig.')]
        if item['checks_pending']:
            out.append(t('⚠️ Provisional candidate: ownership type or auction status is not confirmed. Ask the seller before treating this as a match; your exclusions still apply.','⚠️ Vorläufiges Angebot: Eigentumsart oder Auktionsstatus nicht bestätigt. Vor einer Einstufung als Treffer beim Verkäufer prüfen; Ihre Ausschlüsse gelten weiterhin.'))
        if x['owner_cost_monthly']['value'] is None and x['rent_monthly']['value'] is not None and c['payment'] is not None:
            partial=x['rent_monthly']['value']-c['payment']-x['size_m2']
            out.append(t('🔎 Before unknown owner fees: ','🔎 Vor unbekannten Eigentümerkosten: ')+result(partial)+t(' (maintenance already included; final result unknown).',' (Instandhaltung bereits enthalten; Endergebnis unbekannt).'))
        if x['tax_pct'] is not None and x['broker_pct'] is not None:
            out.append(t('🧾 Purchase costs used: ','🧾 Angesetzte Kaufnebenkosten: ')+f'{x["tax_pct"]:g}% '+t('transfer tax','Grunderwerbsteuer')+f' + ~2% '+t('notary/registry','Notar/Grundbuch')+f' + {x["broker_pct"]:g}% '+t('buyer commission','Käuferprovision'))
        if x.get('tax_lookup'): out.append(t('Transfer tax: official state rate, verified 2026-10-04. ','Grunderwerbsteuer: amtlicher Landessatz, geprüft am 04.10.2026. ')+x['tax_source_url'])
        for field in ('rent_monthly','owner_cost_monthly'):
            v=x[field]
            if v['kind']=='estimate': out.append(t('Estimate basis: ','Schätzgrundlage: ')+v['basis'][:180]+' '+v['source_url'])
        if c['loan'] is None: out.append(t('Loan unknown: buyer commission or state tax missing.','Kredit unbekannt: Käuferprovision oder Landessteuer fehlt.'))
        benchmark=x['area_price_per_m2']['value']
        if benchmark and benchmark>0:
            difference=(c['ppm']/benchmark-1)*100
            out.append(t('Area average comparison: ','Vergleich mit Gebietsdurchschnitt: ')+f'{difference:+.0f}%'+t(' (not a property valuation). ',' (keine Immobilienbewertung). ')+x['area_price_per_m2']['basis'][:120]+' '+x['area_price_per_m2']['source_url'])
        if x['url'] in s.get('_seen',set()): out.append(t('Previously shown; still in the saved pool.','Bereits gezeigt; weiterhin im gespeicherten Bestand.'))
        if alternative:
            out.append(t('Outside your limits; required changes: ','Außerhalb Ihrer Grenzen; nötige Änderungen: ')+', '.join(labels[k]+' → '+(money(v) if k.endswith('_eur') else f'{v:.2f}'+(' m²' if k=='min_size_m2' else ' km' if k=='radius_km' else '%')) for k,v in item['changes']))
            if any(k=='max_loan_eur' for k,_ in item['changes']): out.append(t('Not financeable under your current loan cap.','Mit Ihrer aktuellen Kreditgrenze nicht finanzierbar.'))
        out.append(t('⚠️ Main risk: ','⚠️ Hauptrisiko: ')+(x['risk_de'] if de else x['risk_en'])[:220]);out.append(t('🔗 Listing: ','🔗 Anzeige: ')+x['url'])
        return '\n'.join(out)
    # More verified candidates, never padding; up to 8 strict + 3 flexible.
    shown=m[:8]; alternatives=f[:3] if len(m)<5 else []
    lines.extend(block(i) for i in shown)
    lines.extend(block(i,True) for i in alternatives)
    if len(m)>8: lines.append(t(f'{len(m)-8} more matching properties in the saved pool.',f'{len(m)-8} weitere passende Wohnungen im gespeicherten Bestand.'))
    lines.append('\n'+t('💶 MORTGAGE RATES','💶 BAUZINSEN'))
    if rates['rates']:
        rs=rates['rates']; values=[x['rate_pct'] for x in rs]
        lines.append(t('As of ','Stand ')+checked_at[:10]+' · '+t(f'{s["fixed_rate_years"]}-year fixed',f'{s["fixed_rate_years"]} Jahre fest'))
        lines.append(t('📊 Nominal interest range: ','📊 Sollzinsspanne: ')+f'{min(values):.2f}–{max(values):.2f}%')
        lines.append(t('🧮 Payment estimate uses: ','🧮 Für die Ratenschätzung: ')+f'{(min(values)+max(values))/2:.2f}%'+t(f' interest + {s["repayment_pct"]:g}% initial repayment',f' Zinsen + {s["repayment_pct"]:g}% anfängliche Tilgung'))
        lines.append(t('🌧 Stress scenario: ','🌧 Stresstest: ')+f'{max(values)+1:.2f}%'+t(' interest; this is not a change during an agreed fixed-rate period.',' Zinsen; keine Änderung während einer vereinbarten Zinsbindung.'))
        for r in rs[:2]:
            provider=(urlsplit(r['source_url']).hostname or '').removeprefix('www.')
            lines.append('• '+provider+': '+f'{r["rate_pct"]:.2f}%'+t(' nominal · dated ',' Sollzins · vom ')+r['date'])
            lines.append('🔗 '+r['source_url'])
        lines.append(t('✅ Source dates are no more than 14 days old.','✅ Quelldaten sind höchstens 14 Tage alt.'))
    else:
        lines.append(t('⚠️ Financing unknown: two recent nominal-rate sources unavailable.','⚠️ Finanzierung unbekannt: zwei aktuelle Sollzinsquellen fehlen.'))
    lines.append('\n'+t('📋 STILL TO CHECK','📋 NOCH ZU PRÜFEN'))
    lines.append(t('Ask sellers to confirm ownership type, auction status, lease, owner-only building fees and planned major repairs.','Verkäufer nach Eigentumsart, Auktionsstatus, Mietvertrag, nicht umlagefähigen Kosten und geplanten größeren Sanierungen fragen.'))
    lines.append('\n'+t('⚠️ Estimates include ~2% notary/registry and €1/m² monthly maintenance. Distances use approximate town centers. Taxes on income, empty months and major repairs are excluded. Check leases, building repair plans, rent controls and availability. Zero-equity financing is not guaranteed. Scores use a fixed screening rubric, not predictions.','⚠️ Schätzungen enthalten ca. 2% Notar/Grundbuch und 1 €/m² monatliche Instandhaltung. Entfernungen beziehen sich ungefähr auf Ortszentren. Einkommensteuer, Leerstand und größere Reparaturen fehlen. Mietverträge, Sanierungspläne, Mietregeln und Verfügbarkeit prüfen. Vollfinanzierung ist nicht garantiert. Bewertungen sind Suchhilfen, keine Prognosen.'))
    lines.append(t(DISCLAIMER,'Nur Schätzungen und allgemeine Informationen, keine Finanzberatung oder Finanzierungszusage. Vor Entscheidungen selbst prüfen.'))
    return '\n'.join(lines),[i['listing']['url'] for i in shown+alternatives]

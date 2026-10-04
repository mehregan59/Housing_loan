import copy
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock,patch
import market
import research
import agent

NOW=datetime(2026,10,4,12,tzinfo=timezone.utc)
SOURCE='https://example.de/property/1'
GEO='https://example.de/towns'
TAX='https://finanzamt-bw.fv-bwl.de/tax'
S={'country':'Germany','location':'Freiburg','radius_km':100,'max_price_eur':250000,'max_loan_eur':250000,'equity_eur':0,'min_size_m2':30,'repayment_pct':2,'fixed_rate_years':10,'max_price_per_m2':None,'target_gross_yield_pct':None,'min_monthly_cashflow_eur':None,'exclude':['Erbpacht','Zwangsversteigerung'],'language':'en','areas':[]}
R={'rates':[{'source_url':'https://interhyp.de/rates','date':'2026-10-04','rate_pct':4,'rate_type':'nominal'},{'source_url':'https://drklein.de/rates','date':'2026-10-03','rate_pct':5,'rate_type':'nominal'}]}

def value(amount,kind='actual'):
    return {'value':amount,'kind':kind if amount is not None else 'unknown','basis':'Comparable local buildings' if kind=='estimate' else '', 'source_url':SOURCE if amount is not None else ''}

def listing(**kw):
    return {'url':SOURCE,'title':'Apartment','town':'Freiburg','state':'Baden-Württemberg','country':'Germany','lat':48.0,'lon':7.85,'location_source_url':GEO,'opened':True,'price_eur':150000,'size_m2':32,'rent_monthly':value(460),'owner_cost_monthly':value(100),'area_price_per_m2':value(None),'broker_pct':3.57,'tax_pct':5,'tax_source_url':TAX,'year_built':1982,'energy_class':'E','tenure':'Freehold','auction':False,'risk_en':'Repair plans unknown','risk_de':'Sanierungspläne unbekannt',**kw}

def pool(items=None):
    c={'name':'Freiburg','lat':48.0,'lon':7.85,'source_url':GEO}
    return {'center':c,'places':[c],'listings':items if items is not None else [listing()],'search_note_en':'Partial coverage','search_note_de':'Teilweise Abdeckung'}

def row(kind='pool'):
    return {'cache_key':'key','kind':kind,'version':2,'payload':pool() if kind=='pool' else R,'radius_km':105,'created_at':NOW.isoformat(),'expires_at':(NOW+timedelta(days=7)).isoformat()}

def fake_collection_api(urls,truncated=False,no_center=False,expensive=False):
    import json
    client=Mock()
    def create(**kw):
        stage=kw['text']['format']['name'];response=Mock()
        if stage=='rates':
            extracted=R;output=[{'type':'web_search_call','action':{'type':'search','sources':[{'url':x['source_url']} for x in R['rates']]}}]
        elif stage=='links':
            extracted={'leads':[{'url':u,'town':'Freiburg','title':'Apartment'} for u in urls]}
            output=[{'type':'web_search_call','action':{'type':'search','sources':[{'url':u} for u in urls]}}]
        else:
            selected=json.loads(kw['input'].split('\n')[0])['individual_listing_urls']
            picked=selected[:1] if truncated else selected
            extracted=pool([listing(url=x['url'],rent_monthly=value(None),owner_cost_monthly=value(None)) for x in picked])
            if no_center: extracted['center']={'name':'Freiburg','lat':None,'lon':None,'source_url':''};extracted['places']=[]
            output=[{'type':'web_search_call','action':{'type':'open_page','url':x['url'],'sources':[{'url':GEO},{'url':TAX}]}} for x in picked]
        text=json.dumps(extracted)
        partial=truncated and stage=='pool'
        if partial: text=text[:-1]+',"unfinished":'
        response.output_text=text
        response.model_dump.return_value={'status':'incomplete' if partial else 'completed',
            'incomplete_details':{'reason':'max_output_tokens'} if partial else None,
            'usage':{'input_tokens':400000 if expensive else 2000,'output_tokens':500},'output':output}
        return response
    client.responses.create.side_effect=create
    return client


def collection_database(old=None):
    db=Mock();db.rpc.return_value=True
    def request(method,path,data=None):
        if method!='GET': return None
        if path.startswith('bot_market_cache?cache_key=eq.rates'):return [row('rates')]
        if path.startswith('bot_market_cache?kind=eq.pool') and old:return [old]
        return []
    db.request.side_effect=request
    return db


class MarketTests(unittest.TestCase):
    def test_reference_arithmetic_and_stress(self):
        c=market.calculate(listing(),S,R)
        self.assertAlmostEqual(c['loan'],165855)
        self.assertAlmostEqual(c['payment'],898.38125)
        self.assertAlmostEqual(c['stress_payment'],1105.7)
        self.assertAlmostEqual(c['cash'],-570.38125)
        self.assertAlmostEqual(c['yield'],3.68)

    def test_unknown_commission_never_zero_or_loan_capped(self):
        c=market.calculate(listing(broker_pct=None),S,R)
        self.assertIsNone(c['loan']); self.assertAlmostEqual(c['known_loan'],160500); self.assertEqual(c['missing_costs'],['broker_pct']); self.assertIsNone(c['cash'])
        c=market.calculate(listing(price_eur=240000),S,R)
        self.assertGreater(c['loan'],S['max_loan_eur'])
        m,f,_=market.screen(pool([listing(price_eur=240000)]),S,R,(48,7.85))
        self.assertFalse(m);self.assertTrue(f)
        self.assertIn(('max_loan_eur',c['loan']),f[0]['changes'])

    def test_missing_owner_cost_keeps_cash_unknown(self):
        c=market.calculate(listing(owner_cost_monthly=value(None)),S,R)
        self.assertIsNone(c['cash'])
        text,_=market.render(pool([listing(owner_cost_monthly=value(None))]),S,R,(48,7.85),NOW.isoformat(),True)
        self.assertIn('Monthly',text.replace('monthly','Monthly'))
        self.assertIn('Missing data: rent, financing or owner costs',text)
        self.assertNotIn(' + R',text)

    def test_effective_or_old_rates_do_not_feed_calculations(self):
        effective=copy.deepcopy(R)
        effective['rates'][0]['rate_type']='effective'
        sources={x['source_url'] for x in R['rates']}
        self.assertFalse(market.validate_rates(effective,sources,NOW)['rates'])
        old=copy.deepcopy(R);old['rates'][0]['date']='2026-09-01'
        self.assertFalse(market.validate_rates(old,sources,NOW)['rates'])
        duplicate=copy.deepcopy(R);duplicate['rates'][1]['source_url']='https://www.interhyp.de/other'
        self.assertFalse(market.validate_rates(duplicate,{x['source_url'] for x in duplicate['rates']},NOW)['rates'])

    def test_only_retrieved_and_opened_listings(self):
        sources={SOURCE,GEO,TAX}
        self.assertEqual(len(market.validate_pool(pool(),sources,{SOURCE})['listings']),1)
        self.assertFalse(market.validate_pool(pool(),sources,set())['listings'])
        p=pool();p['listings'][0]['url']='https://fake.de/1'
        self.assertFalse(market.validate_pool(p,sources,{SOURCE})['listings'])

    def test_estimate_requires_source_and_basis(self):
        x=listing(owner_cost_monthly=value(90,'estimate'))
        p=market.validate_pool(pool([x]),{SOURCE,GEO,TAX},{SOURCE})
        text,_=market.render(p,S,R,(48,7.85),NOW.isoformat(),True)
        self.assertIn('Estimate basis: Comparable local buildings',text)
        x['owner_cost_monthly']['basis']=''
        kept=market.validate_pool(pool([x]),{SOURCE,GEO,TAX},{SOURCE})['listings']
        self.assertEqual(len(kept),1)
        self.assertIsNone(kept[0]['owner_cost_monthly']['value'])

    def test_cache_key_uses_discovery_scope_but_not_language(self):
        changed={**S,'max_price_eur':100000,'equity_eur':10000,'language':'de'}
        self.assertNotEqual(market.cache_key('pool',S),market.cache_key('pool',changed))
        self.assertEqual(market.cache_key('pool',S),market.cache_key('pool',{**S,'language':'fa'}))
        self.assertEqual(market.cache_key('rates',S),market.cache_key('rates',changed))
        self.assertNotEqual(market.cache_key('rates',S),market.cache_key('rates',{**S,'fixed_rate_years':15}))

    def test_nearby_cache_requires_full_coverage(self):
        r=row();r['payload']['places'].append({'name':'Nearby','lat':48.02,'lon':7.85,'source_url':GEO})
        s={**S,'location':'Nearby'}
        self.assertIsNotNone(market.choose_pool([r],s,NOW)[0])
        r['radius_km']=100
        self.assertIsNone(market.choose_pool([r],s,NOW)[0])
        r['radius_km']=110;r['payload']['places'][1]['lat']=48.06
        self.assertIsNone(market.choose_pool([r],s,NOW)[0])
        self.assertIsNone(market.choose_pool([row()],{**S,'location':'Unknown'},NOW)[0])

    def test_large_radius_combines_small_and_large_saved_pools(self):
        small=row();small['payload']['listings']=[listing(url=SOURCE+str(i)) for i in range(4)]
        large=row();large['radius_km']=155;large['payload']['listings']=[listing(url=SOURCE+'4')]
        combined,center=market.choose_pool([large,small],{**S,'radius_km':150},NOW)
        self.assertEqual(len(combined['payload']['listings']),5)
        text,urls=market.render(combined['payload'],{**S,'radius_km':150},R,center,NOW.isoformat(),True)
        self.assertEqual(len(urls),5)
        self.assertEqual(len(large['payload']['listings']),1)

    def test_combining_pools_deduplicates_and_ignores_expired_or_distant(self):
        large=row();large['radius_km']=155
        duplicate=row()
        expired=row();expired['expires_at']=(NOW-timedelta(days=1)).isoformat();expired['payload']['listings']=[listing(url=SOURCE+'expired')]
        distant=row();distant['payload']['center']['lat']=50;distant['payload']['listings']=[listing(url=SOURCE+'distant')]
        combined,_=market.choose_pool([large,duplicate,expired,distant],{**S,'radius_km':150},NOW)
        self.assertEqual(len(combined['payload']['listings']),1)

    def test_all_large_pool_matches_survive_validation_and_telegram_splitting(self):
        items=[listing(url=SOURCE+str(i),title='Apartment '+str(i)) for i in range(40)]
        allowed={GEO,TAX,*[x['url'] for x in items]}
        validated=market.validate_pool(pool(items),allowed,{x['url'] for x in items})
        self.assertEqual(len(validated['listings']),40)
        text,urls=market.render(validated,S,R,(48,7.85),NOW.isoformat(),True)
        self.assertEqual(set(urls),{x['url'] for x in items})
        parts=list(agent.chunks(text))
        self.assertGreater(len(parts),1)
        self.assertEqual(''.join(parts),text)
        self.assertTrue(all(len(x.encode('utf-16-le'))//2<=3900 for x in parts))

    def test_persian_report_localised_without_altering_financial_values(self):
        text,urls=market.render(pool(),{**S,'language':'fa'},R,(48,7.85),NOW.isoformat(),True)
        self.assertIn('وام مورد نیاز برآوردی',text)
        self.assertIn('€165,855',text)
        self.assertIn('نرخ ثابت 10 ساله',text)
        self.assertIn('مشاوره مالی',text)
        self.assertNotIn('Estimated loan needed',text)
        self.assertEqual(urls,[SOURCE])

    def test_admin_refresh_bypasses_reports_and_appends_new_listing(self):
        old=row();db=collection_database(old);client=fake_collection_api([SOURCE+'new'])
        meter={'pending':False,'cost':0,'calls':[]}
        with patch('research.datetime',wraps=datetime) as dt,patch('openai.OpenAI',return_value=client):
            dt.now.return_value=NOW
            report,urls,hit=research.analyse(db,{'id':'job','settings':S,'user_id':123,'force_refresh':True,'shared_reports_enabled':True},meter)
        self.assertEqual(set(urls),{SOURCE,SOURCE+'new'})
        self.assertEqual(client.responses.create.call_count,2)
        self.assertNotIn('bot_shared_get',[c.args[0] for c in db.rpc.call_args_list])
        saved=[c.args[2] for c in db.request.call_args_list if c.args[0]=='POST' and c.args[1]=='bot_market_cache'][0]
        self.assertEqual(saved['expires_at'],old['expires_at'])

    def test_missing_inputs_show_missing_not_zero_in_dependent_results(self):
        s={**S,'equity_eur':200000}
        text,urls=market.render(pool([listing(broker_pct=None,rent_monthly=value(None))]),s,R,(48,7.85),NOW.isoformat(),True)
        self.assertIn('🏦 Estimated loan needed: Missing data',text)
        self.assertIn('💳 Estimated mortgage payment: Missing data',text)
        self.assertIn('💵 Cold rent: Missing data',text)
        self.assertIn('Not rated: incomplete data',text)
        self.assertNotIn('€0',text)
        self.assertEqual(urls,[SOURCE])
        complete,_=market.render(pool(),s,R,(48,7.85),NOW.isoformat(),True)
        self.assertIn('No loan needed with your stated equity',complete)
        self.assertIn('No mortgage payment needed',complete)

    def test_expired_cache_not_reused(self):
        r=row();r['expires_at']=(NOW-timedelta(seconds=1)).isoformat()
        self.assertIsNone(market.choose_pool([r],S,NOW)[0])

    def test_flex_options_never_change_settings_or_exclusions(self):
        settings=copy.deepcopy(S)
        p=pool([listing(price_eur=240000),listing(price_eur=400000,url=SOURCE+'2'),listing(tenure='Erbpacht',url=SOURCE+'3')])
        text,urls=market.render(p,S,R,(48,7.85),NOW.isoformat(),True)
        self.assertIn('If you are flexible',text)
        self.assertIn('Not financeable under your current loan cap',text)
        self.assertEqual(S,settings);self.assertEqual(urls,[SOURCE])

    def test_unknown_exclusion_status_is_provisional_not_discarded(self):
        items=[listing(tenure='',auction=None),listing(tenure='Erbpacht',url=SOURCE+'lease'),listing(auction=True,url=SOURCE+'auction')]
        text,urls=market.render(pool(items),S,R,(48,7.85),NOW.isoformat(),True)
        self.assertEqual(urls,[SOURCE])
        self.assertIn('Provisional candidate',text)
        self.assertIn('1 candidates within known limits',text)
        self.assertNotIn('No confirmed matches',text)
        self.assertIn('your exclusions still apply',text)

    def test_broad_search_retains_many_incomplete_but_verified_apartments(self):
        items=[listing(url=SOURCE+str(i),title='Home '+str(i),tenure='',auction=None,
                       rent_monthly=value(None),owner_cost_monthly=value(None),
                       energy_class='',year_built=None,lat=None,lon=None) for i in range(12)]
        text,urls=market.render(pool(items),S,R,(48,7.85),NOW.isoformat(),True)
        self.assertEqual(len(urls),12)
        self.assertIn('12 candidates within known limits',text)
        self.assertEqual(text.count('Provisional candidate'),12)
        self.assertNotIn('more matching properties in the saved pool',text)

    def test_location_fallback_never_substitutes_another_town(self):
        matches,_,blocks=market.screen(pool([listing(town='Unknown town',lat=None,lon=None)]),S,R,(48,7.85))
        self.assertEqual(len(matches),1)
        self.assertIsNone(matches[0]['distance'])
        self.assertIn('radius_km',matches[0]['checks_pending'])

    def test_leasehold_aliases_and_auctions_excluded(self):
        for tenure in ('Erbpacht','Erbbaurecht','Leasehold'):
            matches,_,_=market.screen(pool([listing(tenure=tenure)]),S,R,(48,7.85))
            self.assertEqual(matches,[])
        self.assertEqual(market.screen(pool([listing(auction=True)]),S,R,(48,7.85))[0],[])

    def test_hard_limits_not_relaxed_for_large_result_count(self):
        items=[listing(url=SOURCE+str(i),price_eur=500000) for i in range(12)]
        matches,flex,_=market.screen(pool(items),S,R,(48,7.85))
        self.assertEqual(matches,[])
        self.assertEqual(flex,[])

    def test_missing_bw_tax_does_not_hide_cached_apartments(self):
        broad={**S,'max_price_eur':1000000,'max_loan_eur':1200000,'equity_eur':200000,'min_size_m2':20}
        prices=[250000,165000,150000,299990,139000]
        items=[listing(url=SOURCE+str(i),price_eur=p,tax_pct=None,tenure='',auction=None) for i,p in enumerate(prices)]
        text,urls=market.render(pool(items),broad,R,(48,7.85),NOW.isoformat(),True)
        self.assertEqual(len(urls),5)
        self.assertIn('5 candidates within known limits',text)
        self.assertIn('official state rate',text)
        self.assertTrue(all(x['tax_pct'] is None for x in items),'Saved research is not mutated')

    def test_bw_fallback_never_applies_to_other_states(self):
        x=listing(state='Bayern',tax_pct=None)
        self.assertIsNone(market.with_verified_tax(x)['tax_pct'])
        text,_=market.render(pool([x]),S,R,(48,7.85),NOW.isoformat(),True)
        self.assertIn('Calculation unavailable — missing transfer tax',text)

    def test_missing_target_data_kept_and_explicitly_unchecked(self):
        settings={**S,'target_gross_yield_pct':5,'min_monthly_cashflow_eur':100}
        text,urls=market.render(pool([listing(rent_monthly=value(None),broker_pct=None)]),settings,R,(48,7.85),NOW.isoformat(),True)
        self.assertEqual(urls,[SOURCE])
        self.assertIn('not checked: loan limit, rental yield, monthly result',text)
        self.assertIn('Calculation unavailable — missing buyer commission',text)
        self.assertNotIn('Rent covers estimated costs.',text)

    def test_partial_loan_known_costs_already_over_cap_is_excluded(self):
        matches,flex,_=market.screen(pool([listing(price_eur=400000,broker_pct=None)]),S,R,(48,7.85))
        self.assertEqual(matches,[]);self.assertEqual(flex,[])

    def test_new_properties_first_seen_label_and_more_than_five(self):
        items=[listing(url=SOURCE+str(i),title='Apartment '+str(i)) for i in range(10)]
        s={**S,'_seen':{items[0]['url']}}
        text,urls=market.render(pool(items),s,R,(48,7.85),NOW.isoformat(),True)
        self.assertEqual(len(urls),10);self.assertIn(items[0]['url'],urls)
        self.assertEqual(urls[-1],items[0]['url'])
        self.assertNotIn('2 more matching',text)
        text,_=market.render(pool([items[0]]),s,R,(48,7.85),NOW.isoformat(),True)
        self.assertIn('Previously shown',text)

    def test_cache_hit_never_calls_openai_and_has_no_private_cache(self):
        db=Mock();db.request.side_effect=[[row('rates')],[row()],[],[]]
        meter={'pending':False,'cost':0,'calls':[]}
        with patch('research.datetime',wraps=datetime) as dt,patch('openai.OpenAI') as api:
            dt.now.return_value=NOW
            text,urls,hit=research.analyse(db,{'id':'job','settings':S,'user_id':123},meter)
        api.assert_not_called();db.rpc.assert_not_called()
        self.assertTrue(hit);self.assertEqual(meter['cost'],0)
        self.assertNotIn('API cost',text)

    def test_exhausted_budget_does_not_call_api(self):
        db=Mock();db.request.side_effect=[[],[],[]];db.rpc.return_value=False
        meter={'pending':False,'cost':0,'calls':[]}
        with patch('openai.OpenAI') as api:
            text,_,_=research.analyse(db,{'id':'job','settings':S,'user_id':123},meter)
        api.assert_not_called();self.assertIn('budget unavailable',text)

    def test_source_evidence_ignores_final_message(self):
        self.assertEqual(research.retrieved_sources({'output':[{'type':'message','url':SOURCE}]}),set())

    def test_second_call_timeout_retains_unknown_usage(self):
        db=Mock();db.rpc.side_effect=[{'id':'job','research_v2':True,'settings':{**S,'_guide_version':1},'user_id':123},None]
        db.request.side_effect=[[],[{'charged_usd':None,'reserved_usd':1}]]
        def partial(db,job,meter):
            meter.update(cost=.1,pending=True,calls=[{'model':'gpt-6.1-sol'}]);raise TimeoutError()
        with patch('research.analyse',side_effect=partial),patch.dict('os.environ',{'ADMIN_USER_ID':'123'}): agent.run_job(db,'job')
        args=db.rpc.call_args_list[1].args[1]
        self.assertEqual(args['p_status'],'uncertain');self.assertIsNone(args['p_cost'])

    def test_cached_success_settles_zero_and_admin_only_cost(self):
        db=Mock();db.rpc.side_effect=[{'id':'job','research_v2':True,'settings':{**S,'_guide_version':1},'user_id':456},None]
        db.request.side_effect=[[],None,[{'channel_enabled':False}],[{'charged_usd':0,'reserved_usd':0}]]
        with patch('research.analyse',return_value=('Saved report',[],True)),patch.dict('os.environ',{'ADMIN_USER_ID':'123'}): agent.run_job(db,'job')
        args=db.rpc.call_args_list[1].args[1]
        self.assertEqual(args['p_cost'],0);self.assertEqual(args['p_status'],'complete')
        db.report.assert_called_once_with(456,'Saved report','job','en');self.assertIn('Administrator only',db.admin.call_args.args[0])

    def test_fresh_research_uses_schema_no_calculation_tool_and_saves_public_data(self):
        import json
        urls=[SOURCE+str(i) for i in range(30)]
        db=collection_database();client=fake_collection_api(urls);meter={'pending':False,'cost':0,'calls':[]}
        with patch('research.datetime',wraps=datetime) as dt,patch('openai.OpenAI',return_value=client):
            dt.now.return_value=NOW
            report,shown,hit=research.analyse(db,{'id':'job','settings':S,'user_id':123},meter)
        self.assertEqual(client.responses.create.call_count,5)
        self.assertEqual(set(shown),set(urls[:20]));self.assertFalse(hit)
        calls=client.responses.create.call_args_list
        self.assertEqual(sum(c.kwargs['max_tool_calls'] for c in calls),25)
        self.assertEqual(calls[0].kwargs['text']['format']['name'],'links')
        batches=[json.loads(c.kwargs['input'].split('\n')[0])['individual_listing_urls'] for c in calls[1:]]
        self.assertEqual(len({x['url'] for b in batches for x in b}),20)
        saved=[c.args[2] for c in db.request.call_args_list if c.args[0]=='POST' and c.args[1]=='bot_market_cache'][-1]['payload']
        self.assertEqual(len(saved['pending_leads']),10)
        self.assertIn('10 discovered links await',report)
        for c in calls:self.assertNotIn('max_loan_eur',c.kwargs['input'])
        self.assertNotIn('equity_eur',json.dumps(saved));self.assertNotIn('user_id',json.dumps(saved))

    def test_same_settings_and_data_return_previous_report(self):
        import hashlib,json
        pr=market.choose_pool([row()],S,NOW)[0]
        signature=hashlib.sha256(json.dumps({'renderer_version':9,'settings':S,'pool':pr['payload'],'checked':pr['created_at'],'rates':R},sort_keys=True).encode()).hexdigest()
        db=Mock();db.request.side_effect=[[row('rates')],[pr],[{'report':'Previous report','usage':{'report_signature':signature}}]]
        meter={'pending':False,'cost':0,'calls':[]}
        with patch('research.datetime',wraps=datetime) as dt,patch('openai.OpenAI') as api:
            dt.now.return_value=NOW
            text,urls,hit=research.analyse(db,{'id':'job','settings':S,'user_id':123},meter)
        api.assert_not_called();self.assertEqual(text,'Previous report');self.assertEqual(urls,[])

    def test_shared_report_shortcuts_both_research_calls(self):
        db=Mock();db.rpc.return_value={'report':'Shared report','urls':[SOURCE]}
        meter={'pending':False,'cost':0,'calls':[]}
        with patch('openai.OpenAI') as api:
            text,urls,hit=research.analyse(db,{'id':'job','settings':S,'user_id':123,'shared_reports_enabled':True},meter)
        api.assert_not_called();db.request.assert_not_called();self.assertEqual(text,'Shared report')
        self.assertTrue(meter['shared_hit']);self.assertEqual(meter['cost'],0)

    def test_partial_json_retains_only_complete_objects(self):
        import json
        text='{"center":'+json.dumps(pool()['center'])+',"listings":['+json.dumps(listing())+',{"price_eur":123'
        kept=research.recover_complete_fields(text)
        self.assertEqual(len(kept['listings']),1)
        self.assertEqual(kept['listings'][0]['price_eur'],150000)
        self.assertEqual(research.recover_complete_fields('not JSON'),{})

    def test_bad_optional_benchmark_does_not_discard_real_property(self):
        x=listing(area_price_per_m2={'value':5000,'kind':'actual','basis':'','source_url':'https://fake.de/data'})
        kept=market.validate_pool(pool([x]),{SOURCE,GEO,TAX},{SOURCE})
        self.assertEqual(len(kept['listings']),1)
        self.assertIsNone(kept['listings'][0]['area_price_per_m2']['value'])

    def test_unverified_center_is_not_invented_or_cache_match(self):
        p=pool();p['center']['source_url']='https://fake.de/geo';p['places']=[]
        kept=market.validate_pool(p,{SOURCE,GEO,TAX},{SOURCE})
        self.assertIsNone(market.point(kept['center']))
        r=row();r['payload']=kept
        self.assertIsNone(market.choose_pool([r],S,NOW)[0])
        text,urls=research.partial_report(kept,S,NOW.isoformat())
        self.assertIn('no confirmed investment recommendations',text)
        self.assertEqual(urls,[]);self.assertIn(SOURCE,text)

    def test_unverified_listing_location_cannot_pass_radius(self):
        x=listing(town='Unverified municipality',lat=None,lon=None)
        kept=market.validate_pool(pool([x]),{SOURCE,GEO,TAX},{SOURCE})
        self.assertEqual(len(kept['listings']),1)
        candidate=market.screen(kept,S,R,(48,7.85))[0][0]
        self.assertIn('radius_km',candidate['checks_pending'])
        self.assertIsNone(candidate['distance'])

    def test_city_alias_reuses_verified_pool(self):
        r=row();r['payload']['center']['name']='Freiburg im Breisgau';r['payload']['places'][0]['name']='Freiburg im Breisgau'
        self.assertIsNotNone(market.choose_pool([r],S,NOW)[0])
        self.assertNotEqual(market.location_norm('Frankfurt am Main'),market.location_norm('Frankfurt (Oder)'))

    def test_bad_unrelated_source_does_not_crash_validation(self):
        self.assertEqual(len(market.validate_pool(pool(),{SOURCE,GEO,TAX,'not a URL'},{SOURCE})['listings']),1)

    def test_named_failure_and_evidence_are_saved_without_retry(self):
        db=Mock();db.rpc.side_effect=[{'id':'job','research_v2':True,'settings':{**S,'_guide_version':1},'user_id':123},None]
        db.request.side_effect=[[],[{'charged_usd':.1,'reserved_usd':0}]]
        def failed(db,job,meter):
            meter.update(cost=.1,stage='pool',checkpoints=[{'stage':'pool','extracted':{}}])
            raise research.ResearchDataError('PoolInvalidJSON')
        with patch('research.analyse',side_effect=failed),patch.dict('os.environ',{'ADMIN_USER_ID':'123'}): agent.run_job(db,'job')
        settlement=db.rpc.call_args_list[1].args[1]
        self.assertEqual(settlement['p_error'],'PoolInvalidJSON')
        self.assertEqual(settlement['p_usage']['stage'],'pool')
        self.assertTrue(settlement['p_usage']['checkpoints'])

    def test_output_limit_keeps_verified_listing_without_paid_retry(self):
        urls=[SOURCE+str(i) for i in range(10)]
        db=collection_database(row());client=fake_collection_api(urls,truncated=True);meter={'pending':False,'cost':0,'calls':[]}
        with patch('research.datetime',wraps=datetime) as dt,patch('openai.OpenAI',return_value=client):
            dt.now.return_value=NOW
            report,shown,_=research.analyse(db,{'id':'job','settings':S,'user_id':123,'force_refresh':True},meter)
        self.assertEqual(client.responses.create.call_count,6)
        self.assertEqual(len(shown),6)
        self.assertIn('Partial research',report);self.assertIn('PoolOutputLimitPartial',meter['warnings'])
        saved=[c.args[2] for c in db.request.call_args_list if c.args[0]=='POST'][-1]['payload']
        self.assertEqual(len(saved['pending_leads']),5)

    def test_batch_towns_and_dedup_preserve_every_property(self):
        import json
        p=pool([listing(url=SOURCE+'?utm_source=a')])
        p['places'] += [{'name':'Nearby','lat':48.1,'lon':7.85,'source_url':GEO},
                        {'name':'Far away','lat':53,'lon':10,'source_url':GEO}]
        merged=research.merge_listing_batches(p,pool([listing(url=SOURCE),listing(url=SOURCE+'new')]))
        self.assertEqual(len(merged['listings']),2)
        text,urls=market.render(pool([listing(url=SOURCE+str(i)) for i in range(45)]),{**S,'max_price_eur':1000000,'max_loan_eur':1200000},R,(48,7.85),NOW.isoformat(),False)
        self.assertEqual(len(urls),45)

    def test_expansion_cost_guard_stops_extra_calls(self):
        db=collection_database(row());client=fake_collection_api([SOURCE+'new'],expensive=True);meter={'pending':False,'cost':0,'calls':[]}
        with patch('research.datetime',wraps=datetime) as dt,patch('openai.OpenAI',return_value=client):
            dt.now.return_value=NOW
            report,shown,_=research.analyse(db,{'id':'job','settings':S,'user_id':123,'force_refresh':True},meter)
        self.assertEqual(client.responses.create.call_count,1)
        self.assertEqual(shown,[SOURCE]);self.assertIn('ExpansionStoppedAtCostGuard',meter['warnings'])
        self.assertIn('1 discovered links await',report)

    def test_compact_discovery_does_not_fill_missing_money_with_zero(self):
        compact={k:v for k,v in listing().items() if k in research.COMPACT_FIELDS}
        data=research.expand_discovery({'listings':[compact]})
        self.assertIsNone(data['listings'][0]['area_price_per_m2']['value'])
        self.assertIsNone(data['listings'][0]['lat'])
        self.assertEqual(data['listings'][0]['rent_monthly'],compact['rent_monthly'])
        fields=research.DISCOVERY_SCHEMA['properties']['listings']['items']['properties']
        self.assertNotIn('area_price_per_m2',fields);self.assertNotIn('lat',fields)
        self.assertIn('rent_monthly',fields);self.assertIn('broker_pct',fields)

    def test_refresh_reuses_verified_center_when_new_batch_lacks_coordinates(self):
        db=collection_database(row());client=fake_collection_api([SOURCE+'new'],no_center=True);meter={'pending':False,'cost':0,'calls':[]}
        with patch('research.datetime',wraps=datetime) as dt,patch('openai.OpenAI',return_value=client):
            dt.now.return_value=NOW
            report,shown,_=research.analyse(db,{'id':'job','settings':S,'user_id':123,'force_refresh':True},meter)
        self.assertEqual(client.responses.create.call_count,2)
        self.assertNotIn('SearchCenterUnverified',meter.get('warnings',[]))
        self.assertEqual(set(shown),{SOURCE,SOURCE+'new'})

    def test_discovery_rejects_invented_links_and_category_pages(self):
        category='https://example.de/suche/apartments'
        leads=[{'url':SOURCE+'?utm_source=x','title':'A','town':'Freiburg'},
               {'url':SOURCE,'title':'Duplicate','town':'Freiburg'},
               {'url':'https://invented.de/listing','title':'Fake','town':'Freiburg'},
               {'url':category,'title':'Category','town':'Freiburg'}]
        kept=research.validate_leads({'leads':leads},{SOURCE,category})
        self.assertEqual([x['url'] for x in kept],[SOURCE])

    def test_saved_queue_drains_without_new_discovery(self):
        old=row();old['payload']['pending_leads']=[{'url':SOURCE+str(i),'town':'Freiburg','title':'A'} for i in range(30)]
        db=collection_database(old);client=fake_collection_api([]);meter={'pending':False,'cost':0,'calls':[]}
        with patch('research.datetime',wraps=datetime) as dt,patch('openai.OpenAI',return_value=client):
            dt.now.return_value=NOW
            report,shown,_=research.analyse(db,{'id':'job','settings':S,'user_id':123,'force_refresh':True},meter)
        self.assertEqual(client.responses.create.call_count,5)
        self.assertTrue(all(c.kwargs['text']['format']['name']=='pool' for c in client.responses.create.call_args_list))
        self.assertEqual(len(shown),26)
        self.assertIn('5 discovered links await',report)

    def test_narrower_pool_cannot_satisfy_broader_search(self):
        narrow=row();narrow['payload']['search_scope']={'max_price_eur':100000,'min_size_m2':50}
        self.assertIsNone(market.choose_pool([narrow],S,NOW)[0])
        self.assertIsNotNone(market.choose_pool([narrow],{**S,'max_price_eur':90000,'min_size_m2':55},NOW)[0])
        client=fake_collection_api([SOURCE+'new']);db=collection_database();meter={'pending':False,'cost':0,'calls':[]}
        with patch('research.datetime',wraps=datetime) as dt,patch('openai.OpenAI',return_value=client):
            dt.now.return_value=NOW
            research.analyse(db,{'id':'job','settings':S,'user_id':123},meter)
        import json
        task=json.loads(client.responses.create.call_args_list[0].kwargs['input'].split('\n')[0])
        self.assertEqual(task['numerical_search_limits'],market.search_scope(S))
        self.assertNotIn('target_new_links',task)

    def test_unknown_repayment_never_becomes_zero_payment(self):
        settings={**S,'repayment_pct':None}
        result=market.calculate(listing(),settings,R)
        self.assertIsNone(result['payment']);self.assertIsNone(result['cash'])
        report,_=market.render(pool(),settings,R,(48,7.85),NOW.isoformat(),False)
        self.assertIn('initial repayment assumption is not set',report)

    def test_tracking_url_deduplication(self):
        self.assertEqual(market.url(SOURCE+'?utm_source=test'),SOURCE)

if __name__=='__main__':unittest.main()

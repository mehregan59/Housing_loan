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
        self.assertIsNone(c['loan']); self.assertIsNone(c['cash'])
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
        self.assertIn('unknown: rent, financing or owner costs missing',text)
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

    def test_cache_key_does_not_include_finances_or_language(self):
        changed={**S,'max_price_eur':100000,'equity_eur':10000,'language':'de'}
        self.assertEqual(market.cache_key('pool',S),market.cache_key('pool',changed))
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

    def test_new_properties_first_seen_label_and_more_than_five(self):
        items=[listing(url=SOURCE+str(i),title='Apartment '+str(i)) for i in range(10)]
        s={**S,'_seen':{items[0]['url']}}
        text,urls=market.render(pool(items),s,R,(48,7.85),NOW.isoformat(),True)
        self.assertEqual(len(urls),8);self.assertNotIn(items[0]['url'],urls)
        self.assertIn('2 more matching',text)
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
        db=Mock();db.rpc.side_effect=[{'id':'job','research_v2':True,'settings':S,'user_id':123},None]
        db.request.side_effect=[[{'charged_usd':None,'reserved_usd':1}]]
        def partial(db,job,meter):
            meter.update(cost=.1,pending=True,calls=[{'model':'gpt-6.1-sol'}]);raise TimeoutError()
        with patch('research.analyse',side_effect=partial),patch.dict('os.environ',{'ADMIN_USER_ID':'123'}): agent.run_job(db,'job')
        args=db.rpc.call_args_list[1].args[1]
        self.assertEqual(args['p_status'],'uncertain');self.assertIsNone(args['p_cost'])

    def test_cached_success_settles_zero_and_admin_only_cost(self):
        db=Mock();db.rpc.side_effect=[{'id':'job','research_v2':True,'settings':S,'user_id':456},None]
        db.request.side_effect=[None,[{'channel_enabled':False}],[{'charged_usd':0,'reserved_usd':0}]]
        with patch('research.analyse',return_value=('Saved report',[],True)),patch.dict('os.environ',{'ADMIN_USER_ID':'123'}): agent.run_job(db,'job')
        args=db.rpc.call_args_list[1].args[1]
        self.assertEqual(args['p_cost'],0);self.assertEqual(args['p_status'],'complete')
        db.telegram.assert_called_once_with(456,'Saved report');self.assertIn('Administrator only',db.admin.call_args.args[0])

    def test_fresh_research_uses_schema_no_calculation_tool_and_saves_public_data(self):
        db=Mock()
        # Rates miss, pool miss, old URLs miss, rate save, pool save, prior report, seen.
        db.request.side_effect=lambda method,path,data=None: [] if method=='GET' else None
        db.rpc.return_value=True
        response=Mock()
        response.model_dump.side_effect=[
            {'status':'completed','usage':{'input_tokens':1000,'output_tokens':200},'output':[{'type':'web_search_call','action':{'type':'search','sources':[{'url':x['source_url']} for x in R['rates']]}}]},
            {'status':'completed','usage':{'input_tokens':2000,'output_tokens':600},'output':[{'type':'web_search_call','action':{'type':'open_page','url':SOURCE,'sources':[{'url':GEO},{'url':TAX}]}}]}]
        type(response).output_text=__import__('unittest').mock.PropertyMock(side_effect=[__import__('json').dumps(R),__import__('json').dumps(pool())])
        client=Mock();client.responses.create.return_value=response
        meter={'pending':False,'cost':0,'calls':[]}
        with patch('research.datetime',wraps=datetime) as dt,patch('openai.OpenAI',return_value=client):
            dt.now.return_value=NOW
            text,urls,hit=research.analyse(db,{'id':'job','settings':S,'user_id':123},meter)
        self.assertEqual(client.responses.create.call_count,2);self.assertFalse(hit)
        self.assertEqual(urls,[SOURCE]);self.assertGreater(meter['cost'],0);self.assertFalse(meter['pending'])
        for call in client.responses.create.call_args_list:
            self.assertEqual(call.kwargs['tools'],[{'type':'web_search','search_context_size':'low'}])
            self.assertNotIn('max_loan_eur',call.kwargs['input'])
        saved=[call.args[2] for call in db.request.call_args_list if call.args[0]=='POST']
        self.assertEqual(len(saved),2)
        self.assertNotIn('user_id',__import__('json').dumps(saved));self.assertNotIn('equity_eur',__import__('json').dumps(saved))

    def test_same_settings_and_data_return_previous_report(self):
        import hashlib,json
        pr=row()
        signature=hashlib.sha256(json.dumps({'settings':S,'pool':pr['payload'],'checked':pr['created_at'],'rates':R},sort_keys=True).encode()).hexdigest()
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
        x=listing(lat=None,lon=None)
        kept=market.validate_pool(pool([x]),{SOURCE,GEO,TAX},{SOURCE})
        self.assertEqual(len(kept['listings']),1)
        self.assertFalse(market.screen(kept,S,R,(48,7.85))[0])

    def test_city_alias_reuses_verified_pool(self):
        r=row();r['payload']['center']['name']='Freiburg im Breisgau';r['payload']['places'][0]['name']='Freiburg im Breisgau'
        self.assertIsNotNone(market.choose_pool([r],S,NOW)[0])
        self.assertNotEqual(market.location_norm('Frankfurt am Main'),market.location_norm('Frankfurt (Oder)'))

    def test_bad_unrelated_source_does_not_crash_validation(self):
        self.assertEqual(len(market.validate_pool(pool(),{SOURCE,GEO,TAX,'not a URL'},{SOURCE})['listings']),1)

    def test_named_failure_and_evidence_are_saved_without_retry(self):
        db=Mock();db.rpc.side_effect=[{'id':'job','research_v2':True,'settings':S,'user_id':123},None]
        db.request.side_effect=[[{'charged_usd':.1,'reserved_usd':0}]]
        def failed(db,job,meter):
            meter.update(cost=.1,stage='pool',checkpoints=[{'stage':'pool','extracted':{}}])
            raise research.ResearchDataError('PoolInvalidJSON')
        with patch('research.analyse',side_effect=failed),patch.dict('os.environ',{'ADMIN_USER_ID':'123'}): agent.run_job(db,'job')
        settlement=db.rpc.call_args_list[1].args[1]
        self.assertEqual(settlement['p_error'],'PoolInvalidJSON')
        self.assertEqual(settlement['p_usage']['stage'],'pool')
        self.assertTrue(settlement['p_usage']['checkpoints'])

    def test_output_limit_keeps_verified_listing_without_paid_retry(self):
        import json
        db=Mock();db.rpc.return_value=True
        def database(method,path,data=None):
            if method=='GET' and path.startswith('bot_market_cache?cache_key') and 'rates%3A' in path: return [row('rates')]
            return [] if method=='GET' else None
        db.request.side_effect=database
        response=Mock()
        response.output_text='{"center":'+json.dumps(pool()['center'])+',"places":[],"listings":['+json.dumps(listing())+',{"url":"https://unfinished'
        response.model_dump.return_value={'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'},'usage':{'input_tokens':2000,'output_tokens':14000},'output':[{'type':'web_search_call','status':'completed','action':{'type':'open_page','url':SOURCE,'sources':[{'url':GEO},{'url':TAX}]}}]}
        client=Mock();client.responses.create.return_value=response
        meter={'pending':False,'cost':0,'calls':[]}
        with patch('research.datetime',wraps=datetime) as dt,patch('openai.OpenAI',return_value=client):
            dt.now.return_value=NOW
            report,urls,_=research.analyse(db,{'id':'job','settings':S,'user_id':123},meter)
        self.assertEqual(client.responses.create.call_count,1)
        self.assertEqual(urls,[SOURCE]);self.assertIn('Partial research',report)
        self.assertEqual(meter['calls'][0]['incomplete_reason'],'max_output_tokens')
        self.assertTrue(meter['checkpoints']);self.assertFalse(meter['pending'])
        self.assertTrue(any(c.args[0]=='PATCH' and c.args[1]=='bot_jobs?id=eq.job' for c in db.request.call_args_list))

    def test_tracking_url_deduplication(self):
        self.assertEqual(market.url(SOURCE+'?utm_source=test'),SOURCE)

if __name__=='__main__':unittest.main()

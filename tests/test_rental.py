import unittest
from rental import validate_listings,total_rent,matching,render
from report_pages import split_report,page

class RentalTests(unittest.TestCase):
    def item(self,**extra):
        return {'url':'https://example.org/rent/1','title':'Apartment','town':'Freiburg','country':'Deutschland','property_type':'apartment','warm_rent_eur':900,'cold_rent_eur':750,'charges_eur':150,'charges_complete':True,'size_m2':45,'lat':None,'lon':None,**extra}
    def settings(self): return {'location':'Freiburg','radius_km':25,'max_rent_eur':1000}
    def test_total_is_numeric_and_never_zero_for_missing(self):
        x=self.item();values,rejected=validate_listings({'listings':[x]},[x['url']],[x['url']])
        self.assertEqual(total_rent(values[0])[0],900)
        self.assertEqual(rejected,0)
        self.assertIsNone(total_rent(self.item(warm_rent_eur=None,charges_eur=None))[0])
        self.assertEqual(total_rent(self.item(warm_rent_eur=None))[0],900)
        self.assertIsNone(total_rent(self.item(warm_rent_eur=None,charges_complete=False))[0])
    def test_sources_opened_apartment_and_country_required(self):
        x=self.item()
        self.assertEqual(validate_listings({'listings':[x]},[x['url']],[])[0],[])
        for field,value in [('property_type','room'),('country','France')]:
            self.assertEqual(validate_listings({'listings':[self.item(**{field:value})]},[x['url']],[x['url']])[0],[])
    def test_unknown_rent_distance_provisional_and_hard_limits(self):
        confirmed,provisional=matching([self.item(),self.item(warm_rent_eur=1001),self.item(warm_rent_eur=None,charges_complete=False),self.item(town='Lahr')],self.settings())
        self.assertEqual(len(confirmed),1);self.assertEqual(len(provisional),2)
        self.assertEqual(matching([self.item(warm_rent_eur=None,cold_rent_eur=1001)],self.settings()),([],[]))
    def test_all_matches_paginate_without_cap(self):
        items=[self.item(url=f'https://example.org/rent/{n}') for n in range(28)]
        text=render(items,self.settings(),'2026-10-05',{'new':28})
        view=split_report(text);self.assertEqual(len(view['cards']),28)
        last,entities=page(view,'j00000000-0000-0000-0000-000000000000',5)
        self.assertIn('Page 6/6',last);self.assertIn('Rent & search notes',last)
        self.assertNotIn('mortgage',text.lower())
    def test_sourced_coordinates_filter_radius(self):
        s={**self.settings(),'lat':48.0,'lon':7.85}
        self.assertEqual(matching([self.item(town='Berlin',lat=52.5,lon=13.4)],s),([],[]))
    def test_fresh_shared_cache_never_calls_openai(self):
        from datetime import datetime,timedelta,timezone
        from unittest.mock import Mock,patch
        from rental import analyse
        now=datetime.now(timezone.utc)
        db=Mock();db.request.return_value=[{'checked_at':now.isoformat(),'expires_at':(now+timedelta(days=7)).isoformat(),'payload':[self.item()],'center':{}}]
        meter={'cost':0,'calls':[],'pending':False}
        with patch('openai.OpenAI') as api:
            report,urls,hit=analyse(db,{'id':'test','settings':self.settings()},meter)
        self.assertTrue(hit);self.assertEqual(meter['cost'],0);api.assert_not_called();db.rpc.assert_not_called()
        self.assertEqual(urls,[self.item()['url']]);self.assertIn('1 within verified limits',report)
    def test_fresh_research_deduplicates_opens_sources_and_has_no_mortgage_tools(self):
        import json
        from unittest.mock import Mock,patch
        from rental import analyse
        x=self.item();response=Mock();response.output_text=json.dumps({'center':{'name':'Freiburg','lat':None,'lon':None,'source_url':''},'listings':[x]})
        response.model_dump.return_value={'status':'completed','usage':{'input_tokens':100,'output_tokens':100},'output':[{'type':'web_search_call','status':'completed','action':{'type':'open_page','url':x['url']}}]}
        client=Mock();client.responses.create.return_value=response
        db=Mock();db.request.return_value=[];db.rpc.return_value=True
        meter={'cost':0,'calls':[],'pending':False}
        with patch('openai.OpenAI',return_value=client):
            report,urls,hit=analyse(db,{'id':'test','settings':self.settings()},meter)
        self.assertFalse(hit);self.assertEqual(len(urls),1);self.assertEqual(meter['collection_stats']['retained'],1)
        self.assertGreater(meter['cost'],0);self.assertEqual(client.responses.create.call_count,3)
        for call in client.responses.create.call_args_list:
            self.assertEqual(call.kwargs['tools'],[{'type':'web_search','search_context_size':'low'}])
            self.assertNotIn('mortgage rates',call.kwargs['input'])
        self.assertTrue(any(c.args[0]=='POST' and c.args[1]=='bot_rental_cache' for c in db.request.call_args_list))

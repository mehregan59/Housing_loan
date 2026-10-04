import unittest
from datetime import datetime, timezone
from unittest.mock import patch, Mock
import agent

class Tests(unittest.TestCase):
    def test_unverified_listing_rejected(self):
        with self.assertRaises(ValueError):
            agent.parse_report('Report\n---URLS---\nhttps://fake.example/1', {'https://real.example/1'})

    def test_appendix_removed_and_deduped(self):
        report, urls=agent.parse_report('Report\n---URLS---\nhttps://real.example/1\nhttps://real.example/1', {'https://real.example/1'})
        self.assertNotIn('---URLS---', report)
        self.assertEqual(urls,['https://real.example/1'])
        self.assertIn(agent.DISCLAIMER,report)

    def test_false_url_in_report_rejected(self):
        with self.assertRaises(ValueError):
            agent.parse_report('See https://fake.example/1\n---URLS---', {'https://real.example/1'})

    def test_no_listings_valid(self):
        self.assertEqual(agent.parse_report('No matches\n---URLS---',set())[1],[])

    def test_split_long_line_and_unicode(self):
        text='🏠'*8500
        parts=list(agent.chunks(text))
        self.assertEqual(''.join(parts),text)
        self.assertTrue(all(len(x.encode("utf-16-le"))//2<=3900 for x in parts))

    def test_split_report_preserves_paragraphs(self):
        text=('🏠 Apartment\n📍 Freiburg\n' + 'Details '*400 + '\n\n')*12
        parts=list(agent.chunks(text))
        self.assertGreater(len(parts),2)
        self.assertEqual(''.join(parts),text)
        self.assertTrue(all(len(x.encode('utf-16-le'))//2<=3900 for x in parts))

    def test_long_report_delivery_sends_all_parts_with_pacing(self):
        db=agent.Backend.__new__(agent.Backend)
        db.http=Mock()
        db.http.post.return_value=Mock(is_success=True,json=lambda:{'ok':True})
        text='🏠 Apartment details\n'*1500
        with patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'test'}),patch('agent.time.sleep') as pause:
            db.telegram(123,text)
        sent=[c.kwargs['json']['text'] for c in db.http.post.call_args_list]
        self.assertEqual(''.join(sent),text)
        self.assertEqual(pause.call_count,len(sent)-1)

    def test_sweep_filters_preserve_timestamp_and_do_not_trigger_paid_work(self):
        from urllib.parse import parse_qs,urlsplit
        db=Mock()
        db.request.side_effect=[[{'enabled':True}],[],[],[]]
        with patch('agent.run_job') as run:
            agent.sweep(db)
        path=db.request.call_args_list[1].args[1]
        timestamp=parse_qs(urlsplit('https://test/'+path).query)['started_at'][0][3:]
        self.assertEqual(datetime.fromisoformat(timestamp).utcoffset().total_seconds(),0)
        self.assertNotIn(' ',timestamp)
        run.assert_not_called();db.rpc.assert_not_called()

    def test_database_failure_reports_code_without_private_data(self):
        db=agent.Backend.__new__(agent.Backend);db.base='https://test/';db.headers={};db.http=Mock()
        db.http.request.return_value=Mock(is_success=False,status_code=400,json=lambda:{'code':'22007','message':'private message','details':'secret'})
        with self.assertRaises(agent.DatabaseFailure) as failure:
            db.request('GET','bot_jobs?private=secret')
        self.assertIn('HTTP 400; code 22007',str(failure.exception))
        self.assertNotIn('secret',str(failure.exception));self.assertNotIn('private',str(failure.exception))

    def test_summer_winter_schedule(self):
        user={'timezone':'Europe/Berlin','schedule_time':'08:00','schedule_day':0}
        self.assertEqual(agent.due_slot(user,datetime(2026,7,6,6,17,tzinfo=timezone.utc)),'2026-07-06')
        self.assertEqual(agent.due_slot(user,datetime(2026,12,7,7,17,tzinfo=timezone.utc)),'2026-12-07')
        self.assertIsNone(agent.due_slot(user,datetime(2026,12,7,6,17,tzinfo=timezone.utc)))

    def test_cost_includes_tools_and_cached_tokens(self):
        data={'usage':{'input_tokens':10000,'output_tokens':1000,'input_tokens_details':{'cached_tokens':2000}},
              'output':[{'type':'web_search_call'},{'type':'code_interpreter_call','id':'c','container_id':'same'},
                        {'type':'code_interpreter_call','id':'d','container_id':'same'}]}
        with patch.object(agent,'MODEL','gpt-6-astra'):
            cost, usage=agent.estimate_cost(data)
        self.assertAlmostEqual(cost,.1892)
        self.assertEqual(usage['containers'],1)

    def test_unknown_usage_never_zero(self):
        with self.assertRaises(ValueError): agent.estimate_cost({})

    def test_inactive_upgrade_never_calls_legacy_api(self):
        db=Mock()
        db.rpc.side_effect=[{'settings':{},'user_id':123,'reserved_usd':1},None]
        db.request.side_effect=[[],[{'charged_usd':None,'reserved_usd':1}]]
        client=Mock()
        client.responses.create.side_effect=TimeoutError('not logged')
        with patch('openai.OpenAI',return_value=client), patch.dict('os.environ',{'ADMIN_USER_ID':'123'}):
            agent.run_job(db,'test-job')
        settlement=db.rpc.call_args_list[1].args[1]
        self.assertEqual(settlement['p_status'],'failed')
        self.assertEqual(settlement['p_cost'],0)
        self.assertEqual(client.responses.create.call_count,0)

    def test_already_claimed_job_never_calls_api(self):
        db=Mock(); db.rpc.return_value=None
        with patch('openai.OpenAI') as api:
            agent.run_job(db,'existing-job')
        api.assert_not_called()

if __name__=='__main__': unittest.main()

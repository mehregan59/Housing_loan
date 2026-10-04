import json
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import urlsplit,parse_qs
from report_pages import split_report,page
import agent

CASES=json.loads((Path(__file__).parent/'fixtures/report_views.json').read_text())
SOURCE='j00000000-0000-4000-8000-000000000001'
class ReportPagesTests(unittest.TestCase):
    def test_every_apartment_is_in_index_with_text_links_and_exact_details(self):
        for case in CASES:
            view=split_report(case['report']);self.assertEqual(len(view['cards']),7)
            listings=[]
            for i in range(2):
                text,entities=page(view,SOURCE,i,case['language'])
                self.assertLess(len(text.encode('utf-16-le'))//2,3900)
                self.assertNotIn('Owner building fees',text)
                listings.extend(e for e in entities if e['url'].startswith('https://example.de/'))
                encoded=text.encode('utf-16-le')
                for entity in entities:
                    self.assertTrue(encoded[entity['offset']*2:(entity['offset']+entity['length'])*2].decode('utf-16-le'))
                    if entity['url'].startswith('https://t.me/'):
                        payload=parse_qs(urlsplit(entity['url']).query)['start'][0]
                        self.assertLessEqual(len(payload),64)
                self.assertRegex(text,r'📈[^\n]+ · ')
            self.assertEqual(len(listings),7)
            self.assertTrue(all(c['detail'] in case['report'] for c in view['cards']))

    def test_worker_delivers_summary_pages_and_text_links_without_api(self):
        db=agent.Backend.__new__(agent.Backend);db.telegram=Mock()
        with patch('agent.time.sleep'):
            db.report(123,CASES[0]['report'],SOURCE[1:],'en')
        self.assertEqual(db.telegram.call_count,2)
        links=db.telegram.call_args_list[0].kwargs['entities']
        self.assertTrue(any('prop_'+SOURCE in e['url'] for e in links))

    def test_legacy_or_no_property_report_is_not_discarded(self):
        view=split_report('No matches or legacy report')
        self.assertEqual(view['header'],'No matches or legacy report');self.assertEqual(view['cards'],[])
        db=agent.Backend.__new__(agent.Backend);db.telegram=Mock()
        db.report(123,view['header'],SOURCE[1:])
        db.telegram.assert_called_once_with(123,view['header'])

    def test_text_link_entities_survive_message_splitting_with_emojis(self):
        db=agent.Backend.__new__(agent.Backend);db.http=Mock()
        db.http.post.return_value=Mock(is_success=True,json=lambda:{'ok':True})
        text='🏠'*1949+'Details'
        entities=[{'type':'text_link','offset':3898,'length':7,'url':'https://example.de'}]
        with patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'test'}),patch('agent.time.sleep'):
            db.telegram(123,text,entities=entities)
        bodies=[c.kwargs['json'] for c in db.http.post.call_args_list]
        self.assertEqual(''.join(b['text'] for b in bodies),text)
        labels=[]
        for body in bodies:
            encoded=body['text'].encode('utf-16-le')
            for e in body.get('entities',[]): labels.append(encoded[e['offset']*2:(e['offset']+e['length'])*2].decode('utf-16-le'))
        self.assertEqual(''.join(labels),'Details')

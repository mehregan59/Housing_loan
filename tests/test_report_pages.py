import json
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from report_pages import split_report,page
import agent

CASES=json.loads((Path(__file__).parent/'fixtures/report_views.json').read_text())
SOURCE='j00000000-0000-4000-8000-000000000001'
class ReportPagesTests(unittest.TestCase):
    def test_every_apartment_is_in_index_and_keeps_exact_details(self):
        for case in CASES:
            view=split_report(case['report'])
            self.assertEqual(len(view['cards']),7)
            all_buttons=[]
            for i in range(2):
                text,keyboard=page(view,SOURCE,i,case['language'])
                self.assertLess(len(text.encode('utf-16-le'))//2,3900)
                all_buttons.extend(b for row in keyboard['inline_keyboard'] for b in row if 'url' in b)
                self.assertNotIn('Owner building fees',text)
            self.assertEqual(len(all_buttons),7)
            self.assertTrue(all(c['detail'] in case['report'] for c in view['cards']))
            self.assertTrue(all(len(b['callback_data'].encode())<=64 for i in range(2) for row in page(view,SOURCE,i,case['language'])[1]['inline_keyboard'] for b in row if 'callback_data' in b))

    def test_worker_delivers_summary_pages_and_buttons_without_api(self):
        db=agent.Backend.__new__(agent.Backend);db.telegram=Mock()
        with patch('agent.time.sleep'):
            db.report(123,CASES[0]['report'],SOURCE[1:],'en')
        self.assertEqual(db.telegram.call_count,2)
        self.assertIn('prop:'+SOURCE,db.telegram.call_args_list[0].args[2]['inline_keyboard'][0][0]['callback_data'])

    def test_legacy_or_no_property_report_is_not_discarded(self):
        view=split_report('No matches or legacy report')
        self.assertEqual(view['header'],'No matches or legacy report');self.assertEqual(view['cards'],[])
        db=agent.Backend.__new__(agent.Backend);db.telegram=Mock()
        db.report(123,view['header'],SOURCE[1:])
        db.telegram.assert_called_once_with(123,view['header'])

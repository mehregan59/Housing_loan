import os
import unittest
from unittest.mock import Mock,patch
from datetime import datetime,timezone
import agent

class WeeklyPilotTests(unittest.TestCase):
    def user(self,**extra):
        return {'user_id':42,'pilot_free':True,'approved':True,'accepted_at':'2026-10-05','weekly':True,'service':'investment','settings':{},'schedule_day':0,'schedule_time':'09:00','timezone':'Europe/Berlin',**extra}
    def test_only_approved_consenting_weekly_investment_pilots_qualify(self):
        self.assertTrue(agent.scheduled_pilot(self.user()))
        for key,value in [('approved',False),('accepted_at',None),('pilot_free',False),('weekly',False),('service','rental')]:
            self.assertFalse(agent.scheduled_pilot(self.user(**{key:value})))
    def test_pilot_scheduler_enqueues_without_guide_and_preserves_settings(self):
        db=Mock();u=self.user();db.request.side_effect=[[{'enabled':True}],[],[u],[]]
        with patch('agent.datetime',wraps=datetime) as clock,patch('agent.run_job') as run:
            clock.now.return_value=datetime(2026,10,12,7,5,tzinfo=timezone.utc)
            agent.sweep(db)
        db.rpc.assert_called_once_with('bot_enqueue',{'p_user':42,'p_key':'schedule:42:2026-10-12'})
        self.assertEqual(u['settings'],{});run.assert_not_called()
    def test_worker_allows_only_scheduled_pilot_without_marking_guide(self):
        for key,expected in [('schedule:42:2026-10-12',True),('telegram:123',False),('schedule:99:2026-10-12',False)]:
            db=Mock();job={'id':'job','user_id':42,'settings':{'location':'Freiburg'},'research_v2':True,'service':'investment'}
            db.rpc.return_value=job
            def request(method,path,data=None):
                return [self.user()] if path.startswith('bot_users') else [{'request_key':key}]
            db.request.side_effect=request
            with patch.dict(os.environ,{'ADMIN_USER_ID':'999'}),patch('research.analyse',return_value=('report',[],True)) as analyse,patch('agent.finish_job') as finish:
                agent.run_job(db,'job')
            self.assertEqual(analyse.called,expected)
            self.assertEqual(finish.call_args.args[3],'complete' if expected else 'failed')
            if not expected: self.assertEqual(finish.call_args.args[-1],'GuideRequired')
            self.assertNotIn('_guide_version',job['settings'])

import os
import unittest
from unittest.mock import Mock,patch
from notices import required_notices,reconcile_user

class NoticeTests(unittest.TestCase):
    def user(self,**extra): return {'user_id':42,'accepted_at':'2026-10-05','service':'investment','agreement_version_accepted':1,'settings':{},**extra}
    def test_guide_completion_and_agreement_versions_are_separate(self):
        c={'agreement_version':2,'agreement_text':'Changed terms'}
        self.assertEqual([(k,v) for k,v,_,_ in required_notices(self.user(),c)],[('guide',1),('agreement',2)])
        self.assertEqual([(k,v) for k,v,_,_ in required_notices(self.user(settings={'_guide_version':1}),c)],[('agreement',2)])
        self.assertEqual(required_notices(self.user(settings={'_guide_version':1},agreement_version_accepted=2),c),[])
    def test_single_message_pinned_and_not_duplicated_on_later_sweep(self):
        db=Mock();row={'user_id':42,'kind':'guide','version':1,'message_id':100,'pinned':True,'acknowledged_at':None}
        def request(method,path,data=None): return [row] if path.startswith('bot_notices') and method=='GET' else [self.user()] if path.startswith('bot_users') else []
        db.request.side_effect=request
        with patch('notices.telegram') as tg: reconcile_user(db,self.user(),{})
        tg.assert_called_once_with(db,'pinChatMessage',{'chat_id':42,'message_id':100,'disable_notification':True})
        self.assertFalse(any(c.args[0]=='POST' for c in db.request.call_args_list))
    def test_completion_unpins_only_stored_notice(self):
        db=Mock();db.request.return_value=[{'kind':'guide','version':1,'message_id':100,'pinned':True,'acknowledged_at':None}]
        with patch('notices.telegram') as tg: reconcile_user(db,self.user(settings={'_guide_version':1}),{})
        tg.assert_called_once_with(db,'unpinChatMessage',{'chat_id':42,'message_id':100})
        self.assertIsNotNone(db.request.call_args.args[2]['acknowledged_at'])
    def test_new_message_saved_before_pin(self):
        db=Mock();db.request.side_effect=[[],None,None,[self.user()],None]
        with patch('notices.telegram',return_value={'message_id':100}) as tg: reconcile_user(db,self.user(),{})
        self.assertEqual(tg.call_args_list[0].args[1],'sendMessage')
        self.assertEqual(tg.call_args_list[1].args[1],'pinChatMessage')
        self.assertEqual(db.request.call_args_list[2].args[2],{'message_id':100})

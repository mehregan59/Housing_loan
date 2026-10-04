import os
import unittest
from unittest.mock import Mock,patch
import payments

class PaymentTests(unittest.TestCase):
    def test_refund_never_calls_ai_and_marks_only_confirmed_success(self):
        order={'id':'order','user_id':77,'telegram_charge_id':'charge'}
        db=Mock()
        db.request.side_effect=lambda method,path,data=None: [{'payments_enabled':False}] if path.startswith('bot_control') else [order] if 'state=eq.refund_pending' in path and method=='GET' else []
        db.http.post.return_value.is_success=True
        db.http.post.return_value.json.return_value={'ok':True}
        with patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'test'}),patch('openai.OpenAI') as api:
            payments.process_refunds(db)
        api.assert_not_called()
        db.rpc.assert_called_once_with('bot_order_refunded',{'p_user':77,'p_charge':'charge'})
        self.assertIn('refundStarPayment',db.http.post.call_args.args[0])

    def test_ambiguous_refund_stays_pending_and_alerts_admin(self):
        order={'id':'order','user_id':77,'telegram_charge_id':'charge'}
        db=Mock()
        db.request.side_effect=lambda method,path,data=None: [{'payments_enabled':True}] if path.startswith('bot_control') else [order] if method=='GET' and 'state=eq.refund_pending' in path else []
        db.http.post.side_effect=TimeoutError()
        with patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'test'}):payments.process_refunds(db)
        db.rpc.assert_not_called()
        self.assertIn('needs review',db.admin.call_args.args[0])
        self.assertEqual(db.request.call_args.args[2],{'refund_error':'RefundNeedsReview'})

    def test_terminal_failure_reconciles_interrupted_payment_settlement(self):
        db=Mock()
        db.request.side_effect=[[{'payments_enabled':True}],[{'job_id':'job','bot_jobs':{'status':'uncertain'}}],[]]
        payments.process_refunds(db)
        db.rpc.assert_called_once_with('bot_order_settle',{'p_job':'job','p_delivered':False})

"""Payment fulfillment/refunds only. Never starts an OpenAI call."""
import os
from datetime import datetime,timedelta,timezone


def settle_report(db,job_id,delivered):
    db.rpc('bot_order_settle',{'p_job':job_id,'p_delivered':bool(delivered)})


def process_refunds(db):
    control=db.request('GET','bot_control?id=eq.1')[0]
    if 'payments_enabled' not in control: return
    # Recover a crash between terminal job settlement and payment settlement.
    for order in db.request('GET','bot_orders?product=eq.report&state=eq.paid&job_id=not.is.null&select=id,job_id,bot_jobs(status,delivered,finished_at,created_at)'):
        job=order.get('bot_jobs') or {}
        if job.get('status')=='queued' and job.get('created_at') and datetime.fromisoformat(job['created_at'].replace('Z','+00:00'))<datetime.now(timezone.utc)-timedelta(hours=24):
            db.rpc('bot_order_cancel_overdue',{'p_id':order['id']})
        elif job.get('status') in ('failed','uncertain'):
            settle_report(db,order['job_id'],False)
        elif job.get('status')=='complete':
            if job.get('delivered'):
                settle_report(db,order['job_id'],True)
            elif job.get('finished_at') and datetime.fromisoformat(job['finished_at'].replace('Z','+00:00'))<datetime.now(timezone.utc)-timedelta(minutes=15):
                settle_report(db,order['job_id'],False)
    for order in db.request('GET','bot_orders?state=eq.refund_pending&telegram_charge_id=not.is.null&order=paid_at&limit=50'):
        try:
            r=db.http.post('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/refundStarPayment',
                json={'user_id':order['user_id'],'telegram_payment_charge_id':order['telegram_charge_id']})
            if not r.is_success or not r.json().get('ok'): raise RuntimeError('Refund API failed')
            db.rpc('bot_order_refunded',{'p_user':order['user_id'],'p_charge':order['telegram_charge_id']})
            try: db.telegram(order['user_id'],'⭐ Your purchase has been fully refunded in Telegram Stars. Reference: '+order['id'])
            except Exception: pass
        except Exception:
            # Keep durable refund pending; do not pretend an ambiguous result succeeded.
            if order.get('refund_error')!='RefundNeedsReview':
                db.request('PATCH','bot_orders?id=eq.'+order['id']+'&state=eq.refund_pending',{'refund_error':'RefundNeedsReview'})
                db.admin('⚠️ Stars refund needs review. Order '+order['id']+'. Check Telegram payment transactions; no paid analysis retry.')

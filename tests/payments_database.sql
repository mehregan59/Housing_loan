-- No real invoices, Telegram calls or API spending.
insert into bot_users(user_id,approved,accepted_at,settings) values(999990010,true,now(),'{"_guide_version":1}');
\ir ../supabase/migrations/007_payments.sql
begin;
do $$
declare o jsonb; paid jsonb; job uuid; pass_id uuid; invoice_id uuid; result jsonb;
begin
 assert (select pilot_free from bot_users where user_id=999990010),'Existing pilot must be exempt';
 assert not (select payments_enabled from bot_control where id=1),'Checkout must default OFF';
 update bot_control set enabled=true,research_v2=true,payments_enabled=true,payment_terms_text='Test purchase terms',report_price_stars=50,weekly_price_stars=200,pilot_locked=false;
 insert into bot_users(user_id,approved,accepted_at,settings,payment_terms_version)
 values(999990011,true,now(),'{"_guide_version":1,"location":"Freiburg","country":"Germany","equity_eur":10000}',1);
 assert not (select pilot_free from bot_users where user_id=999990011),'New user must not inherit exemption';
 result=bot_enqueue(999990011,'telegram:unpaid');
 assert result->>'error'='payment_required','Unpaid manual run must not enqueue';
 o=bot_order_create(999990011,'report');invoice_id=(o->>'order_id')::uuid;
 assert (o->>'amount_stars')::int=50;
 result=bot_order_checkout(999990011,invoice_id,49,'XTR');
 assert result ? 'error','Wrong price rejected';
 result=bot_order_checkout(999990011,invoice_id,50,'EUR');
 assert result ? 'error','Wrong currency rejected';
 result=bot_order_checkout(999990011,invoice_id,50,'XTR','checkout-one');
 assert result->>'ok'='true';
 result=bot_order_checkout(999990011,invoice_id,50,'XTR','checkout-two');
 assert result ? 'error','Second concurrent checkout refused';
 result=bot_order_checkout(999990011,invoice_id,50,'XTR','checkout-one');
 assert result->>'ok'='true','Exact checkout retry idempotent';
 paid=bot_order_paid(999990011,invoice_id,50,'XTR','test-report-charge');job=(paid->>'job_id')::uuid;
 assert job is not null,'Payment queues one report';
 result=bot_order_paid(999990011,invoice_id,50,'XTR','test-report-charge');
 assert result->>'duplicate'='true' and (result->>'job_id')::uuid=job,'Payment retries idempotent';
 assert (select count(*)=1 from bot_jobs where request_key='paid:'||invoice_id::text);
 result=bot_order_paid(999990011,invoice_id,50,'XTR','unexpected-second-charge');
 assert result->>'state'='refund_pending';
 assert (select state='refund_pending' from bot_orders where telegram_charge_id='unexpected-second-charge'),'Unexpected second charge retained for refund';
 update bot_users set settings=jsonb_set(settings,'{equity_eur}','50000') where user_id=999990011;
 result=bot_claim(job);
 assert result->'settings'->>'equity_eur'='10000','Invoice settings preserved';
 assert result->>'billing_kind'='report';
 perform bot_finish(job,'failed',0,null,'{}','TestFailure','[]');
 perform bot_order_settle(job,false);
 assert (select state='refund_pending' from bot_orders where id=invoice_id),'Failed report fully refundable';
 perform bot_order_refunded(999990011,'test-report-charge');
 perform bot_order_refunded(999990011,'test-report-charge');
 assert (select state='refunded' from bot_orders where id=invoice_id);

 o=bot_order_create(999990011,'weekly30');pass_id=(o->>'order_id')::uuid;
 result=bot_order_checkout(999990011,pass_id,200,'XTR');assert result->>'ok'='true';
 paid=bot_order_paid(999990011,pass_id,200,'XTR','test-weekly-charge');
 assert (select pass_ends_at-pass_starts_at=interval '30 days' from bot_orders where id=pass_id),'Full 30 days, no four-week ceiling';
 for i in 1..5 loop
  result=bot_enqueue(999990011,'schedule:999990011:test-'||i::text);job=(result->>'job_id')::uuid;
  assert job is not null,'Fifth weekly delivery must be allowed';
  perform bot_claim(job);perform bot_finish(job,'complete',0,'Saved report','{}',null,'[]');
  update bot_jobs set delivered=true where id=job;
 end loop;
 result=bot_enqueue(999990011,'telegram:manual-extra');
 assert result->>'error'='payment_required','Pass does not include unlimited manual reports';
 perform bot_order_refunded(999990011,'test-weekly-charge');
 result=bot_enqueue(999990011,'schedule:999990011:after-refund');
 assert result->>'error'='weekly_payment_required','Refund revokes pass';

 -- Cached shared data cannot be opened by a new unpaid customer.
 insert into bot_users(user_id,approved,accepted_at,settings) values(999990012,true,now(),'{"_guide_version":1,"location":"Freiburg"}');
 perform bot_shared_publish((select settings from bot_users where user_id=999990012),'Paid shared example','[]',now()+interval '1 day');
 assert bot_saved_report(999990012) is null,'Shared cache must not bypass checkout';
 assert bot_order_create(999990010,'report')->>'error'='pilot_free';
 assert not has_function_privilege('anon','bot_order_paid(bigint,uuid,integer,text,text)','EXECUTE');
 assert not has_table_privilege('authenticated','bot_orders','SELECT');
end $$;
rollback;

-- Apply after 006. Existing registered users are grandfathered; checkout stays OFF.
begin;
alter table bot_control add column payment_terms_text text;
alter table bot_control add column report_target_eur numeric not null default 0.99;
alter table bot_control add column weekly_target_eur numeric not null default 3.96;
alter table bot_control add column payments_enabled boolean not null default false;
alter table bot_control add column report_price_stars integer check(report_price_stars between 1 and 100000);
alter table bot_control add column weekly_price_stars integer check(weekly_price_stars between 1 and 100000);
alter table bot_users add column pilot_free boolean not null default false;
alter table bot_users add column payment_terms_version integer not null default 0;
update bot_users set pilot_free=true;
alter table bot_jobs add column billing_kind text check(billing_kind in ('report','weekly'));
alter table bot_jobs add column billing_settings_key text;
create table bot_orders (
 id uuid primary key default gen_random_uuid(), user_id bigint not null references bot_users,
 product text not null check(product in ('report','weekly30')), amount_stars integer not null check(amount_stars>0),
 state text not null default 'created' check(state in ('created','checkout','paid','delivered','refund_pending','refunded')),
 settings_key text not null, settings jsonb,
 checkout_query_id text, telegram_charge_id text unique, job_id uuid unique references bot_jobs,
 created_at timestamptz not null default now(), invoice_expires_at timestamptz not null default now()+interval '30 minutes',
 paid_at timestamptz, delivered_at timestamptz, refunded_at timestamptz,
 pass_starts_at timestamptz, pass_ends_at timestamptz, refund_error text
);
create index bot_orders_refunds on bot_orders(state) where state='refund_pending';
alter table bot_orders enable row level security;
revoke all on bot_orders from public,anon,authenticated;
grant all on bot_orders to service_role;

create function bot_payment_exempt(p_user bigint) returns boolean
language sql stable security definer set search_path=public,pg_temp as $$
 select coalesce((select u.pilot_free or u.user_id=c.admin_user_id from bot_users u cross join bot_control c where c.id=1 and u.user_id=p_user),false)
$$;

create function bot_order_create(p_user bigint,p_product text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare u bot_users; c bot_control; o bot_orders; total numeric;
begin
 select * into c from bot_control where id=1 for update;
 select * into u from bot_users where user_id=p_user for update;
 if not found or not u.approved or u.accepted_at is null or u.settings->>'_guide_version' is distinct from '1' then return jsonb_build_object('error','complete_setup_first'); end if;
 if not c.payments_enabled or nullif(trim(c.payment_terms_text),'') is null or not c.enabled or not c.research_v2 then return jsonb_build_object('error','payments_unavailable'); end if;
 if bot_payment_exempt(p_user) then return jsonb_build_object('error','pilot_free'); end if;
 if u.payment_terms_version<>1 then return jsonb_build_object('error','accept_payment_terms'); end if;
 if (p_product='report' and c.report_price_stars is null) or (p_product='weekly30' and c.weekly_price_stars is null) then return jsonb_build_object('error','stars_price_not_configured'); end if;
 if p_product not in ('report','weekly30') then return jsonb_build_object('error','invalid_product'); end if;
 if exists(select 1 from bot_jobs where user_id=p_user and status in ('queued','running')) then return jsonb_build_object('error','already_running'); end if;
 if exists(select 1 from bot_jobs where status='uncertain') then return jsonb_build_object('error','usage_needs_review'); end if;
 select coalesce(sum(coalesce(charged_usd,reserved_usd)),0) into total from bot_jobs
 where coalesce(started_at,created_at)>=greatest(c.budget_period_started_at,date_trunc('month',now() at time zone 'UTC') at time zone 'UTC') or status in ('queued','running','uncertain');
 if total+c.run_reserve_usd>c.monthly_budget_usd then return jsonb_build_object('error','research_budget_unavailable'); end if;
 if exists(select 1 from bot_orders where user_id=p_user and product='report' and state='paid' and job_id is null) then return jsonb_build_object('error','paid_report_waiting'); end if;
 select * into o from bot_orders where user_id=p_user and product=p_product and state='created' and invoice_expires_at>now() and settings_key=bot_settings_key(u.settings) order by created_at desc limit 1;
 if not found then
  insert into bot_orders(user_id,product,amount_stars,settings_key,settings)
  values(p_user,p_product,case when p_product='report' then c.report_price_stars else c.weekly_price_stars end,bot_settings_key(u.settings),u.settings) returning * into o;
 end if;
 return jsonb_build_object('order_id',o.id,'product',o.product,'amount_stars',o.amount_stars);
end $$;

create function bot_order_checkout(p_user bigint,p_id uuid,p_amount integer,p_currency text,p_checkout text default null) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare c bot_control; u bot_users; o bot_orders; total numeric;
begin
 select * into c from bot_control where id=1 for update;
 select * into u from bot_users where user_id=p_user for update;
 select * into o from bot_orders where id=p_id for update;
 if not found or o.user_id<>p_user or o.state not in ('created','checkout') or o.invoice_expires_at<=now() or o.amount_stars<>p_amount or p_currency<>'XTR' then return jsonb_build_object('error','invalid_or_expired_invoice'); end if;
 if not c.payments_enabled or nullif(trim(c.payment_terms_text),'') is null or not c.enabled or not c.research_v2 or not u.approved or u.accepted_at is null or u.payment_terms_version<>1 or bot_payment_exempt(p_user) or u.settings->>'_guide_version' is distinct from '1' then return jsonb_build_object('error','checkout_unavailable'); end if;
 if o.settings_key<>bot_settings_key(u.settings) then return jsonb_build_object('error','settings_changed_request_new_invoice'); end if;
 if exists(select 1 from bot_jobs where user_id=p_user and status in ('queued','running')) or exists(select 1 from bot_jobs where status='uncertain') then return jsonb_build_object('error','analysis_unavailable'); end if;
 select coalesce(sum(coalesce(charged_usd,reserved_usd)),0) into total from bot_jobs
 where coalesce(started_at,created_at)>=greatest(c.budget_period_started_at,date_trunc('month',now() at time zone 'UTC') at time zone 'UTC') or status in ('queued','running','uncertain');
 if total+c.run_reserve_usd>c.monthly_budget_usd then return jsonb_build_object('error','research_budget_unavailable'); end if;
 if o.state='checkout' and (p_checkout is null or o.checkout_query_id is distinct from p_checkout) then return jsonb_build_object('error','checkout_already_in_progress'); end if;
 update bot_orders set state='checkout',checkout_query_id=p_checkout where id=p_id;
 return jsonb_build_object('ok',true);
end $$;

create or replace function bot_enqueue(p_user bigint,p_key text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare u bot_users; c bot_control; j bot_jobs; o bot_orders; w date; n integer; total numeric; reserve numeric; billing text;
begin
 select * into c from bot_control where id=1 for update;
 select * into u from bot_users where user_id=p_user for update;
 if not found or not u.approved or u.accepted_at is null then return jsonb_build_object('error','not_approved_or_accepted'); end if;
 select * into j from bot_jobs where request_key=p_key;
 if found then return jsonb_build_object('job_id',j.id,'duplicate',true); end if;
 if not c.enabled then return jsonb_build_object('error','disabled'); end if;
 if exists(select 1 from bot_jobs where user_id=p_user and status in ('queued','running')) then return jsonb_build_object('error','already_running'); end if;
 if exists(select 1 from bot_jobs where status='uncertain') then return jsonb_build_object('error','usage_needs_review'); end if;
 if c.payments_enabled and not bot_payment_exempt(p_user) then
  if p_key like 'schedule:%' then
   if not exists(select 1 from bot_orders where user_id=p_user and product='weekly30' and state='paid' and pass_starts_at<=now() and pass_ends_at>now()) then return jsonb_build_object('error','weekly_payment_required'); end if;
   billing='weekly';
  elsif p_key ~ '^paid:[0-9a-f-]{36}$' then
   select * into o from bot_orders where id=substring(p_key from 6)::uuid and user_id=p_user and product='report' and state='paid' and job_id is null for update;
   if not found then return jsonb_build_object('error','payment_required'); end if;
   billing='report';
  else return jsonb_build_object('error','payment_required'); end if;
 end if;
 w:=date_trunc('week',now() at time zone 'Europe/Berlin')::date;
 select count(*) into n from bot_jobs where user_id=p_user and week_start=w and (status<>'failed' or charged_usd>0) and usage->>'shared_hit' is distinct from 'true';
 if billing is null and (c.admin_user_id is null or p_user<>c.admin_user_id) and n>=(case when u.plan='paid' then 7 else 1 end) then return jsonb_build_object('error','weekly_quota'); end if;
 select coalesce(sum(coalesce(charged_usd,reserved_usd)),0) into total from bot_jobs
 where coalesce(started_at,created_at)>=greatest(c.budget_period_started_at,date_trunc('month',now() at time zone 'UTC') at time zone 'UTC') or status in ('queued','running','uncertain');
 reserve:=case when c.research_v2 then 0 else c.run_reserve_usd end;
 if total+reserve>c.monthly_budget_usd and not c.research_v2 then return jsonb_build_object('error','monthly_budget'); end if;
 insert into bot_jobs(user_id,request_key,week_start,reserved_usd,billing_kind,billing_settings_key)
 values(p_user,left(p_key,160),w,reserve,billing,coalesce(o.settings_key,bot_settings_key(u.settings))) returning * into j;
 if billing='report' then update bot_orders set job_id=j.id where id=o.id; end if;
 return jsonb_build_object('job_id',j.id);
end $$;

create function bot_order_paid(p_user bigint,p_id uuid,p_amount integer,p_currency text,p_charge text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare c bot_control; u bot_users; o bot_orders; result jsonb; start_at timestamptz;
begin
 select * into c from bot_control where id=1 for update;
 select * into u from bot_users where user_id=p_user for update;
 select * into o from bot_orders where id=p_id for update;
 if not found or o.user_id<>p_user or o.amount_stars<>p_amount or p_currency<>'XTR' or length(p_charge)<1 then raise exception 'Invalid payment'; end if;
 if o.telegram_charge_id is not null then
  if o.telegram_charge_id<>p_charge then
   -- A second successful charge cannot buy the same order twice. Retain and
   -- refund it instead of losing its payment identifier on webhook retries.
   if exists(select 1 from bot_orders where telegram_charge_id=p_charge) then return jsonb_build_object('duplicate',true,'state','refund_pending'); end if;
   insert into bot_orders(user_id,product,amount_stars,state,settings_key,telegram_charge_id,paid_at)
   values(p_user,o.product,p_amount,'refund_pending',o.settings_key,p_charge,now());
   return jsonb_build_object('state','refund_pending');
  end if;
  return jsonb_build_object('duplicate',true,'state',o.state,'job_id',o.job_id,'product',o.product);
 end if;
 if exists(select 1 from bot_orders where telegram_charge_id=p_charge) then raise exception 'Charge reused'; end if;
 -- Successful Telegram payment is authoritative even if checkout settings changed.
 update bot_orders set telegram_charge_id=p_charge,paid_at=now(),state='paid' where id=p_id;
 if o.state not in ('created','checkout') or not u.approved or u.accepted_at is null or not c.enabled or not c.payments_enabled or bot_payment_exempt(p_user) then
  update bot_orders set state='refund_pending' where id=p_id;return jsonb_build_object('state','refund_pending');
 end if;
 if o.product='weekly30' then
  select greatest(now(),coalesce(max(pass_ends_at),now())) into start_at from bot_orders where user_id=p_user and product='weekly30' and state='paid';
  update bot_orders set pass_starts_at=start_at,pass_ends_at=start_at+interval '30 days',settings=null where id=p_id;
  update bot_users set weekly=true where user_id=p_user;
  return jsonb_build_object('state','paid','product','weekly30','starts_at',start_at,'ends_at',start_at+interval '30 days');
 end if;
 result:=bot_enqueue(p_user,'paid:'||p_id::text);
 if result ? 'error' then update bot_orders set state='refund_pending',refund_error=result->>'error' where id=p_id;return jsonb_build_object('state','refund_pending'); end if;
 return result||jsonb_build_object('state','paid','product','report');
end $$;

-- Claimed single reports use the invoice snapshot, not subsequently edited settings.
alter function bot_claim(uuid) rename to bot_claim_unbilled;
create function bot_claim(p_id uuid) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare result jsonb; snapshot jsonb; billing text;
begin
 result:=bot_claim_unbilled(p_id);
 if result is null then return null; end if;
 select settings into snapshot from bot_orders where job_id=p_id and product='report' and state='paid';
 if snapshot is not null then result:=jsonb_set(result,'{settings}',snapshot); end if;
 select billing_kind into billing from bot_jobs where id=p_id;
 result:=result||jsonb_build_object('billing_kind',billing);
 return result;
end $$;

create function bot_order_settle(p_job uuid,p_delivered boolean) returns void
language plpgsql security definer set search_path=public,pg_temp as $$
begin
 update bot_orders set state=case when p_delivered then 'delivered' else 'refund_pending' end,
 delivered_at=case when p_delivered then now() else null end,settings=null
 where job_id=p_job and product='report' and state='paid';
end $$;

create function bot_order_refunded(p_user bigint,p_charge text) returns void
language plpgsql security definer set search_path=public,pg_temp as $$
begin
 update bot_orders set state='refunded',refunded_at=now(),settings=null,refund_error=null
 where user_id=p_user and telegram_charge_id=p_charge;
 -- A refunded order that has not started must never consume new research.
 update bot_jobs set status='failed',charged_usd=0,finished_at=now(),error_code='PaymentRefunded'
 where status='queued' and id in (select job_id from bot_orders where user_id=p_user and telegram_charge_id=p_charge);
end $$;

create function bot_order_cancel_overdue(p_id uuid) returns void
language plpgsql security definer set search_path=public,pg_temp as $$
declare c bot_control; j bot_jobs; o bot_orders; job uuid;
begin
 select * into c from bot_control where id=1 for update;
 select job_id into job from bot_orders where id=p_id;
 select * into j from bot_jobs where id=job for update;
 if not found or j.status<>'queued' or j.created_at>now()-interval '24 hours' then return; end if;
 select * into o from bot_orders where id=p_id for update;
 if not found or o.state<>'paid' then return; end if;
 update bot_jobs set status='failed',charged_usd=0,finished_at=now(),error_code='PaidQueueOverdue' where id=job;
 update bot_orders set state='refund_pending',settings=null where id=p_id;
end $$;

-- Shared cached results are freely reopened by purchasers, not a checkout bypass.
alter function bot_saved_report(bigint) rename to bot_saved_report_unbilled;
create function bot_saved_report(p_user bigint) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare u bot_users; c bot_control;
begin
 select * into u from bot_users where user_id=p_user;
 select * into c from bot_control where id=1;
 if c.payments_enabled and not bot_payment_exempt(p_user) and not exists(
  select 1 from bot_jobs j where j.user_id=p_user and j.status='complete' and j.delivered and j.billing_kind in ('report','weekly') and j.billing_settings_key=bot_settings_key(u.settings)
 ) then return null; end if;
 return bot_saved_report_unbilled(p_user);
end $$;

do $$
declare signature text;
begin
 foreach signature in array array['bot_payment_exempt(bigint)','bot_order_create(bigint,text)','bot_order_checkout(bigint,uuid,integer,text,text)','bot_order_paid(bigint,uuid,integer,text,text)','bot_order_settle(uuid,boolean)','bot_order_refunded(bigint,text)','bot_order_cancel_overdue(uuid)','bot_claim(uuid)','bot_claim_unbilled(uuid)','bot_saved_report(bigint)','bot_saved_report_unbilled(bigint)'] loop
  execute 'revoke all on function '||signature||' from public,anon,authenticated';
  execute 'grant execute on function '||signature||' to service_role';
 end loop;
end $$;
commit;

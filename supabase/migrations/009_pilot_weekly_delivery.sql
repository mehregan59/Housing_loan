-- Apply after 008. Pilot weekly delivery is separate from manual quotas.
-- Approval, consent, one active job, idempotency and spending safeguards remain.
begin;
alter table bot_control add column notices_enabled boolean not null default true;
alter table bot_control add column agreement_version integer not null default 1 check(agreement_version>0);
alter table bot_control add column agreement_text text check(length(agreement_text)<=3200);
alter table bot_users add column agreement_version_accepted integer not null default 0;
-- These users already accepted the unchanged initial notice; no new terms are accepted for them.
update bot_users set agreement_version_accepted=1 where accepted_at is not null;
create table bot_notices(
 user_id bigint not null references bot_users,kind text not null check(kind in ('guide','agreement')),
 version integer not null check(version>0),message_id bigint,pinned boolean not null default false,
 acknowledged_at timestamptz,created_at timestamptz not null default now(),primary key(user_id,kind,version)
);
alter table bot_notices enable row level security;
revoke all on bot_notices from public,anon,authenticated;
grant all on bot_notices to service_role;
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
 select count(*) into n from bot_jobs where user_id=p_user and service='investment' and week_start=w and (status<>'failed' or charged_usd>0) and usage->>'shared_hit' is distinct from 'true';
 if billing is null and not (u.pilot_free and u.weekly and u.service='investment' and p_key like ('schedule:'||p_user||':%')) and (c.admin_user_id is null or p_user<>c.admin_user_id) and n>=(case when u.plan='paid' then 7 else 1 end) then return jsonb_build_object('error','weekly_quota'); end if;
 select coalesce(sum(coalesce(charged_usd,reserved_usd)),0) into total from bot_jobs
 where coalesce(started_at,created_at)>=greatest(c.budget_period_started_at,date_trunc('month',now() at time zone 'UTC') at time zone 'UTC') or status in ('queued','running','uncertain');
 reserve:=case when c.research_v2 then 0 else c.run_reserve_usd end;
 if total+reserve>c.monthly_budget_usd and not c.research_v2 then return jsonb_build_object('error','monthly_budget'); end if;
 insert into bot_jobs(user_id,request_key,week_start,reserved_usd,billing_kind,billing_settings_key)
 values(p_user,left(p_key,160),w,reserve,billing,coalesce(o.settings_key,bot_settings_key(u.settings))) returning * into j;
 if billing='report' then update bot_orders set job_id=j.id where id=o.id; end if;
 return jsonb_build_object('job_id',j.id);
end $$;
commit;

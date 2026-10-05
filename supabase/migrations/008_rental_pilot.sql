-- Rental pilot: no rental payment price is set and no rental invoice is issued.
begin;
alter table bot_users add column service text not null default 'investment' check(service in ('investment','rental'));
alter table bot_users add column service_selected boolean not null default false;
update bot_users set service_selected=true;
alter table bot_users add column rental_settings jsonb not null default '{"location":"Freiburg","radius_km":25,"max_rent_eur":1000}';
alter table bot_users add column rental_daily boolean not null default false;
alter table bot_users add column rental_trial_used_at timestamptz;
alter table bot_jobs add column service text not null default 'investment' check(service in ('investment','rental'));
alter table bot_jobs add column rental_snapshot jsonb;
alter table bot_jobs add column rental_day date;
alter table bot_control add column rental_enabled boolean not null default false;
alter table bot_control add column rental_prices_stars jsonb not null default '{}';
create table bot_rental_cache(cache_key text primary key,payload jsonb not null,center jsonb not null default '{}',stats jsonb not null default '{}',checked_at timestamptz not null,expires_at timestamptz not null);
alter table bot_rental_cache enable row level security;
revoke all on bot_rental_cache from public,anon,authenticated;
grant all on bot_rental_cache to service_role;

create function bot_rental_enqueue(p_user bigint,p_key text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare u bot_users; c bot_control; j bot_jobs; d date;
begin
 select * into c from bot_control where id=1 for update;
 select * into u from bot_users where user_id=p_user for update;
 if not found or not u.approved or u.accepted_at is null or u.service<>'rental' then return jsonb_build_object('error','choose_rental_and_accept_first'); end if;
 if not c.enabled or not c.research_v2 or not c.rental_enabled then return jsonb_build_object('error','rental_not_enabled'); end if;
 if jsonb_typeof(u.rental_settings->'max_rent_eur') is distinct from 'number' or jsonb_typeof(u.rental_settings->'radius_km') is distinct from 'number' or coalesce(length(trim(u.rental_settings->>'location')),0)=0 or (u.rental_settings->>'max_rent_eur')::numeric<=0 or (u.rental_settings->>'radius_km')::numeric not between 0 and 300 then return jsonb_build_object('error','invalid_rental_settings'); end if;
 select * into j from bot_jobs where request_key=p_key;
 if found then return jsonb_build_object('job_id',j.id,'duplicate',true); end if;
 if exists(select 1 from bot_jobs where user_id=p_user and status in ('queued','running')) then return jsonb_build_object('error','already_running'); end if;
 if exists(select 1 from bot_jobs where status='uncertain') then return jsonb_build_object('error','usage_needs_review'); end if;
 if not bot_payment_exempt(p_user) and (u.rental_trial_used_at is not null or exists(select 1 from bot_jobs where user_id=p_user and service='rental' and status='complete' and report is not null)) then return jsonb_build_object('error','rental_prices_not_ready'); end if;
 d:=(now() at time zone 'Europe/Berlin')::date;
 if c.admin_user_id is distinct from p_user and exists(select 1 from bot_jobs where user_id=p_user and service='rental' and rental_day=d) then return jsonb_build_object('error','one_rental_attempt_per_day'); end if;
 insert into bot_jobs(user_id,request_key,week_start,reserved_usd,service,rental_snapshot,rental_day)
 values(p_user,left(p_key,160),date_trunc('week',now() at time zone 'Europe/Berlin')::date,0,'rental',u.rental_settings,d) returning * into j;
 return jsonb_build_object('job_id',j.id);
end $$;

alter function bot_claim(uuid) rename to bot_claim_investment;
create function bot_claim(p_id uuid) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare result jsonb; j bot_jobs;
begin
 select * into j from bot_jobs where id=p_id;
 if j.service='rental' and not exists(select 1 from bot_control where id=1 and rental_enabled) then return null; end if;
 result:=bot_claim_investment(p_id);
 if result is null then return null; end if;
 select * into j from bot_jobs where id=p_id;
 result:=result||jsonb_build_object('service',j.service);
 if j.service='rental' then result:=result||jsonb_build_object('settings',j.rental_snapshot||'{"_guide_version":1,"language":"en"}'::jsonb); end if;
 return result;
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
 select count(*) into n from bot_jobs where user_id=p_user and service='investment' and week_start=w and (status<>'failed' or charged_usd>0) and usage->>'shared_hit' is distinct from 'true';
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

-- A preview can only expose the administrator's weekly investment report,
-- never another customer's private report. No AI call or quota is consumed.
create function bot_weekly_preview(p_user bigint) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare j bot_jobs;
begin
 if not exists(select 1 from bot_users where user_id=p_user and approved and accepted_at is not null and service='investment') then return null; end if;
 select b.* into j from bot_jobs b join bot_control c on c.id=1 and b.user_id=c.admin_user_id
 where b.service='investment' and b.status='complete' and b.delivered and b.report is not null and b.request_key like 'schedule:%' and b.finished_at>now()-interval '7 days'
 order by b.finished_at desc limit 1;
 if not found then return null; end if;
 return jsonb_build_object('report',j.report,'finished_at',j.finished_at);
end $$;
revoke all on function bot_rental_enqueue(bigint,text),bot_claim(uuid),bot_claim_investment(uuid),bot_weekly_preview(bigint) from public,anon,authenticated;
grant execute on function bot_rental_enqueue(bigint,text),bot_claim(uuid),bot_claim_investment(uuid),bot_weekly_preview(bigint) to service_role;
commit;

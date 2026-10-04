-- Apply once AFTER the code update. Existing bot remains on the legacy pipeline.
-- Activation is a separate administrator step; this migration makes no API call.
begin;
alter table public.bot_control add column research_v2 boolean not null default false;
create table public.bot_market_cache (
 cache_key text primary key, kind text not null check(kind in ('pool','rates')),
 version integer not null, payload jsonb not null,
 radius_km numeric, created_at timestamptz not null, expires_at timestamptz not null
);
create index bot_cache_lookup on public.bot_market_cache(kind,expires_at);
alter table public.bot_market_cache enable row level security;
revoke all on public.bot_market_cache from public,anon,authenticated;
grant all on public.bot_market_cache to service_role;
create or replace function public.bot_enqueue(p_user bigint,p_key text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare u bot_users; c bot_control; j bot_jobs; w date; n integer; total numeric; reserve numeric;
begin
  select * into c from bot_control where id=1 for update;
  select * into u from bot_users where user_id=p_user for update;
  if not found or not u.approved or u.accepted_at is null then return jsonb_build_object('error','not_approved_or_accepted'); end if;
  select * into j from bot_jobs where request_key=p_key;
  if found then return jsonb_build_object('job_id',j.id,'duplicate',true); end if;
  if not c.enabled then return jsonb_build_object('error','disabled'); end if;
  if exists(select 1 from bot_jobs where user_id=p_user and status in ('queued','running')) then return jsonb_build_object('error','already_running'); end if;
  if exists(select 1 from bot_jobs where status='uncertain') then return jsonb_build_object('error','usage_needs_review'); end if;
  w := date_trunc('week',now() at time zone 'Europe/Berlin')::date;
  select count(*) into n from bot_jobs where user_id=p_user and week_start=w
    and (status<>'failed' or charged_usd>0);
  if n >= (case when u.plan='paid' then 7 else 1 end) then return jsonb_build_object('error','weekly_quota'); end if;
  select coalesce(sum(coalesce(charged_usd,reserved_usd)),0) into total from bot_jobs
    where coalesce(started_at,created_at) >= date_trunc('month',now() at time zone 'UTC') at time zone 'UTC'
       or status in ('queued','running','uncertain');
  reserve := case when c.research_v2 then 0 else c.run_reserve_usd end;
  if total+reserve > c.monthly_budget_usd and not c.research_v2 then return jsonb_build_object('error','monthly_budget'); end if;
  insert into bot_jobs(user_id,request_key,week_start,reserved_usd) values(p_user,left(p_key,160),w,reserve) returning * into j;
  return jsonb_build_object('job_id',j.id);
end $$;

create or replace function public.bot_claim(p_id uuid) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare j bot_jobs; u bot_users; c bot_control; total numeric;
begin
  select * into c from bot_control where id=1 for update;
  select * into j from bot_jobs where id=p_id for update;
  if not found or j.status<>'queued' then return null; end if;
  select * into u from bot_users where user_id=j.user_id;
  if not c.enabled or not u.approved or u.accepted_at is null or exists(select 1 from bot_jobs where status='uncertain') then return null; end if;
  select coalesce(sum(coalesce(charged_usd,reserved_usd)),0) into total from bot_jobs
    where coalesce(started_at,created_at) >= date_trunc('month',now() at time zone 'UTC') at time zone 'UTC'
       or status in ('queued','running','uncertain');
  if total>c.monthly_budget_usd and not c.research_v2 then return null; end if;
  update bot_jobs set status='running',started_at=now() where id=p_id;
  return jsonb_build_object('id',j.id,'user_id',j.user_id,'settings',u.settings,'reserved_usd',j.reserved_usd,'research_v2',c.research_v2);
end $$;


create function public.bot_research_reserve(p_id uuid) returns boolean
language plpgsql security definer set search_path=public,pg_temp as $$
declare c bot_control; j bot_jobs; total numeric;
begin
 select * into c from bot_control where id=1 for update;
 select * into j from bot_jobs where id=p_id for update;
 if not found or j.status<>'running' or not c.enabled or not c.research_v2 then return false; end if;
 if exists(select 1 from bot_jobs where status='uncertain') then return false; end if;
 select coalesce(sum(coalesce(charged_usd,reserved_usd)),0) into total from bot_jobs
 where coalesce(started_at,created_at)>=date_trunc('month',now() at time zone 'UTC') at time zone 'UTC'
 or status in ('queued','running','uncertain');
 if total-j.reserved_usd+c.run_reserve_usd>c.monthly_budget_usd then return false; end if;
 update bot_jobs set reserved_usd=c.run_reserve_usd where id=p_id;
 return true;
end $$;
revoke execute on function public.bot_research_reserve(uuid) from public,anon,authenticated;
grant execute on function public.bot_research_reserve(uuid) to service_role;
commit;

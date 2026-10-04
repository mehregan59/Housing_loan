-- Run once in Supabase SQL Editor. No personal settings or identifiers are seeded.
begin;
create table public.bot_users (
  user_id bigint primary key, approved boolean not null default false,
  plan text not null default 'free' check (plan in ('free','paid')),
  accepted_at timestamptz,
  settings jsonb not null default '{"location":"Freiburg","country":"Germany","radius_km":100,"max_price_eur":250000,"max_loan_eur":250000,"equity_eur":0,"min_size_m2":30,"language":"en","fixed_rate_years":10,"repayment_pct":2,"target_gross_yield_pct":null,"min_monthly_cashflow_eur":null,"max_price_per_m2":null,"areas":[],"exclude":["Erbpacht","Zwangsversteigerung"]}',
  weekly boolean not null default false,
  schedule_day integer not null default 0 check(schedule_day between 0 and 6),
  schedule_time text not null default '08:00' check(schedule_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
  timezone text not null default 'Europe/Berlin',
  created_at timestamptz not null default now()
);
create table public.bot_control (
  id integer primary key check(id=1), enabled boolean not null default false,
  channel_enabled boolean not null default false,
  monthly_budget_usd numeric not null default 8 check(monthly_budget_usd>0),
  run_reserve_usd numeric not null default 1 check(run_reserve_usd>0)
);
insert into public.bot_control(id) values(1);
create table public.bot_jobs (
  id uuid primary key default gen_random_uuid(), user_id bigint not null references public.bot_users,
  request_key text unique not null, week_start date not null,
  status text not null default 'queued' check(status in ('queued','running','complete','failed','uncertain')),
  reserved_usd numeric not null, charged_usd numeric,
  started_at timestamptz, finished_at timestamptz, created_at timestamptz not null default now(),
  report text, usage jsonb, error_code text, delivered boolean not null default false
);
create unique index bot_one_active_job on public.bot_jobs(user_id) where status in ('queued','running');
create table public.bot_seen (
  user_id bigint references public.bot_users, url text not null, evaluated_at timestamptz not null default now(),
  primary key(user_id,url)
);
create table public.bot_health (id integer primary key check(id=1), checked_at timestamptz not null default now());
create table public.bot_updates (update_id bigint primary key, created_at timestamptz not null default now());
alter table public.bot_users enable row level security;
alter table public.bot_jobs enable row level security;
alter table public.bot_control enable row level security;
alter table public.bot_seen enable row level security;
alter table public.bot_health enable row level security;
alter table public.bot_updates enable row level security;
revoke all on public.bot_users,public.bot_jobs,public.bot_control,public.bot_seen,public.bot_health from anon,authenticated;
grant all on public.bot_users,public.bot_jobs,public.bot_control,public.bot_seen,public.bot_health to service_role;
revoke all on public.bot_updates from anon,authenticated;
grant all on public.bot_updates to service_role;

create function public.bot_enqueue(p_user bigint,p_key text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare u bot_users; c bot_control; j bot_jobs; w date; n integer; total numeric;
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
  if total+c.run_reserve_usd > c.monthly_budget_usd then return jsonb_build_object('error','monthly_budget'); end if;
  insert into bot_jobs(user_id,request_key,week_start,reserved_usd) values(p_user,left(p_key,160),w,c.run_reserve_usd) returning * into j;
  return jsonb_build_object('job_id',j.id);
end $$;

create function public.bot_claim(p_id uuid) returns jsonb
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
  if total>c.monthly_budget_usd then return null; end if;
  update bot_jobs set status='running',started_at=now() where id=p_id;
  return jsonb_build_object('id',j.id,'user_id',j.user_id,'settings',u.settings,'reserved_usd',j.reserved_usd);
end $$;

create function public.bot_finish(p_id uuid,p_status text,p_cost numeric,p_report text,p_usage jsonb,p_error text,p_urls jsonb) returns void
language plpgsql security definer set search_path=public,pg_temp as $$
declare j bot_jobs; v text;
begin
  select * into j from bot_jobs where id=p_id for update;
  if not found or j.status<>'running' then raise exception 'Job not running'; end if;
  if p_status not in ('complete','failed','uncertain') or (p_cost is not null and p_cost<0) then raise exception 'Invalid settlement'; end if;
  update bot_jobs set status=p_status,charged_usd=p_cost,report=p_report,usage=p_usage,
    error_code=p_error,finished_at=now() where id=p_id;
  if p_status='complete' then
    for v in select jsonb_array_elements_text(p_urls) loop
      if length(v)<=2048 and v ~ '^https?://' then
        insert into bot_seen(user_id,url) values(j.user_id,v) on conflict(user_id,url) do update set evaluated_at=now();
      end if;
    end loop;
  end if;
end $$;

revoke execute on function public.bot_enqueue(bigint,text),public.bot_claim(uuid),public.bot_finish(uuid,text,numeric,text,jsonb,text,jsonb) from public,anon,authenticated;
grant execute on function public.bot_enqueue(bigint,text),public.bot_claim(uuid),public.bot_finish(uuid,text,numeric,text,jsonb,text,jsonb) to service_role;
commit;

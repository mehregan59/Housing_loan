-- Apply once after 003. Creates free saved-report retrieval, never a paid run.
begin;
alter table public.bot_control add column shared_reports_enabled boolean not null default true;
create table public.bot_shared_reports (
 settings_key text primary key, report text not null, urls jsonb not null,
 expires_at timestamptz not null, created_at timestamptz not null default now()
);
alter table public.bot_shared_reports enable row level security;
revoke all on public.bot_shared_reports from public,anon,authenticated;
grant all on public.bot_shared_reports to service_role;
create function public.bot_settings_key(p_settings jsonb) returns text
language sql immutable set search_path=public,pg_temp as $$
 select encode(sha256(convert_to(coalesce((select jsonb_object_agg(key,value) from jsonb_each(p_settings) where left(key,1)<>'_'),'{}'::jsonb)::text,'UTF8')),'hex')
$$;
create function public.bot_shared_get(p_settings jsonb) returns jsonb
language sql security definer set search_path=public,pg_temp as $$
 select jsonb_build_object('report',r.report,'urls',r.urls,'expires_at',r.expires_at)
 from bot_shared_reports r,bot_control c
 where c.id=1 and c.shared_reports_enabled and r.settings_key=bot_settings_key(p_settings) and r.expires_at>now()
$$;
create function public.bot_shared_publish(p_settings jsonb,p_report text,p_urls jsonb,p_expires timestamptz) returns void
language plpgsql security definer set search_path=public,pg_temp as $$
begin
 if p_expires<=now() or length(p_report)>30000 or jsonb_typeof(p_urls)<>'array' then return; end if;
 if not exists(select 1 from bot_control where id=1 and shared_reports_enabled) then return; end if;
 insert into bot_shared_reports(settings_key,report,urls,expires_at)
 values(bot_settings_key(p_settings),p_report,p_urls,p_expires)
 on conflict(settings_key) do update set report=excluded.report,urls=excluded.urls,expires_at=excluded.expires_at,created_at=now();
end $$;
create function public.bot_saved_report(p_user bigint) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare u bot_users; result jsonb; v text;
begin
 select * into u from bot_users where user_id=p_user;
 if not found or not u.approved or u.accepted_at is null then return null; end if;
 result:=bot_shared_get(u.settings);
 if result is not null then
  for v in select jsonb_array_elements_text(result->'urls') loop
   insert into bot_seen(user_id,url) values(p_user,v) on conflict(user_id,url) do update set evaluated_at=now();
  end loop;
 end if;
 return result;
end $$;
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
    and (status<>'failed' or charged_usd>0) and (usage->>'shared_hit') is distinct from 'true';
  if (c.admin_user_id is null or p_user<>c.admin_user_id) and n >= (case when u.plan='paid' then 7 else 1 end) then return jsonb_build_object('error','weekly_quota'); end if;
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
  return jsonb_build_object('id',j.id,'user_id',j.user_id,'settings',u.settings,'reserved_usd',j.reserved_usd,'research_v2',c.research_v2,'shared_reports_enabled',c.shared_reports_enabled);
end $$;


revoke execute on function public.bot_settings_key(jsonb),public.bot_shared_get(jsonb),public.bot_shared_publish(jsonb,text,jsonb,timestamptz),public.bot_saved_report(bigint) from public,anon,authenticated;
grant execute on function public.bot_settings_key(jsonb),public.bot_shared_get(jsonb),public.bot_shared_publish(jsonb,text,jsonb,timestamptz),public.bot_saved_report(bigint) to service_role;
commit;

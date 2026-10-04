-- Apply once after migration 002. No administrator ID is committed.
-- The authenticated administrator's next private bot interaction configures the ID.
begin;
alter table public.bot_control add column admin_user_id bigint check(admin_user_id>0);
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
  if (c.admin_user_id is null or p_user<>c.admin_user_id) and n >= (case when u.plan='paid' then 7 else 1 end) then return jsonb_build_object('error','weekly_quota'); end if;
  select coalesce(sum(coalesce(charged_usd,reserved_usd)),0) into total from bot_jobs
    where coalesce(started_at,created_at) >= date_trunc('month',now() at time zone 'UTC') at time zone 'UTC'
       or status in ('queued','running','uncertain');
  reserve := case when c.research_v2 then 0 else c.run_reserve_usd end;
  if total+reserve > c.monthly_budget_usd and not c.research_v2 then return jsonb_build_object('error','monthly_budget'); end if;
  insert into bot_jobs(user_id,request_key,week_start,reserved_usd) values(p_user,left(p_key,160),w,reserve) returning * into j;
  return jsonb_build_object('job_id',j.id);
end $$;

commit;

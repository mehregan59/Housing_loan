\ir ../supabase/migrations/009_pilot_weekly_delivery.sql
begin;
do $$
declare result jsonb; w date;
begin
 update bot_control set enabled=true,research_v2=true,pilot_locked=false,payments_enabled=false;
 insert into bot_users(user_id,approved,accepted_at,pilot_free,weekly,settings) values(999990031,true,now(),true,true,'{}');
 w:=date_trunc('week',now() at time zone 'Europe/Berlin')::date;
 insert into bot_jobs(user_id,request_key,week_start,reserved_usd,charged_usd,status,usage) values(999990031,'manual-used',w,0,0,'complete','{}');
 result:=bot_enqueue(999990031,'telegram:manual-quota');assert result->>'error'='weekly_quota','Manual quota preserved';
 result:=bot_enqueue(999990031,'schedule:999990031:'||w);assert result ? 'job_id','Pilot weekly delivery cannot be blocked by manual quota';
 result:=bot_enqueue(999990031,'schedule:999990031:'||w);assert result->>'duplicate'='true','Scheduled run remains idempotent';
 assert (select settings->>'_guide_version' is null from bot_users where user_id=999990031),'Guide not falsely completed';
end $$;
rollback;
begin;
do $$
begin
 assert not has_table_privilege('anon','bot_notices','select');
 assert not has_table_privilege('authenticated','bot_notices','insert');
 assert (select agreement_version_accepted=1 from bot_users where user_id=999990010),'Existing consent to unchanged initial notice retained';
end $$;
rollback;

\ir ../supabase/migrations/006_budget_restart.sql
begin;
do $$
declare result boolean; job uuid; before_count integer;
begin
 update bot_control set enabled=true,research_v2=true;
 insert into bot_users(user_id,approved,accepted_at,settings) values(999990003,true,now(),'{"_guide_version":1}');
 insert into bot_jobs(user_id,request_key,week_start,status,reserved_usd,charged_usd,started_at,created_at)
 values(999990003,'old-budget-ledger',current_date,'complete',0,99,now()-interval '1 hour',now()-interval '1 hour');
 insert into bot_jobs(user_id,request_key,week_start,status,reserved_usd,started_at)
 values(999990003,'new-budget-period',current_date,'running',0,now()) returning id into job;
 result=bot_research_reserve(job);
 assert result,'Historical charges should not block the new period';
 assert (select charged_usd=99 from bot_jobs where request_key='old-budget-ledger'),'Real charges must remain intact';
 assert (select reserved_usd=1 from bot_jobs where id=job),'Reserve remains active';
 update bot_control set monthly_budget_usd=0.5;
 result=bot_research_reserve(job);
 assert not result,'New period must still enforce its cap';
end $$;
rollback;

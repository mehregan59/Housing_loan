begin;
insert into bot_users(user_id,approved,accepted_at) values(3001,true,now()),(3002,true,now()),(3003,false,now());
update bot_control set enabled=true,admin_user_id=3001,monthly_budget_usd=8,research_v2=true;
do $$ declare a jsonb; j uuid; i integer; begin
 for i in 1..12 loop
  a:=bot_enqueue(3001,'admin-run-'||i);j:=(a->>'job_id')::uuid;
  if j is null then raise exception 'Administrator weekly quota applied'; end if;
  if bot_enqueue(3001,'admin-parallel-'||i)->>'error'<>'already_running' then raise exception 'Administrator parallel protection bypass'; end if;
  perform bot_claim(j);perform bot_finish(j,'complete',0,'cached','{}',null,'[]');
 end loop;
 a:=bot_enqueue(3002,'ordinary-first');j:=(a->>'job_id')::uuid;
 perform bot_claim(j);perform bot_finish(j,'complete',0,'cached','{}',null,'[]');
 if bot_enqueue(3002,'ordinary-second')->>'error'<>'weekly_quota' then raise exception 'Ordinary quota exemption leaked'; end if;
 update bot_control set admin_user_id=3003;
 if bot_enqueue(3003,'admin-not-approved')->>'error'<>'not_approved_or_accepted' then raise exception 'Administrator approval bypass'; end if;
 update bot_control set admin_user_id=3001,monthly_budget_usd=.5,research_v2=false;
 update bot_jobs set charged_usd=.5 where request_key='admin-run-1';
 if bot_enqueue(3001,'admin-budget')->>'error'<>'monthly_budget' then raise exception 'Administrator spending cap bypass'; end if;
 update bot_control set research_v2=true;
 a:=bot_enqueue(3001,'admin-cached');j:=(a->>'job_id')::uuid;
 perform bot_claim(j);
 if bot_research_reserve(j) then raise exception 'Administrator fresh research allowed at budget'; end if;
 perform bot_finish(j,'uncertain',null,null,'{}','test','[]');
 if bot_enqueue(3001,'admin-uncertain')->>'error'<>'usage_needs_review' then raise exception 'Administrator uncertainty protection bypass'; end if;
end $$;
rollback;

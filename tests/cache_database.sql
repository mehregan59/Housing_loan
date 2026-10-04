begin;
insert into bot_users(user_id,approved,accepted_at,plan) values(2001,true,now(),'free'),(2002,true,now(),'paid'),(2003,false,now(),'free');
update bot_control set enabled=true,research_v2=true,monthly_budget_usd=1,run_reserve_usd=1;
do $$ declare a jsonb; j uuid; i integer; begin
 a:=bot_enqueue(2003,'cache-unapproved');
 if a->>'error'<>'not_approved_or_accepted' then raise exception 'Approval bypass'; end if;
 a:=bot_enqueue(2001,'cache-free');j:=(a->>'job_id')::uuid;
 a:=bot_claim(j);
 if a->>'research_v2'<>'true' or (a->>'reserved_usd')::numeric<>0 then raise exception 'V2 claim invalid'; end if;
 if not bot_research_reserve(j) then raise exception 'Fresh research not reserved'; end if;
 perform bot_finish(j,'complete',1,'report','{}',null,'[]');
 if bot_enqueue(2001,'cache-free-again')->>'error'<>'weekly_quota' then raise exception 'Free cache quota bypass'; end if;
 for i in 1..7 loop
  a:=bot_enqueue(2002,'cache-paid-'||i);j:=(a->>'job_id')::uuid;
  if j is null then raise exception 'Cached request blocked at budget'; end if;
  if bot_claim(j) is null then raise exception 'Cached claim blocked at budget'; end if;
  if bot_research_reserve(j) then raise exception 'New spend permitted at exhausted budget'; end if;
  perform bot_finish(j,'complete',0,'cached','{}',null,'[]');
 end loop;
 if bot_enqueue(2002,'cache-paid-8')->>'error'<>'weekly_quota' then raise exception 'Paid cache quota bypass'; end if;
 if has_table_privilege('anon','bot_market_cache','SELECT') or has_table_privilege('authenticated','bot_market_cache','SELECT') then raise exception 'Cache leaked'; end if;
 if has_function_privilege('anon','bot_research_reserve(uuid)','EXECUTE') then raise exception 'Research reserve exposed'; end if;
end $$;
rollback;

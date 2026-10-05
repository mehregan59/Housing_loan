\ir ../supabase/migrations/008_rental_pilot.sql
begin;
do $$
declare result jsonb; j uuid;
begin
 update bot_control set enabled=true,research_v2=true,rental_enabled=true,pilot_locked=true;
 insert into bot_users(user_id,approved,accepted_at,service) values(999990021,true,now(),'rental');
 assert not (select pilot_free from bot_users where user_id=999990021),'Future users not pilot exempt';
 update bot_users set rental_settings='{"location":"Berlin","radius_km":15,"max_rent_eur":1500}' where user_id=999990021;
 assert (select rental_settings->>'location'='Berlin' from bot_users where user_id=999990021),'Investment pilot lock must not reset rental settings';
 result:=bot_rental_enqueue(999990021,'rental:test');j:=(result->>'job_id')::uuid;
 assert j is not null,'Free rental trial must enqueue without payment or investment guide';
 result:=bot_rental_enqueue(999990021,'rental:test');assert result->>'duplicate'='true';
 result:=bot_rental_enqueue(999990021,'rental:second');assert result->>'error'='already_running';
 update bot_users set rental_settings='{"location":"Hamburg","radius_km":5,"max_rent_eur":900}' where user_id=999990021;
 result:=bot_claim(j);assert result->>'service'='rental';
 assert result->'settings'->>'location'='Berlin','Queued rental snapshot preserved';
 assert result->'settings'->>'_guide_version'='1';
 perform bot_finish(j,'failed',0,null,'{}','OfflineTest','[]');
 assert (select rental_trial_used_at is null from bot_users where user_id=999990021),'Failed trial remains unused';
 result:=bot_rental_enqueue(999990021,'rental:retry');assert result->>'error'='one_rental_attempt_per_day';
 update bot_jobs set rental_day=rental_day-1 where id=j;
 result:=bot_rental_enqueue(999990021,'rental:retry-next-day');assert result ? 'job_id';
 j:=(result->>'job_id')::uuid;result:=bot_claim(j);
 perform bot_finish(j,'complete',0,'example rental report','{}',null,'[]');
 result:=bot_rental_enqueue(999990021,'rental:trial-bypass');assert result->>'error'='rental_prices_not_ready','Saved completed report must block trial duplication until reopened/delivered';
 update bot_users set rental_trial_used_at=now() where user_id=999990021;
 result:=bot_rental_enqueue(999990021,'rental:payment');assert result->>'error'='rental_prices_not_ready';
 assert bot_weekly_preview(999990021) is null,'Rental user cannot request investment preview';
 assert not has_function_privilege('anon','bot_rental_enqueue(bigint,text)','execute');
 assert not has_table_privilege('authenticated','bot_rental_cache','select');
end $$;
rollback;

\ir ../supabase/migrations/011_rental_language.sql
begin;
do $$
declare r jsonb; j uuid;
begin
 update bot_control set admin_user_id=999990051,enabled=true,research_v2=true,rental_enabled=true;
 insert into bot_users(user_id,approved,accepted_at,service,rental_settings) values
 (999990051,true,now(),'rental','{"location":"Berlin","radius_km":25,"max_rent_eur":1000,"language":"de"}');
 r:=bot_rental_enqueue(999990051,'rent:german');j:=(r->>'job_id')::uuid;
 r:=bot_claim(j);assert r->'settings'->>'language'='de','Rental language must survive claim';
 assert not has_function_privilege('anon','bot_claim(uuid)','execute');
end $$;
rollback;

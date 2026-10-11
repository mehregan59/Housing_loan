\ir ../supabase/migrations/010_rental_rent_limits.sql
begin;
do $$
declare r jsonb;
begin
 update bot_control set admin_user_id=999990041,enabled=true,research_v2=true,rental_enabled=true;
 insert into bot_users(user_id,approved,accepted_at,service,rental_settings) values
 (999990041,true,now(),'rental','{"location":"Berlin","radius_km":25,"max_rent_eur":null,"max_cold_rent_eur":800,"max_charges_eur":200}'),
 (999990042,true,now(),'rental','{"location":"Berlin","radius_km":25,"max_rent_eur":1000}');
 r:=bot_rental_enqueue(999990042,'rent:blocked');assert r->>'error'='rental_admin_only';
 r:=bot_rental_enqueue(999990041,'rent:allowed');assert r ? 'job_id','Cold and charges limits without warm limit should work';
 update bot_jobs set status='failed',charged_usd=0 where user_id=999990041;
 update bot_users set rental_settings='{"location":"Berlin","radius_km":25,"max_rent_eur":null}' where user_id=999990041;
 r:=bot_rental_enqueue(999990041,'rent:invalid');assert r->>'error'='invalid_rental_settings';
 assert not has_function_privilege('anon','bot_rental_enqueue_internal(bigint,text)','execute');
end $$;
rollback;

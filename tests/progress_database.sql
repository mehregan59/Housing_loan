begin;
do $$
declare r jsonb; j uuid;
begin
 update bot_control set admin_user_id=999990061,enabled=true,research_v2=true,rental_enabled=true;
 insert into bot_users(user_id,approved,accepted_at,service,rental_settings) values
 (999990061,true,now(),'rental','{"location":"Freiburg","radius_km":60,"max_rent_eur":1700,"min_rooms":2.5,"max_rooms":4,"furnishing":"partial"}');
 r:=bot_rental_enqueue(999990061,'rent:progress');j:=(r->>'job_id')::uuid;
 assert j is not null;
 r:=bot_rental_enqueue(999990061,'rent:duplicate-active');assert r->>'error'='already_running';
 update bot_jobs set progress_message_id=777 where id=j;
 r:=bot_claim(j);assert r->>'progress_message_id'='777';assert r->'settings'->>'min_rooms'='2.5';
 update bot_jobs set status='failed',charged_usd=0 where id=j;
 update bot_users set rental_settings=jsonb_set(rental_settings,'{min_rooms}','5') where user_id=999990061;
 r:=bot_rental_enqueue(999990061,'rent:invalid-room');assert r->>'error'='invalid_room_limits';
end $$;
rollback;

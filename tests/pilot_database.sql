-- Offline test only: verify preset migration affects existing and new users.
insert into bot_users(user_id,approved,settings,weekly,schedule_time)
values(999990001,true,'{"location":"Berlin","_guide_version":1,"_access":{"nonce":"preserve"}}',false,'18:00');
\ir ../supabase/migrations/005_locked_pilot.sql
begin;
do $$
declare u bot_users;
begin
 select * into u from bot_users where user_id=999990001;
 assert u.settings->>'location'='Freiburg';
 assert u.settings->>'radius_km'='150';
 assert u.settings->>'equity_eur'='10000';
 assert u.settings->>'max_price_eur'='300000';
 assert u.settings->>'max_loan_eur'='300000';
 assert u.settings->>'repayment_pct'='2';
 assert u.settings->>'_guide_version'='1';
 assert u.settings->'_access'->>'nonce'='preserve';
 assert u.weekly and u.schedule_day=0 and u.schedule_time='09:00' and u.timezone='Europe/Berlin';
 insert into bot_users(user_id) values(999990002);
 select * into u from bot_users where user_id=999990002;
 assert not u.approved;
 assert u.accepted_at is null;
 assert u.weekly;
 assert u.settings->>'fixed_rate_years'='30';
 update bot_users set settings='{"location":"Hamburg","repayment_pct":99,"_guide_version":1}',weekly=false,schedule_day=5,schedule_time='20:00' where user_id=999990002;
 select * into u from bot_users where user_id=999990002;
 assert u.settings->>'location'='Freiburg';
 assert u.settings->>'repayment_pct'='2';
 assert u.settings->>'_guide_version'='1';
 assert u.weekly and u.schedule_day=0 and u.schedule_time='09:00';
 update bot_control set pilot_locked=false where id=1;
 update bot_users set settings=settings || '{"location":"Hamburg"}',weekly=false where user_id=999990002;
 select * into u from bot_users where user_id=999990002;
 assert u.settings->>'location'='Hamburg' and not u.weekly;
end $$;
rollback;
delete from bot_users where user_id=999990001;

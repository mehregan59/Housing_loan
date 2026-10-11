begin;
alter table bot_jobs add column if not exists progress_message_id bigint;
create or replace function bot_claim(p_id uuid) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare result jsonb; j bot_jobs;
begin
 select * into j from bot_jobs where id=p_id;
 if j.service='rental' and not exists(select 1 from bot_control where id=1 and rental_enabled) then return null; end if;
 result:=bot_claim_investment(p_id);
 if result is null then return null; end if;
 select * into j from bot_jobs where id=p_id;
 result:=result||jsonb_build_object('service',j.service,'progress_message_id',j.progress_message_id);
 if j.service='rental' then result:=result||jsonb_build_object('settings',j.rental_snapshot||jsonb_build_object('_guide_version',1,'language',case when j.rental_snapshot->>'language'='de' then 'de' else 'en' end)); end if;
 return result;
end $$;

revoke all on function bot_claim(uuid) from public,anon,authenticated;
grant execute on function bot_claim(uuid) to service_role;
create or replace function bot_rental_enqueue_internal(p_user bigint,p_key text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare u bot_users; c bot_control; j bot_jobs; d date;
begin
 select * into c from bot_control where id=1 for update;
 select * into u from bot_users where user_id=p_user for update;
 if not found or not u.approved or u.accepted_at is null or u.service<>'rental' then return jsonb_build_object('error','choose_rental_and_accept_first'); end if;
 if not c.enabled or not c.research_v2 or not c.rental_enabled then return jsonb_build_object('error','rental_not_enabled'); end if;
 if jsonb_typeof(u.rental_settings->'radius_km') is distinct from 'number' or coalesce(length(trim(u.rental_settings->>'location')),0)=0 or (u.rental_settings->>'radius_km')::numeric not between 0 and 300 then return jsonb_build_object('error','invalid_rental_settings'); end if;
 if not exists(select 1 from jsonb_each(u.rental_settings) where key in ('max_rent_eur','max_cold_rent_eur','max_charges_eur') and jsonb_typeof(value)='number') or exists(select 1 from jsonb_each(u.rental_settings) where key in ('max_rent_eur','max_cold_rent_eur','max_charges_eur') and value<>'null'::jsonb and (jsonb_typeof(value)<>'number' or case when jsonb_typeof(value)='number' then value::text::numeric<=0 or value::text::numeric>20000 else true end)) then return jsonb_build_object('error','invalid_rental_settings'); end if;
 if exists(select 1 from jsonb_each(u.rental_settings) where key in ('min_rooms','max_rooms') and value<>'null'::jsonb and (jsonb_typeof(value)<>'number' or case when jsonb_typeof(value)='number' then value::text::numeric<=0 or value::text::numeric>20 else true end)) then return jsonb_build_object('error','invalid_room_limits'); end if;
 if u.rental_settings->>'min_rooms' is not null and u.rental_settings->>'max_rooms' is not null and (u.rental_settings->>'min_rooms')::numeric>(u.rental_settings->>'max_rooms')::numeric then return jsonb_build_object('error','invalid_room_limits'); end if;
 if coalesce(u.rental_settings->>'furnishing','any') not in ('any','furnished','partial','unfurnished') then return jsonb_build_object('error','invalid_furnishing'); end if;
 select * into j from bot_jobs where request_key=p_key;
 if found then return jsonb_build_object('job_id',j.id,'duplicate',true); end if;
 if exists(select 1 from bot_jobs where user_id=p_user and status in ('queued','running')) then return jsonb_build_object('error','already_running'); end if;
 if exists(select 1 from bot_jobs where status='uncertain') then return jsonb_build_object('error','usage_needs_review'); end if;
 if not bot_payment_exempt(p_user) and (u.rental_trial_used_at is not null or exists(select 1 from bot_jobs where user_id=p_user and service='rental' and status='complete' and report is not null)) then return jsonb_build_object('error','rental_prices_not_ready'); end if;
 d:=(now() at time zone 'Europe/Berlin')::date;
 if c.admin_user_id is distinct from p_user and exists(select 1 from bot_jobs where user_id=p_user and service='rental' and rental_day=d) then return jsonb_build_object('error','one_rental_attempt_per_day'); end if;
 insert into bot_jobs(user_id,request_key,week_start,reserved_usd,service,rental_snapshot,rental_day)
 values(p_user,left(p_key,160),date_trunc('week',now() at time zone 'Europe/Berlin')::date,0,'rental',u.rental_settings,d) returning * into j;
 return jsonb_build_object('job_id',j.id);
end $$;

revoke all on function bot_rental_enqueue_internal(bigint,text) from public,anon,authenticated;
grant execute on function bot_rental_enqueue_internal(bigint,text) to service_role;
commit;

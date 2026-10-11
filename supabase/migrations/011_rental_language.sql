begin;
create or replace function bot_claim(p_id uuid) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare result jsonb; j bot_jobs;
begin
 select * into j from bot_jobs where id=p_id;
 if j.service='rental' and not exists(select 1 from bot_control where id=1 and rental_enabled) then return null; end if;
 result:=bot_claim_investment(p_id);
 if result is null then return null; end if;
 select * into j from bot_jobs where id=p_id;
 result:=result||jsonb_build_object('service',j.service);
 if j.service='rental' then result:=result||jsonb_build_object('settings',j.rental_snapshot||jsonb_build_object('_guide_version',1,'language',case when j.rental_snapshot->>'language'='de' then 'de' else 'en' end)); end if;
 return result;
end $$;

revoke all on function bot_claim(uuid) from public,anon,authenticated;
grant execute on function bot_claim(uuid) to service_role;
commit;

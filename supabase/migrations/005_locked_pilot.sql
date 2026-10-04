-- Apply once in Supabase SQL Editor. Locks the private pilot for every user.
-- Does not approve users, bypass the guide, start AI calls, or change quotas/budget.
begin;
alter table public.bot_control add column if not exists pilot_locked boolean not null default true;
update public.bot_control set pilot_locked=true where id=1;
alter table public.bot_users alter column settings set default '{"location":"Freiburg","country":"Germany","radius_km":150,"max_price_eur":300000,"max_loan_eur":300000,"equity_eur":10000,"min_size_m2":30,"language":"en","fixed_rate_years":30,"repayment_pct":2,"target_gross_yield_pct":null,"min_monthly_cashflow_eur":null,"max_price_per_m2":null,"areas":[],"exclude":["Erbpacht","Zwangsversteigerung"]}'::jsonb;
alter table public.bot_users alter column weekly set default true;
alter table public.bot_users alter column schedule_time set default '09:00';
create or replace function public.bot_apply_pilot_settings() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
begin
 if exists(select 1 from bot_control where id=1 and pilot_locked) then
   new.settings=(coalesce(new.settings,'{}'::jsonb)-'_edit') || '{"location":"Freiburg","country":"Germany","radius_km":150,"max_price_eur":300000,"max_loan_eur":300000,"equity_eur":10000,"min_size_m2":30,"language":"en","fixed_rate_years":30,"repayment_pct":2,"target_gross_yield_pct":null,"min_monthly_cashflow_eur":null,"max_price_per_m2":null,"areas":[],"exclude":["Erbpacht","Zwangsversteigerung"]}'::jsonb;
   new.weekly=true;
   new.schedule_day=0;
   new.schedule_time='09:00';
   new.timezone='Europe/Berlin';
 end if;
 return new;
end $$;
revoke all on function public.bot_apply_pilot_settings() from public;
drop trigger if exists bot_locked_pilot on public.bot_users;
create trigger bot_locked_pilot before insert or update on public.bot_users
for each row execute function public.bot_apply_pilot_settings();
-- Trigger updates the preset while preserving access, guide and other internal state.
update public.bot_users set settings=settings;
commit;

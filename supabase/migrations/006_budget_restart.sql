-- Starts a new bot spending period with a USD10 cap. Real costs are NOT erased.
-- Applying this file again intentionally restarts the period again.
begin;
alter table public.bot_control add column if not exists budget_period_started_at timestamptz;
do $apply$
declare name text; definition text; updated text;
begin
 foreach name in array array['public.bot_enqueue(bigint,text)','public.bot_claim(uuid)','public.bot_research_reserve(uuid)'] loop
  definition=pg_get_functiondef(name::regprocedure);
  updated=regexp_replace(definition,
   $pattern$coalesce[(]started_at,created_at[)][[:space:]]*>=[[:space:]]*date_trunc[(]'month',now[(][)] at time zone 'UTC'[)] at time zone 'UTC'$pattern$,
   $replacement$coalesce(started_at,created_at) >= greatest(c.budget_period_started_at, date_trunc('month',now() at time zone 'UTC') at time zone 'UTC')$replacement$,'g');
  if updated=definition and position('c.budget_period_started_at' in definition)=0 then
    raise exception 'Budget function did not match: %',name;
  end if;
  execute updated;
 end loop;
end $apply$;
update public.bot_control set monthly_budget_usd=10,budget_period_started_at=now() where id=1;
commit;
select monthly_budget_usd,budget_period_started_at from public.bot_control where id=1;

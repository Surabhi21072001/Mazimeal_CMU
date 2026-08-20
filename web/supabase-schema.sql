create table if not exists public.weekly_plans (
  user_key text primary key,
  planner_state jsonb not null,
  updated_at timestamptz not null default timezone('utc', now())
);

alter table public.weekly_plans enable row level security;

create policy "Allow anon read weekly plans"
on public.weekly_plans
for select
to anon
using (true);

create policy "Allow anon write weekly plans"
on public.weekly_plans
for insert
to anon
with check (true);

create policy "Allow anon update weekly plans"
on public.weekly_plans
for update
to anon
using (true)
with check (true);

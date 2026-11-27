-- Brands @mentioned in contests of followed accounts (co-organised giveaways).
-- Filled by the collector; reviewed by hand: to follow one, add it to `accounts`;
-- to dismiss it for good, add it to `accounts` with enabled = false.
-- Private table: no access for the app (no policy, no grant).

create table public.account_suggestions (
    username      text primary key check (username ~ '^[a-z0-9._]{1,30}$'),
    mentioned_by  text[] not null default '{}',     -- followed accounts that mentioned it
    mention_count integer not null default 0,       -- = cardinality(mentioned_by), for sorting
    first_seen_at timestamptz not null default now(),
    last_seen_at  timestamptz not null default now()
);

alter table public.account_suggestions enable row level security;
revoke all on public.account_suggestions from anon, authenticated;

-- Same signature and result as before (number of purged posts); also forgets suggestions
-- not seen for 30 days. Data-modifying CTEs always run, even if not referenced.
create or replace function public.purge_old_posts() returns integer
language sql
security invoker
set search_path = ''
as $$
    with stale_suggestions as (
        delete from public.account_suggestions
        where last_seen_at < now() - interval '30 days'
        returning 1
    ),
    deleted as (
        delete from public.posts
        where published_at < now() - interval '30 days'
           or deadline < current_date
        returning 1
    )
    select count(*)::integer from deleted;
$$;

revoke execute on function public.purge_old_posts() from public, anon, authenticated;

-- Followed accounts: Instagram Business/Creator accounts whose posts are collected through
-- Business Discovery (in addition to hashtag search). Edit the list in Supabase → Table Editor.

create table public.accounts (
    username           text primary key check (username ~ '^[a-z0-9._]{1,30}$'),  -- without '@', lowercase
    enabled            boolean not null default true,
    note               text,
    added_at           timestamptz not null default now(),
    last_collected_at  timestamptz,
    last_error         text            -- e.g. personal (non-business) account, renamed account
);

alter table public.accounts enable row level security;
revoke all on public.accounts from anon, authenticated;
grant select (username) on public.accounts to anon, authenticated;   -- the app only needs the names

create policy "enabled accounts are public"
    on public.accounts for select
    to anon, authenticated
    using (enabled);

create index posts_author_username_idx on public.posts (author_username)
    where author_username is not null;

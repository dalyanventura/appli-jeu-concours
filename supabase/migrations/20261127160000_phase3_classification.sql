-- Phase 3: the collector now fills contest_score / categories / entry_type / deadline.
-- The app only sees posts that look like real contests. is_hidden stays for manual moderation only.

drop policy "visible posts are public" on public.posts;
create policy "visible posts are public"
    on public.posts for select
    to anon, authenticated
    using (not is_hidden and contest_score >= 0.5);   -- 0.5 = detect.VISIBLE_THRESHOLD

drop index if exists public.posts_published_at_idx;
create index posts_published_at_idx on public.posts (published_at desc)
    where not is_hidden and contest_score >= 0.5;

-- Partner suggestions are checked with Business Discovery before being worth a look.
alter table public.account_suggestions
    add column checked_at      timestamptz,
    add column is_business     boolean,          -- null: not checked yet; false: personal / unknown account
    add column recent_contests integer;          -- contest posts among its last 25 (when is_business)

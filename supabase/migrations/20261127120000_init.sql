-- Initial schema: contests collected from Instagram hashtag search.
-- Apply in Supabase: SQL Editor → paste → Run (or `supabase db push` with the CLI).

-- ---------------------------------------------------------------------------
-- Categories (source of truth: collector/config/categories.yaml; mirrored here
-- so the Android app can fetch labels and order)
-- ---------------------------------------------------------------------------
create table public.categories (
    slug        text primary key,
    label       text not null,
    sort_order  smallint not null default 0
);

insert into public.categories (slug, label, sort_order) values
    ('mode_bijoux',        'Mode & bijoux',           10),
    ('beaute_bien_etre',   'Beauté & bien-être',      20),
    ('jeux_video',         'Jeux vidéo',              30),
    ('jeux_societe',       'Jeux de société',         40),
    ('high_tech',          'High-tech',               50),
    ('deco_maison',        'Déco & maison',           60),
    ('bricolage',          'Bricolage & jardin',      70),
    ('cinema_series',      'Cinéma & séries',         80),
    ('livres',             'Livres',                  90),
    ('gastronomie',        'Gastronomie',            100),
    ('voyage',             'Voyage',                 110),
    ('sorties_evenements', 'Sorties & événements',   120),
    ('sport',              'Sport',                  130),
    ('enfants_famille',    'Enfants & famille',      140),
    ('animaux',            'Animaux',                150),
    ('bons_achat',         'Bons d''achat & argent', 160),
    ('autre',              'Autre',                  999);

-- ---------------------------------------------------------------------------
-- Posts
-- ---------------------------------------------------------------------------
create table public.posts (
    ig_media_id      text primary key,
    permalink        text not null,
    caption          text,
    caption_hash     text not null unique,            -- normalized caption hash, dedupes reposts
    media_url        text,                            -- expires (oe= param); may be null
    media_type       text not null check (media_type in ('IMAGE', 'VIDEO', 'CAROUSEL_ALBUM')),
    author_username  text,                            -- not provided by hashtag search
    published_at     timestamptz not null,
    collected_at     timestamptz not null default now(),
    source_hashtags  text[] not null default '{}',
    categories       text[] not null default '{}',
    entry_type       text not null default 'instagram'
                     check (entry_type in ('instagram', 'purchase', 'in_store', 'external_form', 'other')),
    deadline         date,
    location         text,
    contest_score    real not null default 0 check (contest_score between 0 and 1),
    is_hidden        boolean not null default false   -- set by collector (low score) or moderation
);

create index posts_published_at_idx on public.posts (published_at desc) where not is_hidden;
create index posts_categories_idx   on public.posts using gin (categories);
create index posts_deadline_idx     on public.posts (deadline) where deadline is not null;

-- ---------------------------------------------------------------------------
-- Collector internals (never exposed to the app)
-- ---------------------------------------------------------------------------
create table public.hashtags (
    tag                text primary key,              -- without '#', lowercase
    ig_hashtag_id      text,                          -- cached result of ig_hashtag_search
    enabled            boolean not null default true,
    last_collected_at  timestamptz
);

create table public.collector_runs (
    id              bigint generated always as identity primary key,
    started_at      timestamptz not null default now(),
    finished_at     timestamptz,
    status          text not null default 'running' check (status in ('running', 'success', 'error')),
    posts_fetched   integer not null default 0,
    posts_upserted  integer not null default 0,
    error           text
);

-- ---------------------------------------------------------------------------
-- Row Level Security: the app (anon / publishable key) may only READ visible
-- posts and categories. The collector uses the secret key, which bypasses RLS.
-- ---------------------------------------------------------------------------
alter table public.categories     enable row level security;
alter table public.posts          enable row level security;
alter table public.hashtags       enable row level security;
alter table public.collector_runs enable row level security;

revoke all on public.categories, public.posts, public.hashtags, public.collector_runs
    from anon, authenticated;
grant select on public.categories, public.posts to anon, authenticated;

create policy "categories are public"
    on public.categories for select
    to anon, authenticated
    using (true);

create policy "visible posts are public"
    on public.posts for select
    to anon, authenticated
    using (not is_hidden);

-- ---------------------------------------------------------------------------
-- Retention: drop posts older than 30 days or whose deadline has passed.
-- Called by the collector at the end of each run (service role only).
-- ---------------------------------------------------------------------------
create function public.purge_old_posts() returns integer
language sql
security invoker
set search_path = ''
as $$
    with deleted as (
        delete from public.posts
        where published_at < now() - interval '30 days'
           or deadline < current_date
        returning 1
    )
    select count(*)::integer from deleted;
$$;

revoke execute on function public.purge_old_posts() from public, anon, authenticated;

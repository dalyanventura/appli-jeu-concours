# CLAUDE.md — Appli Jeu Concours

## Objectif du projet

Application Android qui recense les jeux concours publiés sur Instagram.
Un collecteur côté serveur interroge l'API Instagram toutes les heures par deux sources :
des **hashtags** (#concours, #jeuconcours…) et une liste de **comptes suivis** (marques dont les
amis attendent les concours — c'est ainsi qu'ils les découvrent aujourd'hui, via leur fil, plus que
par hashtag). Il classe chaque publication par thème
(mode, jeux vidéo, déco, cinéma…) et la stocke. L'app affiche ce flux avec un filtre par thème
et un tri par date de publication. Elle ne participe pas aux concours à la place de l'utilisateur :
elle renvoie vers la publication Instagram d'origine.

Public visé : un petit groupe d'amis au départ, puis peut-être une publication sur le Play Store.
L'interface est en **français**.

## Architecture

```
[Cron horaire] → collector/ (Python) → API Instagram Graph
                       │                 ├─ hashtag search  (posts sans auteur)
                       │                 └─ business discovery (comptes de la table `accounts`, avec auteur)
                       ├─ filtre (est-ce vraiment un concours ?) + classification par thème
                       ▼
                 Supabase (PostgreSQL)  ←── lecture seule (RLS) ──  android/ (Kotlin + Compose)
```

- **L'app Android n'appelle jamais l'API Instagram directement.** Le token Meta et les quotas
  restent côté serveur. L'app lit seulement la base, avec la clé publique de Supabase et des
  politiques RLS en lecture seule.
- Le collecteur est **idempotent** : un upsert sur `ig_media_id` permet de relancer un passage
  sans créer de doublons.

## Contraintes de l'API Instagram (à lire avant de toucher au collecteur)

- On utilise l'**Instagram Graph API** (Facebook Login for Business). Il faut un **compte Instagram
  professionnel (Business ou Creator) relié à une Page Facebook**, ainsi qu'une app Meta avec la
  fonctionnalité **Instagram Public Content Access**. Cette fonctionnalité exige une **App Review**
  de Meta : politique de confidentialité, screencast, et parfois une vérification d'entreprise.
  L'ancienne Basic Display API n'existe plus.
- Endpoints :
  1. `GET /ig_hashtag_search?user_id={ig-user-id}&q={tag}` → ID du hashtag (à mettre en cache
     dans la table `hashtags`, car l'ID ne change pas).
  2. `GET /{hashtag-id}/recent_media?user_id=...&fields=id,caption,media_type,media_url,permalink,timestamp`
     → publications des dernières 24 h, paginées par 50.
  3. `GET /{ig-user-id}?fields=business_discovery.username({compte}){username,media.limit(25){…}}`
     → derniers posts d'un compte **Business ou Creator** (les comptes personnels et ceux à
     restriction d'âge échouent : l'erreur est notée dans `accounts.last_error` et le passage
     continue). Ne consomme **pas** le quota de 30 hashtags, mais 1 appel de la limite de
     plateforme (`X-App-Usage`) par compte → au plus 60 comptes par passage, en rotation
     (les moins récemment lus d'abord). Seuls les posts qui passent `looks_like_contest()` sont gardés.
     Permissions du token : `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement`
     (+ `ads_read` si le rôle sur la Page vient de Business Manager). Sans elles : erreur `(#10)`
     → `PermissionDeniedError`, la lecture des comptes s'arrête sans noter d'erreur par compte.
- **Limite stricte : 30 hashtags uniques par compte IG sur une fenêtre glissante de 7 jours.**
  Il faut garder une liste fixe d'au plus environ 25 hashtags (dans `collector/config/hashtags.yaml`)
  et ne jamais en générer dynamiquement. Les appels `recent_media`/`top_media` comptent dans ce
  plafond même avec un ID en cache : ne jamais tester de hashtags « pour voir ».
- **Usages autorisés par Meta** pour Public Content Access : campagnes de marque, support client,
  identification des participants à un concours, analyse de sentiment. Un agrégateur de concours
  tiers n'entre pas clairement dans ces cas : risque principal de refus en App Review.
- Phase 0 : `python collector/scripts/probe_api.py [hashtag]` vérifie token, compte IG et recherche.

### Constats de la phase 0 (27/11/2026, #jeuconcours, 50 posts, API v27.0, app en mode Développement)

- La recherche par hashtag **fonctionne en mode Développement** avec le compte admin de l'app.
- Volume : 50 posts en ~50 min pour le seul #jeuconcours (jour de Black Friday) → prévoir
  plusieurs pages par hashtag et par passage.
- **Pas de nom d'auteur** dans la réponse (`username`/`owner` non fournis pour les médias hashtag) :
  l'app ne peut pas afficher « par @compte » sans source supplémentaire (oEmbed, mentions de la légende).
- `media_url` absent sur 8/50 (uniquement des reels). Pour les vidéos, `media_url` est un `.mp4`
  (pas de miniature) → vignette par défaut selon le thème.
- Les `media_url` **expirent** (paramètre `oe=`) et un post sort de `recent_media` après 24 h :
  on ne peut pas rafraîchir l'URL ensuite. L'app doit gérer une image cassée proprement.
- Répartition : ~56 % vrais concours Instagram (abonnement/like/identification), ~28 % concours hors
  Instagram (achat, magasin, formulaire, appli), ~16 % bruit (annonces de gagnants, teasers, pubs,
  agrégateurs concurrents). → `detect.py` doit produire aussi un `entry_type`
  (`instagram`, `purchase`, `in_store`, `external_form`) pour filtrer côté app.
- Doublons : un même annonceur publie la même légende plusieurs fois → dédoublonner sur un hash
  de légende normalisée en plus de `ig_media_id`.
- Dates limites presque toujours explicites en français (« jusqu'au 29 novembre 2026 à 23h59 »,
  « tirage le 07/12 ») → extraction par règles faisable, LLM en repli.
- Beaucoup de concours **locaux** (magasin, ville) → champ `location` utile (filtre « près de moi »
  ou « national » plus tard).
- **Le lien `paging.next` contient le token d'accès** : ne jamais le logger ni l'enregistrer.
- Quota d'appels : environ 200 appels par heure et par utilisateur. Le collecteur suit l'en-tête
  `X-Business-Use-Case-Usage` et ralentit au-delà de 80 %.
- Les publications des comptes privés et les Stories ne sont pas accessibles. `media_url` peut
  être absent (contenu protégé par des droits d'auteur, certains carrousels) : il faut prévoir une vignette par défaut.
- Le **token** (utilisateur Facebook Login) a deux échéances : `expires_at` (~60 jours) et
  `data_access_expires_at` (90 jours après la dernière connexion de l'utilisateur). Ré-échanger le
  token ne repousse pas la seconde : **pas de rafraîchissement automatique**. Le workflow quotidien
  `token-check.yml` (`python -m collector.ig_token check`, sans secret d'app : le token s'inspecte
  lui-même) échoue à J-7, et GitHub envoie alors un e-mail. Renouvellement sur le PC :
  `python -m collector.ig_token renew` (token collé depuis Graph API Explorer → échange longue durée
  avec `META_APP_ID`/`META_APP_SECRET` du `.env` local → met à jour `.env` et le secret GitHub via `gh`).
  Piste pour supprimer cette corvée : un token d'utilisateur système (Business Manager) sans expiration,
  à tester avec la recherche par hashtag.
- **Pas de scraping** (ni Instaloader, ni navigateur headless, etc.) : c'est contraire aux CGU de
  Meta et cela met en danger le compte et l'app. Si l'App Review est refusée, on en parle au
  propriétaire du projet plutôt que de contourner.
- Respect des droits : on affiche la légende, une vignette et un lien `permalink` vers Instagram.
  On ne ré-héberge pas les images. On supprime les publications de plus de 30 jours, ou dès que
  leur date limite est passée.

## Stack

| Partie       | Choix                                                                   |
|--------------|-------------------------------------------------------------------------|
| Collecteur   | Python 3.12+, `httpx` (Graph API et REST Supabase/PostgREST directement, pas de `supabase-py`), `pyyaml`, tests `pytest` + `httpx.MockTransport` |
| Planification| GitHub Actions, dépôt **public** (minutes illimitées) : `collect.yml` (cron `17 * * * *`), `token-check.yml` (quotidien + keep-alive anti-désactivation à 60 jours), `tests.yml` (push) |
| Base         | Supabase (PostgreSQL), migrations SQL dans `supabase/migrations/`       |
| Classification | Règles par mots-clés d'abord ; LLM en option (Claude Haiku) pour les cas ambigus et l'extraction de la date limite |
| Android      | Kotlin, Jetpack Compose, Material 3, architecture MVVM, Hilt, Retrofit/Ktor ou `supabase-kt`, Coil, Paging 3, Room (cache hors ligne), WorkManager (notifications) |
| minSdk / targetSdk | 26 / dernière version stable                                    |

## Structure du dépôt (cible)

```
collector/
  src/collector/
    config.py         # .env / variables d'environnement, validation de hashtags.yaml
    instagram.py      # client Graph API (pagination par curseur, quotas, retries)
    normalize.py      # média → ligne `posts`, caption_hash, dédoublonnage (merge_batch), fold(), partner_mentions()
    analyze.py        # colonnes de classification d'un post (detect + classify + deadline)
    reclassify.py     # recalcule la classification de tous les posts en base
    detect.py         # est-ce un concours ? (score par mots-clés)
    classify.py       # attribution d'un ou plusieurs thèmes
    deadline.py       # extraction de la date limite depuis la légende
    store.py          # REST Supabase (upsert posts/hashtags, collector_runs, purge)
    main.py           # un passage horaire + garde-fou des 30 hashtags/7 jours
    ig_token.py       # santé du token (CI quotidienne) et renouvellement guidé (local)
  config/hashtags.yaml
  config/categories.yaml   # thème → mots-clés / hashtags
  tests/
supabase/migrations/
android/              # projet Gradle (app/)
.github/workflows/   # collect.yml (horaire), token-check.yml (quotidien), tests.yml (push)
```

Secrets GitHub (Settings → Secrets → Actions) : `IG_ACCESS_TOKEN`, `IG_USER_ID`, `SUPABASE_URL`,
`SUPABASE_SECRET_KEY`. Le dépôt est public : les logs des Actions aussi (GitHub masque les secrets,
`RedactingFormatter` aussi) ; ne jamais y imprimer de données personnelles.

## Modèle de données (table `posts`)

`ig_media_id` (PK, texte), `permalink`, `caption`, `media_url`, `media_type`, `author_username`
(si disponible), `published_at` (timestamptz, issu de `timestamp`), `collected_at`, `source_hashtags` (text[]),
`categories` (text[]), `deadline` (date, nullable), `contest_score` (réel 0–1), `is_hidden` (bool).
Index sur `published_at DESC` et index GIN sur `categories`.

Colonnes ajoutées après la phase 0 : `entry_type` (text), `caption_hash` (text, unique),
`location` (text, nullable).

`author_username` n'est renseigné que pour les posts lus via un compte suivi (ou trouvés à la fois
par hashtag et par compte). Il n'est envoyé à l'upsert que lorsqu'il est connu, pour ne jamais
l'effacer. Table `accounts` (`username` PK au format `^[a-z0-9._]{1,30}$`, `enabled`, `note`,
`last_collected_at`, `last_error`) : éditée à la main dans Supabase → Table Editor ; l'app ne peut
lire que la colonne `username` des comptes actifs.

Table `account_suggestions` (privée, invisible pour l'app) : marques @mentionnées dans les concours
des comptes suivis (concours co-organisés, « double jeu concours » : c'est ainsi que les amies
découvrent de nouvelles marques). `mentioned_by` = comptes suivis qui l'ont citée, `mention_count`
pour trier. Les annonces de gagnants sont ignorées (elles citent des particuliers), les comptes déjà
dans `accounts` aussi ; une suggestion non revue depuis 30 jours est purgée. **L'API retire le « @ »
des mentions dans les légendes** (« Follow marque_a & marque_b ») : `partner_mentions()` reconnaît les
comptes par leur contexte (« abonne-toi à », « follow », « x », « en partenariat avec », une ligne par
compte après « nos comptes : »), ce qui laisse passer des mots courants. Chaque passage vérifie donc
jusqu'à 10 suggestions avec Business Discovery : `is_business` (null = pas encore vérifiée, false =
compte perso ou inexistant) et `recent_contests` (concours parmi ses 25 derniers posts sur 30 jours).
Trier par `is_business`, `recent_contests`, `mention_count`. Validation à la main :
l'ajouter à `accounts` (suivre) ou l'y ajouter avec `enabled = false` (refuser définitivement).
Jamais d'ajout automatique dans `accounts` (quota d'appels, et risque de suivre des particuliers).

Filtre par compte dans l'app (phase 5) : liste des comptes suivis + recherche sur `author_username`.
Les posts venus uniquement d'un hashtag n'ont pas d'auteur et n'apparaissent pas dans ce filtre
(piste ultérieure : oEmbed, qui exige lui aussi une App Review).

Thèmes initiaux (slug → libellé) : `mode_bijoux`, `beaute_bien_etre`, `jeux_video`, `jeux_societe`,
`high_tech`, `deco_maison`, `bricolage`, `cinema_series`, `livres`, `gastronomie`, `voyage`,
`sorties_evenements`, `sport`, `enfants_famille`, `animaux`, `bons_achat`, `autre`.
Ces thèmes sont définis uniquement dans `collector/config/categories.yaml`, et l'app récupère la liste depuis la base.

## Commandes

```bash
# Collecteur (venv dans collector/.venv ; sous Windows : .venv\Scripts\python)
cd collector && python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
.venv/Scripts/python -m collector.main --dry-run   # appelle l'API et lit la base, n'écrit rien
.venv/Scripts/python -m collector.main             # passage réel
.venv/Scripts/python -m collector.reclassify [--dry-run]   # après un changement de règles (sans appel Instagram)
.venv/Scripts/python -m collector.ig_token check   # jours restants avant expiration du token
.venv/Scripts/python -m collector.ig_token renew   # renouvellement guidé (.env + secret GitHub)
.venv/Scripts/python scripts/export_sample.py      # posts en base → probe_output/posts.jsonl (git-ignoré)
.venv/Scripts/python scripts/review_rules.py       # applique les règles → probe_output/review.csv + bilan

# Android (Windows : gradlew.bat)
cd android && ./gradlew assembleDebug
./gradlew test
./gradlew lint
```

## Conventions

- Code, noms de variables et commits en anglais ; textes de l'UI en français dans `strings.xml`
  (pas de chaînes en dur dans Compose).
- Secrets (`IG_ACCESS_TOKEN`, `IG_USER_ID`, `META_APP_SECRET`, `SUPABASE_SECRET_KEY`,
  `ANTHROPIC_API_KEY`) : variables d'environnement ou secrets GitHub, jamais commités. Un fichier
  `.env.example` documente les noms. La clé secrète Supabase (`sb_secret_…` / `service_role`) ne doit
  jamais se trouver dans l'app Android, qui n'utilise que `SUPABASE_PUBLISHABLE_KEY`.
- Schéma : toute modification passe par un nouveau fichier dans `supabase/migrations/`
  (jamais d'édition d'une migration déjà appliquée). Vérification RLS : `python collector/scripts/check_db.py`.
- Les tests du collecteur utilisent des réponses API enregistrées (`tests/fixtures/*.json`) et
  n'appellent jamais la vraie API.
- Collecteur : l'upsert envoie les colonnes de collecte (`ig_media_id`, `permalink`, `caption`,
  `caption_hash`, `media_url`, `media_type`, `published_at`, `source_hashtags`, `author_username` si
  connu) **et** la classification (`contest_score`, `categories`, `entry_type`, `deadline`), calculée
  de façon déterministe à chaque passage. **`is_hidden` n'est jamais envoyé** : il est réservé à la
  modération manuelle. Visibilité côté app = `not is_hidden and contest_score >= 0.5` (politique RLS,
  miroir de `detect.VISIBLE_THRESHOLD` : changer les deux ensemble, par une migration). Après une
  modification des règles : `collector.reclassify`. Le garde-fou de quota s'appuie
  sur `hashtags.last_collected_at`, que `--dry-run` ne met pas à jour : ne pas changer la liste de
  hashtags juste après un dry-run sans en tenir compte.
- Toute modification de `detect.py` ou de `classify.py` doit être accompagnée de cas de test
  tirés de vraies légendes, anonymisées.
- Dates stockées en UTC et affichées dans le fuseau du téléphone.

## Détection (phase 3) — vocabulaire relevé par une participante

Signaux forts, surtout combinés : « jeu concours », consignes de participation (« like la
publication », « commente », « identifie 2 amies », « abonne-toi à @… », « reposte en story » /
« sur ton compte », « enregistre le post »), date de tirage (« tirage au sort le … », « nom du
gagnant annoncé le … » → aussi source de `deadline`). Signal négatif : annonce de résultat
(« la gagnante est @… », « bravo à @… »). Une consigne seule (« like », « commente ») n'est pas un
concours : il faut une combinaison.

Implémentation (`detect.py`) : score additif — mot « concours » & co. (+0.4, hors hashtags), chaque
type de consigne (like, abonnement, identification, commentaire, partage, enregistrement : +0.12,
max 3), « pour participer » (+0.1), date de tirage/fin (+0.12), lot (+0.08) ; pénalités : annonce de
gagnant (−0.45), agrégateur ou « mes gains » (−0.6), concours d'examen / vote (−0.5), arnaque (−0.9),
teaser sans consignes (−0.2). Sans mot « concours », ou légende majoritairement non française :
plafonné à 0.3. `entry_type` : achat > magasin (bulletin, urne) > Instagram (≥ 2 consignes) >
formulaire externe (lien en bio, inscription) > `other`.
Premier réglage le 27/11/2026 sur 537 posts réels : ~75 % affichés, ~80 % d'entre eux avec date limite.
`deadline.py` : fin de participation > date de tirage > première date future ; « 24h pour participer »,
« tirage dimanche » (jour suivant) ; année déduite de la date de publication.

## Points de vigilance

- Faux positifs : beaucoup de posts utilisent #concours sans être des concours (concours photo,
  pubs, comptes de spam ou d'arnaque du type « cliquez sur le lien en bio pour réclamer votre lot »). Il vaut mieux
  sous-afficher que montrer des arnaques ; `contest_score` sert de seuil.
- Play Store : politique de confidentialité obligatoire, formulaire « Sécurité des données »,
  et le nom ou l'icône ne doivent pas reprendre la marque Instagram.

"""Turn Graph API media into `posts` rows and deduplicate them."""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from collections.abc import Iterable

from collector.instagram import parse_timestamp

log = logging.getLogger(__name__)

VALID_MEDIA_TYPES = {"IMAGE", "VIDEO", "CAROUSEL_ALBUM"}


def caption_hash(caption: str | None, media_id: str) -> str:
    """Hash of the caption reduced to letters and digits.

    NFKC folds "𝗝𝗘𝗨" into "JEU"; dropping punctuation, emoji and whitespace makes
    "500 €" / "500€" or ' / ’ variants of the same repost collide on purpose.
    """
    text = unicodedata.normalize("NFKC", caption or "").casefold()
    basis = "".join(ch for ch in text if ch.isalnum())
    if not basis:
        basis = f"id:{media_id}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


CONTEST_KEYWORDS = re.compile(
    r"concours|giveaway|tirage au sort|tir[ée]e?s? au sort|[àa] gagner|remporte[rz]?|"
    r"tente[rz]? (votre|ta) chance|gagnant|fai(?:t|sons|re) gagner",
    re.IGNORECASE,
)

def fold(text: str | None) -> str:
    """Lowercase, NFKC (𝗕𝗢𝗟𝗗 → bold), no accents, straight apostrophes: for keyword matching."""
    text = unicodedata.normalize("NFKC", text or "").casefold().replace("’", "'")
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))


def looks_like_contest(caption: str | None) -> bool:
    """Cheap pre-filter for posts from followed accounts (hashtag posts are kept anyway).

    Intentionally broad: phase 3's detect.py does the real scoring.
    """
    if not caption:
        return False
    return bool(CONTEST_KEYWORDS.search(unicodedata.normalize("NFKC", caption)))


# The Graph API returns captions with the "@" of mentions removed ("Follow marque_a & marque_b"),
# so partner accounts are recognised from their context instead.
WINNER_ANNOUNCEMENT = re.compile(
    r"gagnant(?:e|s|es)? (?:est|sont|du|de|:)|bravo [àa]|f[ée]licitations? [àa]|"
    r"r[ée]sultats? du (?:jeu[ -])?concours",
    re.IGNORECASE,
)
FOLLOW_CUE = re.compile(r"abonne[sz]?[- ](?:toi|vous)|abonn[ée]e?s?(?:\(e\))? (?:à|a|aux)|abonne[rz]? (?:à|a|aux)\b"
                        r"|\bfollow(?:ez)?\b|\bsuis[- ](?:moi|nous)?|\bsuivez\b|\bsuivre\b", re.IGNORECASE)
PARTNER_CUE = re.compile(r"en partenariat avec|en collab\w* avec|je m'associe (?:à|a|avec)|avec la (?:jolie )?marque"
                         r"|(?<=\w )x(?= \w)", re.IGNORECASE)
# usernames are shown lowercase; capitalised words are prose
HANDLE = re.compile(r"(?<![\w.@#/])@?([a-z0-9._]*[a-z][a-z0-9._]*)(?![\w@/'-])")
URL = re.compile(r"https?://\S+|www\.\S+")
NOT_HANDLES = set("""
a au aux avec bien bio bonne by ce celle cette chance chez ci commentaire commentaires compte comptes
d de des deux du elle elles en est et etre facebook fois ici il ils instagram insta je l la le les leur
leurs lien like likez liker ma marque marques mes moi mon ne ni nos notre nous on ou page pages par
partenaire partenaires pas plus post pour publication que qui sa ses site son sont story sur ta te tes
the toi ton tous tout toutes trois tu un une via vos votre vous x and our account accounts both all
to and this et_ also aussi ainsi ses afin celui organisateurs jolie belle donc car or mais nouveau
nouvelle participer identifie identifiez tague taguez tag commente commentez partage partagez repost
enregistre aime aimez abonne abonnez follow suivez suis suivre ami amis amie amies personne personnes
tiktok youtube https http www com fr gratuit gratuitement vite ici-bas ensuite puis et/ou
activez attendons autrices auteurs aventure beaux boutiques chien chat curieuse curieux dessert disant dit
donne faire fan grande grand heureuse heureux indications invitations joie jour locaux logiquement
manquer manquez mentionnez moins offert one parent parents parti participe podcast proches ravie ravi
reproduire restez rien sans soutenir tellement tenter tentez titres train travail trop jeu concours
tirage tirages gagner remporter cadeau cadeaux offre offrir surprise super lui lors dans depuis enfin
envie savoir pouvoir peux rester sort temps tour week vivre voulez seront serez prochains prochaines
aucun aucune case cils coffret double doubler fer feu gamme joli lancement lettre lettres lieux magie
mise peine permettre pose produits projets quotidien recettes remercier sessions sociaux soutien
univers calendrier chances jouer partager comments friend crew two art associer abonnements abonner
activer notifications notif cloche mensuelle annuels enthousiasme correspondance contente aimeriez
messages ouverture atteints accouchement artisanale auteure extensions issues photo
""".split())


def _handles(fragment: str) -> list[str]:
    """Account-looking tokens. A plain word ("cookut") is only trusted as the first token after
    the cue; later ones must look like handles (contain ".", "_" or a digit)."""
    out = []
    for token in HANDLE.findall(fragment):
        token = token.strip(".")
        if len(token) < 3 or token in NOT_HANDLES or token.isdigit():
            continue
        if out or not re.search(r"[._0-9]", token):
            if out and not re.search(r"[._0-9]", token):
                continue
        out.append(token)
    return out


def partner_mentions(caption: str | None, author: str) -> set[str]:
    """Accounts to follow / co-organisers named in a followed account's contest post.

    "Follow marque_a & marque_b", "Abonne-toi à nos comptes :\n marque_a\n marque_b",
    "JEU CONCOURS x marque_b", "en partenariat avec marque_b", "@marque_b".
    Winner announcements are skipped (they name individuals, not brands).
    """
    if not caption:
        return set()
    text = URL.sub(" ", unicodedata.normalize("NFKC", caption).replace("‌", "").replace("’", "'"))
    if WINNER_ANNOUNCEMENT.search(text):
        return set()
    found = {m.lower().strip(".") for m in re.findall(r"(?<![\w.])@([A-Za-z0-9._]{1,30})", text)}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        partner = PARTNER_CUE.search(line)
        if partner:
            found.update(_handles(line[partner.end():])[:1])
        follow = FOLLOW_CUE.search(line)
        if not follow:
            continue
        rest = re.split(r"[!?;]|\.\s", line[follow.end():])[0]
        handles = _handles(rest)
        if handles:
            found.update(handles)
            continue
        # "Abonnez-vous à nos deux comptes :" followed by one account per line
        for nxt in (l.strip(" \t-•·*>→✨🎁❤️💙🤍🖤") for l in lines[i + 1:i + 5]):
            if not nxt:
                continue
            words = _handles(nxt)
            if len(words) != 1 or len(nxt.split()) != 1:
                break
            found.add(words[0])
    return {m for m in found if 3 <= len(m) <= 30 and m != author and m not in NOT_HANDLES}


def to_row(item: dict, tag: str | None = None, author: str | None = None) -> dict | None:
    """Graph API media → `posts` row (collection columns only), or None if unusable.

    `tag`: hashtag it was found under; `author`: followed account it was read from.
    `author_username` is only present when known, so an upsert never erases it.
    """
    media_id, permalink, timestamp = item.get("id"), item.get("permalink"), item.get("timestamp")
    media_type = item.get("media_type")
    if not (media_id and permalink and timestamp) or media_type not in VALID_MEDIA_TYPES:
        log.info("Publication ignorée (champs manquants ou type %r) : %s", media_type, media_id)
        return None
    row = {
        "ig_media_id": media_id,
        "permalink": permalink,
        "caption": item.get("caption"),
        "caption_hash": caption_hash(item.get("caption"), media_id),
        "media_url": item.get("media_url"),
        "media_type": media_type,
        "published_at": parse_timestamp(timestamp).isoformat(),
        "source_hashtags": [tag] if tag else [],
    }
    if author:
        row["author_username"] = author
    return row


def merge_batch(rows: Iterable[dict], existing: Iterable[dict] = ()) -> list[dict]:
    """Deduplicate one run's rows against each other and against posts already stored.

    - same ig_media_id seen under several hashtags → one row, hashtags merged;
    - same caption_hash within the batch → keep the oldest post (the original);
    - caption_hash already stored under another ig_media_id → drop (repost);
    - ig_media_id already stored → merge its stored hashtags into the row.
    """
    by_id: dict[str, dict] = {}
    for row in rows:
        current = by_id.get(row["ig_media_id"])
        if current is None:
            by_id[row["ig_media_id"]] = {**row, "source_hashtags": set(row["source_hashtags"])}
        else:
            current["source_hashtags"] |= set(row["source_hashtags"])
            if row.get("author_username"):
                current["author_username"] = row["author_username"]

    by_hash: dict[str, dict] = {}
    for row in sorted(by_id.values(), key=lambda r: (r["published_at"], r["ig_media_id"])):
        kept = by_hash.setdefault(row["caption_hash"], row)
        if kept is not row:
            kept["source_hashtags"] |= row["source_hashtags"]

    existing = list(existing)
    owner_of_hash = {e["caption_hash"]: e["ig_media_id"] for e in existing}
    stored_tags = {e["ig_media_id"]: set(e.get("source_hashtags") or []) for e in existing}

    result = []
    for row in by_hash.values():
        owner = owner_of_hash.get(row["caption_hash"])
        if owner is not None and owner != row["ig_media_id"]:
            continue
        tags = row["source_hashtags"] | stored_tags.get(row["ig_media_id"], set())
        result.append({**row, "source_hashtags": sorted(tags)})
    return result

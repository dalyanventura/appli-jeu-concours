import pytest

from collector.normalize import caption_hash, looks_like_contest, merge_batch, partner_mentions, to_row


@pytest.mark.parametrize("caption", [
    "🎁 JEU CONCOURS 🎁", "Giveaway time!", "Tirage au sort le 12/12", "Un sac à gagner",
    "Tentez votre chance", "Pour remporter ce coffret", "𝗖𝗢𝗡𝗖𝗢𝗨𝗥𝗦 de Noël",
])
def test_contest_prefilter_accepts(caption):
    assert looks_like_contest(caption)


@pytest.mark.parametrize("caption", [None, "", "Nouvelle collection disponible", "Black Friday -30 %"])
def test_contest_prefilter_rejects(caption):
    assert not looks_like_contest(caption)


def test_to_row_only_sets_author_key_when_known():
    item = {"id": "1", "permalink": "p", "timestamp": "2026-11-27T11:00:00+0000", "media_type": "IMAGE"}
    assert "author_username" not in to_row(item, "t")
    assert to_row(item, author="compte")["author_username"] == "compte"


def by_id(items: list[dict]) -> dict[str, dict]:
    return {item["id"]: item for item in items}


def test_reposts_with_spacing_and_punctuation_variants_share_a_hash(sample_media):
    media = by_id(sample_media)
    assert caption_hash(media["1003"]["caption"], "1003") == caption_hash(media["1004"]["caption"], "1004")


def test_math_bold_unicode_is_folded():
    assert caption_hash("𝗝𝗘𝗨 𝗖𝗢𝗡𝗖𝗢𝗨𝗥𝗦 !", "a") == caption_hash("Jeu concours", "b")


def test_accents_are_significant():
    assert caption_hash("gâteau", "a") != caption_hash("gateau", "a")


def test_empty_caption_falls_back_to_media_id():
    assert caption_hash(None, "1") != caption_hash(None, "2")
    assert caption_hash("🎁🎁", "1") == caption_hash(None, "1")


def test_to_row_maps_fields(sample_media):
    row = to_row(by_id(sample_media)["1001"], "jeuconcours")
    assert row["ig_media_id"] == "1001"
    assert row["published_at"] == "2026-11-27T11:20:00+00:00"
    assert row["source_hashtags"] == ["jeuconcours"]
    assert set(row) == {"ig_media_id", "permalink", "caption", "caption_hash", "media_url",
                        "media_type", "published_at", "source_hashtags"}


def test_to_row_keeps_media_without_url_and_without_caption(sample_media):
    media = by_id(sample_media)
    assert to_row(media["1002"], "t")["media_url"] is None
    assert to_row(media["1007"], "t")["caption"] is None


def test_to_row_skips_unknown_media_type(sample_media):
    assert to_row(by_id(sample_media)["1006"], "t") is None


def rows_for(sample_media, tag):
    return [r for r in (to_row(m, tag) for m in sample_media) if r]


def test_merge_keeps_oldest_repost_and_merges_hashtags(sample_media):
    rows = rows_for(sample_media, "jeuconcours") + rows_for(sample_media, "concours")
    merged = {r["ig_media_id"]: r for r in merge_batch(rows)}
    assert "1003" not in merged and "1004" in merged
    assert merged["1001"]["source_hashtags"] == ["concours", "jeuconcours"]
    assert len(merged) == 5   # 7 media - 1 unknown type - 1 repost


def test_merge_drops_repost_of_already_stored_post(sample_media):
    row = to_row(by_id(sample_media)["1001"], "jeuconcours")
    stored = [{"ig_media_id": "0999", "caption_hash": row["caption_hash"], "source_hashtags": ["concours"]}]
    assert merge_batch([row], stored) == []


def test_merge_unions_hashtags_with_stored_version_of_same_post(sample_media):
    row = to_row(by_id(sample_media)["1001"], "jeuconcours")
    stored = [{"ig_media_id": "1001", "caption_hash": row["caption_hash"], "source_hashtags": ["tirageausort"]}]
    assert merge_batch([row], stored)[0]["source_hashtags"] == ["jeuconcours", "tirageausort"]


def test_partner_mentions_finds_co_organising_brands():
    caption = ("🎁 JEU CONCOURS en collab avec @Partenaire_Deco et @autre.marque. !\n"
               "Abonne-toi à @ma_marque, like, identifie 2 amies. Contact : jeu@ma_marque.fr")
    assert partner_mentions(caption, "ma_marque") == {"partenaire_deco", "autre.marque"}


@pytest.mark.parametrize("caption", [
    "La gagnante est @julie_123 ! Merci à toutes", "Bravo à @paul.x pour sa victoire",
    "Résultats du jeu concours : @marie", None,
])
def test_partner_mentions_skips_winner_announcements(caption):
    assert partner_mentions(caption, "ma_marque") == set()

# Captions adapted from real posts collected on 27/11/2026 (brands, people and places renamed).
import re
from datetime import date
from pathlib import Path

import pytest

from collector.analyze import analyze
from collector.classify import classify, load_categories
from collector.deadline import extract_deadline

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20261127120000_init.sql"
PUBLISHED = date(2026, 11, 27)   # a Friday


def test_yaml_slugs_match_the_categories_table():
    sql = MIGRATION.read_text(encoding="utf-8")
    block = sql[sql.index("insert into public.categories"):]
    seeded = set(re.findall(r"\('([a-z_]+)',", block[:block.index(";")]))
    assert set(load_categories()) | {"autre"} == seeded


@pytest.mark.parametrize("caption,expected", [
    ("🎄 GRAND JEU CONCOURS ! Tentez de remporter un bonsaï d'une valeur de 100 € pour votre jardin", "bricolage"),
    ("JEU CONCOURS : gagne 4 produits de soin (crème, sérum) d'une valeur de 138€", "beaute_bien_etre"),
    ("À GAGNER : 🥇 Une PS5 + 1 jeu", "jeux_video"),
    ("🎁 Gagne ta paire de UGG ! *150€ de carte cadeau à dépenser sur l'app", "mode_bijoux"),
    ("🎁 JEU CONCOURS – 2 PLACES À GAGNER ! Une soirée au théâtre", "sorties_evenements"),
    ("Tentez de gagner 110 livres avant Noël ! Votre bibliothèque idéale", "livres"),
    ("🎄 CONCOURS DE NOËL : un kit tableau magnétique pour les enfants", "enfants_famille"),
    ("Gagne un week-end pour 2 : 2 nuits avec petits-déjeuners à l'hôtel", "voyage"),
    ("🎁 3 CARTES CADEAUX DE 20 € À GAGNER !", "bons_achat"),
])
def test_main_theme(caption, expected):
    assert expected in classify(caption)


def test_collection_hashtag_gives_a_theme():
    assert classify("🎁 Concours ! Un lot à gagner", ["concoursbeaute"]) == ["beaute_bien_etre"]
    assert "beaute_bien_etre" in classify("Concours #jeuconcoursbeaute")


def test_decouvrir_is_not_deco():
    assert "deco_maison" not in classify("Venez découvrir notre concours")


def test_unknown_theme_falls_back_to_autre():
    assert classify("🎁 JEU CONCOURS : tentez de gagner une formation en ligne") == ["autre"]


def test_at_most_three_themes():
    caption = "parfum, sac, PS5, livre, chocolat, week-end, chien, carte cadeau"
    assert len(classify(caption)) == 3


@pytest.mark.parametrize("caption,expected", [
    ("Participez jusqu'au 29 novembre 2026 à 23h59 !", date(2026, 11, 29)),
    ("⏳ Fin du concours : dimanche 29 novembre à 23h59. 🎁 Tirage au sort : lundi 30 novembre", date(2026, 11, 29)),
    ("Tirage au sort le 07/12, bonne chance !", date(2026, 12, 7)),
    ("Tirage au sort le 2 Décembre, bonne chance à tous 🍀", date(2026, 12, 2)),
    ("📅 Du 28 novembre au 6 décembre", date(2026, 12, 6)),
    ("Du 1er au 24 décembre, une surprise par jour !", date(2026, 12, 24)),
    ("Tirage au sort dimanche 29/11 au soir.", date(2026, 11, 29)),
    ("⏳ 24H POUR PARTICIPER !", date(2026, 11, 28)),
    ("Tirage au sort ce dimanche soir !", date(2026, 11, 29)),
    ("Résultats le 5 janvier", date(2027, 1, 5)),
    ("2 places pour le concert du samedi 12 décembre", date(2026, 12, 12)),
])
def test_deadline(caption, expected):
    assert extract_deadline(caption, PUBLISHED) == expected


@pytest.mark.parametrize("caption", [
    "Une valeur de 113,50 € et 4.5/5 d'avis", "Concours ouvert à tous !", None,
    "Tirage au sort le 12 mars 2025",                  # far in the past: ignored
])
def test_no_deadline(caption):
    assert extract_deadline(caption, PUBLISHED) is None


def test_analyze_returns_db_ready_columns():
    result = analyze("JEU CONCOURS : like, abonne-toi, identifie 2 amis. Tirage le 07/12. Un parfum à gagner",
                     "2026-11-27T11:20:00+00:00", ["jeuconcours"])
    assert result == {"contest_score": 0.96, "entry_type": "instagram",
                      "categories": ["beaute_bien_etre"], "deadline": "2026-12-07"}

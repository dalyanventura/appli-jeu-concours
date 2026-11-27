# Captions adapted from real posts collected on 27/11/2026 (brands, people and places renamed).
import pytest

from collector.detect import VISIBLE_THRESHOLD, detect

INSTAGRAM_CONTEST = """🎁 JEU CONCOURS – 2 PLACES À GAGNER ! 🎭
Envie de passer une soirée pleine de rires ? On vous offre 2 places pour le spectacle, samedi au théâtre !
🍀 4 conditions pour participer :
1️⃣ Likez cette publication ❤️
2️⃣ Suivez le compte theatre_exemple
3️⃣ Identifiez 2 amis en commentaire
4️⃣ Partagez en story
Tirage au sort le 28 novembre à 12h."""

CO_BRANDED = """CONCOURS 🍂 Gagne un week-end pour 2 en Normandie !*
Pour participer :
🤍 Follow marque_a & gite_exemple
🤍 Like et enregistre ce post
🤍 Tag en commentaire ton + 1
Tirage au sort le 2 Décembre, bonne chance à tous 🍀"""

PURCHASE = """🚨 ALERTE NOUVEAU CONCOURS ! 🎁 Envie de remporter le parfum 30 ml de ton choix ?
📅 Du 28 novembre au 6 décembre
🛍️ 1 participation dès 35 € de commande
✨ 2 participations dès 70 € de commande"""

IN_STORE = """🎄🍫 UN CALENDRIER DE L'AVENT GÉANT À GAGNER ! Tentez votre chance pour remporter un calendrier
d'une valeur de 199€ ! 🎁 Pour participer : 📝 Remplissez votre bulletin de participation à l'accueil du magasin."""

EXTERNAL = """🚨 CONCOURS – Derniers jours pour tenter de gagner 110 livres avant Noël ! 📚
Pour participer : ✨ Inscrivez-vous gratuitement via le lien en bio. ✨ Partagez votre lien personnalisé à vos proches.
⏳ Fin du concours : dimanche 29 novembre à 23h59."""

WINNER = """🎉 FIN DE NOTRE JEU CONCOURS ! 🎉 Un grand merci à toutes et à tous pour votre participation ! ❤️
Nos heureux gagnants ont été contactés et ont bien récupéré leurs lots ! 🎁 Félicitations à eux !"""

WINNER_NAMED = "🎉 FÉLICITATIONS CAMILLE ! 🎉 Gagnante de notre jeu concours, elle est venue récupérer ses 2 tickets 🎤"

TEASER = """🤎 QUELQUE CHOSE SE PRÉPARE… 🎁 C'est une première et j'ai décidé de vous gâter avec un tout premier
jeu concours… 🥰 ✨ 3 lots à gagner. Restez connectés !"""

AGGREGATOR = """🏴‍☠️ BLACK FRIDAY : LES CADEAUX DÉBARQUENT ! 🚀 123 NOUVEAUX CONCOURS viennent d'arriver aujourd'hui
sur notre site ! ✈️ Voyage, 📺 TV, 🎮 PS5 et bien d'autres cadeaux !"""

PERSONAL_WINS = """🎁🍀 GAINS JEUX CONCOURS 🍀🎁 Ce jeudi, je vous présente mes nouveaux gains remportés grâce aux
jeux concours ! 😍 📀 Un coffret DVD, 🎶 un CD et une belle surprise !"""

EXAM = """Demain, on se voit au salon ? 📍 Paris, samedi 28 novembre. 🎤 13h00 : concours post-bac des écoles
de commerce. 🎤 14h00 : devenir ingénieur après le bac."""

HASHTAG_ONLY = "Ça serait dommage de passer à côté… #BlackFriday #Concours #Nails"

ENGLISH = """💥 WIN 500€ GIFT CARD 💥 The BIGGEST SALE of the Year deserves the BIGGEST GIVEAWAY! Enter now to win
and follow us for your chance, tag a friend in the comments. Ends Sunday."""

SCAM = "🎁 Félicitations, vous avez été sélectionné ! Réclamez votre lot via le lien en bio, payez uniquement les frais de port."


@pytest.mark.parametrize("caption,entry_type", [
    (INSTAGRAM_CONTEST, "instagram"), (CO_BRANDED, "instagram"), (PURCHASE, "purchase"),
    (IN_STORE, "in_store"), (EXTERNAL, "external_form"),
])
def test_open_contests_are_shown_with_their_entry_type(caption, entry_type):
    result = detect(caption)
    assert result.score >= VISIBLE_THRESHOLD, result
    assert result.entry_type == entry_type


@pytest.mark.parametrize("caption", [
    WINNER, WINNER_NAMED, TEASER, AGGREGATOR, PERSONAL_WINS, EXAM, HASHTAG_ONLY, ENGLISH, SCAM, "", None,
])
def test_noise_is_hidden(caption):
    assert detect(caption).score < VISIBLE_THRESHOLD, detect(caption)


def test_participation_words_alone_are_not_a_contest():
    assert detect("Likez, commentez et partagez notre nouvelle collection en story !").score < VISIBLE_THRESHOLD


def test_full_contest_scores_high():
    assert detect(INSTAGRAM_CONTEST).score >= 0.9


def test_no_purchase_mention_is_not_purchase():
    caption = INSTAGRAM_CONTEST + "\nJeu sans obligation d'achat, votre commande n'augmente pas vos chances."
    assert detect(caption).entry_type == "instagram"

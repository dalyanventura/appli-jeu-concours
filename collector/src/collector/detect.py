"""Is this post an open contest? Keyword score in [0, 1] + how to enter (entry_type).

Rules work on `fold()`ed text (lowercase, no accents). Hashtags are ignored for the
contest signals: "#concours" alone on an ad is not a contest.
Tuned on real captions (phase 3, 27/11/2026); vocabulary partly given by a regular player.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from collector.normalize import fold

VISIBLE_THRESHOLD = 0.5   # mirrored in the RLS policy "visible posts are public" (posts.contest_score)

HASHTAG = re.compile(r"#\w+")


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern)


CONTEST = _rx(r"concours|giveaway|tirage au sort|tire(?:e|s|es)? au sort|a gagner|a remporter|\bgagne[rz]?\b"
              r"|remporte[rz]?\b|tente[rz]? (?:ta|votre|de) |fai(?:t|s|sons|re|te) gagner|font gagner"
              r"|on (?:t|vous) offre|\bwin\b")
# how to enter on Instagram: each group counts once
ACTIONS = {
    "like": _rx(r"\blike[rsz]?\b|\blikez\b|aime[rz]? (?:ce|cette|la|le) (?:post|publication)|\baime cette"),
    "follow": _rx(r"abonne|\bfollow|\bsuis[- ](?:moi|nous|notre|nos|la|le|les)\b|\bsuivez\b|\bsuivre\b"),
    "tag": _rx(r"identifie|\btague?[rsz]?\b|\btag\b|mentionne"),
    "comment": _rx(r"commente|en commentaire|\bcomment\b"),
    "share": _rx(r"partage|repost|republie|en story|\bstory\b|\bstories\b"),
    "save": _rx(r"enregistre"),
}
HOW_TO = _rx(r"pour participer|comment participer|conditions?|pour (?:tenter|jouer)|regles? du jeu|to enter"
             r"|\d+ participations?\b|participe[rz]? (?:au|a notre|en)")
DRAW = _rx(r"tirage|tire(?:e|s)? au sort|fin du (?:jeu|concours)|jusqu'(?:au|a)\b|cloture|\bends?\b"
           r"|\bdu \d{1,2}(?:er)? (?:[a-z]+ )?au \d"
           r"|resultats? (?:le|annonce)|gagnant(?:e)?s? (?:sera|seront) (?:annonce|tire|designe|contacte)"
           r"|annonce (?:du|des) (?:gagnant|resultat)|avant le \d|date limite")
PRIZE = _rx(r"d'une valeur|valeur de|\d+ ?(?:€|euros)|\blots?\b|a gagner|offert|cadeau")

WINNER = _rx(r"felicitations|bravo a|(?:heureux|heureuse|heureuses|notre|nos) gagnant"
             r"|gagnant(?:e|s|es)? (?:est|sont|de notre|de la|du jeu|du concours)"
             r"|fin de (?:notre|ce) (?:jeu|concours)|(?:jeu )?concours (?:est )?termine"
             r"|resultats? du (?:jeu )?concours|a ete tire(?:e)? au sort|ont ete (?:tire|contacte)")
TEASER = _rx(r"bientot|se prepare|loading|restez connecte|prochainement|a venir|mets? la cloche"
             r"|active[rz]? (?:les |la )?notif|arrive(?:nt)? (?:bientot|demain|des le)|ouvre(?:nt)? demain")
AGGREGATOR = _rx(r"nouveaux concours|(?:mes|nos) (?:nouveaux )?gains|gains? (?:jeux )?concours"
                 r"|liste des concours|retrouve[rz]? (?:tous )?les concours")
OFF_TOPIC = _rx(r"concours (?:post.bac|d'entree|administratifs?|de la fonction publique|infirmier|blanc"
                r"|aux ecoles|de recrutement|externe|interne)|prepa(?:ration)? (?:au|aux) concours"
                r"|votez pour|\bvote[rz]?\b|trophee")
SCAM = _rx(r"reclame[rz]? (?:ton|votre) (?:lot|prix|cadeau)|vous avez (?:ete selectionne|gagne)"
           r"|frais de (?:livraison|port) (?:a payer|uniquement)|paye[rz]? (?:uniquement )?les frais"
           r"|carte bancaire")

PURCHASE = _rx(r"des \d+ ?(?:€|euros?)(?: d'achat| de commande)?|(?:pour|a) (?:tout|chaque) achat"
               r"|(?:toute|chaque|votre) commande|passe[rz]? (?:votre |une )?commande"
               r"|participation (?:des|avec|pour) .{0,30}(?:achat|commande)|ticket de caisse"
               r"|achat (?:obligatoire|minimum)")
NO_PURCHASE = _rx(r"sans (?:obligation d')?achat|no purchase")
IN_STORE = _rx(r"bulletin|\burne\b|a l'accueil|lors de (?:votre|ton) (?:prochain )?passage"
               r"|venez (?:jouer|participer)|au comptoir|en caisse")
EXTERNAL = _rx(r"lien en bio|link in bio|inscri(?:s|vez|re|ption)|formulaire|sur (?:notre|le|mon) site"
               r"|via le lien|sur l'app|telecharge|https?://|www\.|en dm|par mail|@gmail")


@dataclass(frozen=True)
class Detection:
    score: float
    entry_type: str
    signals: tuple[str, ...]


def detect(caption: str | None) -> Detection:
    text = HASHTAG.sub(" ", fold(caption))
    if not text.strip():
        return Detection(0.0, "other", ())
    signals: list[str] = []
    score = 0.0
    if CONTEST.search(text):
        score += 0.4
        signals.append("contest")
    actions = [name for name, rx in ACTIONS.items() if rx.search(text)]
    score += 0.12 * min(len(actions), 3)
    signals += actions
    for name, rx, weight in (("how_to", HOW_TO, 0.1), ("draw", DRAW, 0.12), ("prize", PRIZE, 0.08)):
        if rx.search(text):
            score += weight
            signals.append(name)
    for name, rx, weight in (("winner", WINNER, -0.45), ("aggregator", AGGREGATOR, -0.6),
                             ("off_topic", OFF_TOPIC, -0.5), ("scam", SCAM, -0.9)):
        if rx.search(text):
            if name == "winner" and "how_to" in signals:
                weight /= 2          # "Bravo à X ! Nouveau concours : pour participer…"
            score += weight
            signals.append(name)
    if TEASER.search(text) and len(actions) < 2:
        score -= 0.2
        signals.append("teaser")
    if "contest" not in signals or _foreign(text):
        # participation words alone ("like et commente") are not a contest; the app is for French players
        score = min(score, 0.3)
        if _foreign(text):
            signals.append("foreign")
    return Detection(round(max(0.0, min(1.0, score)), 2), _entry_type(text, len(actions)), tuple(signals))


FRENCH_WORDS = _rx(r"\b(?:le|la|les|de|des|du|et|pour|un|une|vous|tu|ton|ta|en|sur|avec|est|au|ce|nos|notre)\b")
FOREIGN_WORDS = _rx(r"\b(?:the|and|to|your|you|for|with|this|het|een|jouw|wij|voor|met|van|ons|und|der|die|mit"
                    r"|el|los|las|con|para|di|che|per)\b")


def _foreign(text: str) -> bool:
    """Mostly not French (the app is for a French audience)."""
    french = len(FRENCH_WORDS.findall(text))
    foreign = len(FOREIGN_WORDS.findall(text))
    return foreign >= 3 and foreign > french


def _entry_type(text: str, n_actions: int) -> str:
    if PURCHASE.search(text) and not NO_PURCHASE.search(text):
        return "purchase"
    if IN_STORE.search(text):
        return "in_store"
    if n_actions >= 2:
        return "instagram"
    if EXTERNAL.search(text):
        return "external_form"
    return "instagram" if n_actions else "other"

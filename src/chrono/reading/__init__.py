"""Lecture du bandeau : du texte reconnu vers un événement typé.

Deux moitiés volontairement séparées. `ocr` parle au moteur de reconnaissance,
qui est lent et demande un écran. `parsing` transforme des lignes de texte en
bandeau typé, et ne dépend de rien : c'est là que vivent les cas tordus, donc
c'est la partie qui doit être vérifiable sans rien installer.
"""

from .models import BannerKind, BannerReading
from .ocr import UPSCALE, RapidOcrReader, TextReader, upscale
from .parsing import (
    MIN_LINE_SCORE,
    MIN_READING_SCORE,
    TITLES,
    is_known_title,
    known_titles,
    parse_banner,
)

__all__ = [
    "MIN_LINE_SCORE",
    "MIN_READING_SCORE",
    "TITLES",
    "UPSCALE",
    "BannerKind",
    "BannerReading",
    "RapidOcrReader",
    "TextReader",
    "is_known_title",
    "known_titles",
    "parse_banner",
    "upscale",
]

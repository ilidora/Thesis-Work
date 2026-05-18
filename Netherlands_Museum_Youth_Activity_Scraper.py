"""
Netherlands Museum Youth Activity Scraper
==========================================
Thesis: "Mapping and Navigating the Netherlands Museum Scene with the (Post)migrant Youth"

PIPELINE:
  Stage 1 — Scrape museum.nl to collect a pool of Dutch museums with metadata
  Stage 2 — Randomly sample 80 museums
  Stage 3 — Scrape each museum's own website for youth/family activities (ages 3–18)
  Stage 4 — Build a structured DataFrame and export to CSV

REQUIREMENTS:
  pip install requests beautifulsoup4 pandas lxml tqdm

NOTES:
  - Many museum sites use JavaScript (React/Vue). For those, the scraper falls back
    to keyword scanning of whatever static HTML is available.
  - Run time: ~20–40 minutes for 80 museums (polite 2 s delay between requests).
  - Review the CSV manually afterwards — automated scraping will miss some content.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import random
import time
import re
import logging
from urllib.parse import urljoin, urlparse
from tqdm import tqdm
from typing import Optional, Tuple
import urllib3

# ── Configuration ──────────────────────────────────────────────────────────────

SAMPLE_SIZE = 80
REQUEST_DELAY = 2
REQUEST_TIMEOUT = 15
OUTPUT_CSV = "museum_youth_activities.csv"

VERIFY_SSL = False

if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ThesisResearchBot/1.0; "
        "contact: your_email@example.com)"   # ← replace with your email
    )
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("scraper.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)


# ── Keyword banks (Dutch + English) ───────────────────────────────────────────

YOUTH_KEYWORDS = [
    # Dutch
    "kinderen", "kind", "jeugd", "jongeren", "tieners", "gezin", "gezinnen",
    "familie", "schoolgroep", "schoolklas", "basisschool", "middelbare school",
    "peuter", "kleuter", "leerling", "educatie", "rondleiding kinderen",
    "familierondleiding", "kidsclub", "kinderprogramma", "schoolprogramma",
    "workshop kinderen", "vakantie activiteit",
    # English
    "children", "child", "kids", "youth", "teen", "teenager", "family",
    "families", "school group", "primary school", "secondary school",
    "toddler", "educational", "guided tour children", "family tour",
    "kids workshop", "holiday activity", "school programme",
]

AGE_PATTERN = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:jaar|years?|jr\.?)|"
    r"(?:vanaf|from|age|leeftijd)\s*(\d{1,2})|"
    r"(\d{1,2})\+",
    re.IGNORECASE
)

LANGUAGE_KEYWORDS = {
    "nl": ["nederlands", "dutch", "nl"],
    "en": ["english", "engels", "en"],
    "de": ["deutsch", "german", "duits", "de"],
    "fr": ["français", "french", "frans", "fr"],
    "ar": ["arabisch", "arabic", "عربي"],
    "tr": ["turks", "turkish", "türkçe"],
}

DIGITAL_KEYWORDS = {
    "VR": ["virtual reality", "vr", "vr-bril", "vr headset"],
    "AR": ["augmented reality", "ar", "augmented"],
    "Digital guide": ["digitale gids", "digital guide", "audio guide", "audiogids", "app"],
    "Interactive screen": ["interactief scherm", "touchscreen", "interactive screen", "digitaal scherm"],
    "Online/hybrid": ["online", "livestream", "hybrid", "digitaal bezoek", "virtual tour"],
    "Game/quiz": ["game", "quiz", "spel", "digitaal spel"],
}

ACCESSIBILITY_KEYWORDS = [
    "rolstoel", "wheelchair", "toegankelijk", "accessible", "accessibility",
    "slechthorend", "slechtziend", "blind", "doof", "autisme", "dyslexie",
    "beperking", "disability", "special needs", "inclusive", "inclusief",
    "gebarentaal", "sign language", "braille", "audiodescriptie",
]

CATEGORY_KEYWORDS = {
    "history": [
        "geschiedenis", "historisch", "history", "historical", "erfgoed",
        "heritage", "archeologie", "archaeology", "oorlog", "war",
    ],
    "art": [
        "kunst", "art", "museum voor moderne kunst", "schilderij", "painting",
        "beeldhouwkunst", "sculpture", "fotografie", "photography", "design",
        "mode", "fashion",
    ],
    "science": [
        "wetenschap", "science", "technologie", "technology", "natuur",
        "nature", "biologie", "biology", "scheikunde", "chemistry",
        "sterrenkunde", "astronomy", "nemo", "naturalis",
    ],
}

# ── Stage 1: Collect museums from museum.nl ────────────────────────────────────

def fetch_museum_list_from_museumnl(max_pages: int = 20) -> list[dict]:
    """
    Scrapes museum.nl/en/museums for a list of museums with name, city, and URL.
    Falls back to a curated seed list if scraping fails.
    """
    museums = []
    base = "https://www.museum.nl/en/museums"

    log.info("Fetching museum list from museum.nl …")
    for page in range(1, max_pages + 1):
        url = f"{base}?page={page}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "lxml")

            # museum.nl card structure (adjust selectors if the site updates)
            cards = soup.select("article.museum-card, div.museum-item, li.museum")
            if not cards:
                # fallback: look for any <a> with /museum/ in href
                cards = soup.find_all("a", href=re.compile(r"/museum/|/musea/"))

            if not cards:
                log.info(f"  No cards found on page {page}, stopping.")
                break

            for card in cards:
                name_tag = card.select_one("h2, h3, .museum-name, .title")
                name = name_tag.get_text(strip=True) if name_tag else card.get_text(strip=True)[:60]
                link_tag = card if card.name == "a" else card.find("a")
                href = link_tag["href"] if link_tag and link_tag.get("href") else ""
                city_tag = card.select_one(".city, .location, .place")
                city = city_tag.get_text(strip=True) if city_tag else "Unknown"

                if name and href:
                    museums.append({
                        "name": name.strip(),
                        "city": city.strip(),
                        "museum_nl_url": urljoin("https://www.museum.nl", href),
                        "website": ""
                    })

            log.info(f"  Page {page}: {len(cards)} museums found (total so far: {len(museums)})")
            time.sleep(REQUEST_DELAY)

        except Exception as e:
            log.warning(f"  Error on page {page}: {e}")
            break

    if len(museums) < SAMPLE_SIZE:
        log.warning(
            f"Only {len(museums)} museums scraped from museum.nl. "
            "Supplementing with curated seed list."
        )
        museums += get_seed_museums()

    # Deduplicate by name
    seen = set()
    unique = []
    for m in museums:
        key = m["name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(m)

    log.info(f"Total unique museums collected: {len(unique)}")
    return unique


def get_seed_museums() -> list[dict]:
    """
    Curated seed list of well-known Dutch museums with known websites.
    Used as fallback / supplement when scraping yields too few results.
    """
    return [
        {"name": "Rijksmuseum", "city": "Amsterdam", "website": "https://www.rijksmuseum.nl", "museum_nl_url": ""},
        {"name": "Van Gogh Museum", "city": "Amsterdam", "website": "https://www.vangoghmuseum.nl", "museum_nl_url": ""},
        {"name": "Stedelijk Museum Amsterdam", "city": "Amsterdam", "website": "https://www.stedelijk.nl", "museum_nl_url": ""},
        {"name": "Anne Frank House", "city": "Amsterdam", "website": "https://www.annefrank.org", "museum_nl_url": ""},
        {"name": "NEMO Science Museum", "city": "Amsterdam", "website": "https://www.nemosciencemuseum.nl", "museum_nl_url": ""},
        {"name": "Amsterdam Museum", "city": "Amsterdam", "website": "https://www.amsterdammuseum.nl", "museum_nl_url": ""},
        {"name": "Tropenmuseum", "city": "Amsterdam", "website": "https://www.tropenmuseum.nl", "museum_nl_url": ""},
        {"name": "Allard Pierson", "city": "Amsterdam", "website": "https://allardpierson.nl", "museum_nl_url": ""},
        {"name": "EYE Filmmuseum", "city": "Amsterdam", "website": "https://www.eyefilm.nl", "museum_nl_url": ""},
        {"name": "Moco Museum", "city": "Amsterdam", "website": "https://mocomuseum.com", "museum_nl_url": ""},
        {"name": "Mauritshuis", "city": "Den Haag", "website": "https://www.mauritshuis.nl", "museum_nl_url": ""},
        {"name": "Gemeentemuseum Den Haag", "city": "Den Haag", "website": "https://www.gemeentemuseum.nl", "museum_nl_url": ""},
        {"name": "Escher in het Paleis", "city": "Den Haag", "website": "https://www.escherinhetpaleis.nl", "museum_nl_url": ""},
        {"name": "Panorama Mesdag", "city": "Den Haag", "website": "https://www.panorama-mesdag.nl", "museum_nl_url": ""},
        {"name": "Louwman Museum", "city": "Den Haag", "website": "https://www.louwmanmuseum.nl", "museum_nl_url": ""},
        {"name": "Museum Boijmans Van Beuningen", "city": "Rotterdam", "website": "https://www.boijmans.nl", "museum_nl_url": ""},
        {"name": "Kunsthal Rotterdam", "city": "Rotterdam", "website": "https://www.kunsthal.nl", "museum_nl_url": ""},
        {"name": "Maritiem Museum Rotterdam", "city": "Rotterdam", "website": "https://www.maritiemmuseum.nl", "museum_nl_url": ""},
        {"name": "Wereldmuseum Rotterdam", "city": "Rotterdam", "website": "https://www.wereldmuseum.nl", "museum_nl_url": ""},
        {"name": "Museum Rotterdam", "city": "Rotterdam", "website": "https://www.museumrotterdam.nl", "museum_nl_url": ""},
        {"name": "Centraal Museum Utrecht", "city": "Utrecht", "website": "https://www.centraalmuseum.nl", "museum_nl_url": ""},
        {"name": "Museum Speelklok", "city": "Utrecht", "website": "https://www.museumspeelklok.nl", "museum_nl_url": ""},
        {"name": "Universiteitsmuseum Utrecht", "city": "Utrecht", "website": "https://www.uu.nl/universiteitsmuseum", "museum_nl_url": ""},
        {"name": "Groninger Museum", "city": "Groningen", "website": "https://www.groningermuseum.nl", "museum_nl_url": ""},
        {"name": "Noordelijk Scheepvaartmuseum", "city": "Groningen", "website": "https://www.noordelijkscheepvaartmuseum.nl", "museum_nl_url": ""},
        {"name": "Bonnefantenmuseum", "city": "Maastricht", "website": "https://www.bonnefanten.nl", "museum_nl_url": ""},
        {"name": "Museum aan de Stroom (MAS)", "city": "Antwerpen", "website": "https://www.mas.be", "museum_nl_url": ""},
        {"name": "Fries Museum", "city": "Leeuwarden", "website": "https://www.friesmuseum.nl", "museum_nl_url": ""},
        {"name": "Princessehof Nationaal Keramiekmuseum", "city": "Leeuwarden", "website": "https://www.princessehof.nl", "museum_nl_url": ""},
        {"name": "Kröller-Müller Museum", "city": "Otterlo", "website": "https://krollermuller.nl", "museum_nl_url": ""},
        {"name": "Openluchtmuseum", "city": "Arnhem", "website": "https://www.openluchtmuseum.nl", "museum_nl_url": ""},
        {"name": "Museum Arnhem", "city": "Arnhem", "website": "https://www.museumarnhem.nl", "museum_nl_url": ""},
        {"name": "Airborne Museum Hartenstein", "city": "Arnhem", "website": "https://www.airbornemuseum.nl", "museum_nl_url": ""},
        {"name": "Naturalis Biodiversity Center", "city": "Leiden", "website": "https://www.naturalis.nl", "museum_nl_url": ""},
        {"name": "Rijksmuseum van Oudheden", "city": "Leiden", "website": "https://www.rmo.nl", "museum_nl_url": ""},
        {"name": "Museum Volkenkunde", "city": "Leiden", "website": "https://www.volkenkunde.nl", "museum_nl_url": ""},
        {"name": "Stedelijk Museum De Lakenhal", "city": "Leiden", "website": "https://www.lakenhal.nl", "museum_nl_url": ""},
        {"name": "Paleis Het Loo", "city": "Apeldoorn", "website": "https://www.paleishetloo.nl", "museum_nl_url": ""},
        {"name": "Apenheul", "city": "Apeldoorn", "website": "https://www.apenheul.nl", "museum_nl_url": ""},
        {"name": "Van Abbe Museum", "city": "Eindhoven", "website": "https://vanabbemuseum.nl", "museum_nl_url": ""},
        {"name": "Philips Museum", "city": "Eindhoven", "website": "https://www.philips-museum.com", "museum_nl_url": ""},
        {"name": "DAF Museum", "city": "Eindhoven", "website": "https://www.dafmuseum.nl", "museum_nl_url": ""},
        {"name": "Museum de Fundatie", "city": "Zwolle", "website": "https://www.museumdefundatie.nl", "museum_nl_url": ""},
        {"name": "Historisch Museum Deventer", "city": "Deventer", "website": "https://www.historischmuseumdeventer.nl", "museum_nl_url": ""},
        {"name": "Rijksmuseum Twenthe", "city": "Enschede", "website": "https://www.rijksmuseumtwenthe.nl", "museum_nl_url": ""},
        {"name": "TextielMuseum", "city": "Tilburg", "website": "https://www.textielmuseum.nl", "museum_nl_url": ""},
        {"name": "Noordbrabants Museum", "city": "'s-Hertogenbosch", "website": "https://www.noordbrabantsmuseum.nl", "museum_nl_url": ""},
        {"name": "Design Museum Den Bosch", "city": "'s-Hertogenbosch", "website": "https://www.designmuseumdenbosch.nl", "museum_nl_url": ""},
        {"name": "Zeeuws Museum", "city": "Middelburg", "website": "https://www.zeeuwsmuseum.nl", "museum_nl_url": ""},
        {"name": "Museum Flehite", "city": "Amersfoort", "website": "https://www.museumflehite.nl", "museum_nl_url": ""},
        {"name": "Mondriaanhuis", "city": "Amersfoort", "website": "https://www.mondriaanhuis.nl", "museum_nl_url": ""},
        {"name": "Joods Historisch Museum", "city": "Amsterdam", "website": "https://www.jhm.nl", "museum_nl_url": ""},
        {"name": "Verzetsmuseum", "city": "Amsterdam", "website": "https://www.verzetsmuseum.org", "museum_nl_url": ""},
        {"name": "Scheepvaartmuseum", "city": "Amsterdam", "website": "https://www.hetscheepvaartmuseum.nl", "museum_nl_url": ""},
        {"name": "Hermitage Amsterdam", "city": "Amsterdam", "website": "https://www.hermitage.nl", "museum_nl_url": ""},
        {"name": "Museum Ons' Lieve Heer op Solder", "city": "Amsterdam", "website": "https://www.opsolder.nl", "museum_nl_url": ""},
        {"name": "Foam Fotografiemuseum", "city": "Amsterdam", "website": "https://www.foam.org", "museum_nl_url": ""},
        {"name": "Hash Marihuana & Hemp Museum", "city": "Amsterdam", "website": "https://hashmuseum.com", "museum_nl_url": ""},
        {"name": "Micropia", "city": "Amsterdam", "website": "https://www.micropia.nl", "museum_nl_url": ""},
        {"name": "ARTIS-Zoo", "city": "Amsterdam", "website": "https://www.artis.nl", "museum_nl_url": ""},
        {"name": "Museum Het Rembrandthuis", "city": "Amsterdam", "website": "https://www.rembrandthuis.nl", "museum_nl_url": ""},
        {"name": "Westfries Museum", "city": "Hoorn", "website": "https://www.westfriesmuseum.nl", "museum_nl_url": ""},
        {"name": "Zuiderzeemuseum", "city": "Enkhuizen", "website": "https://www.zuiderzeemuseum.nl", "museum_nl_url": ""},
        {"name": "Museum Haarlem", "city": "Haarlem", "website": "https://www.museumhaarlem.nl", "museum_nl_url": ""},
        {"name": "Frans Hals Museum", "city": "Haarlem", "website": "https://www.franshalsmuseum.nl", "museum_nl_url": ""},
        {"name": "Teylers Museum", "city": "Haarlem", "website": "https://www.teylersmuseum.nl", "museum_nl_url": ""},
        {"name": "Museum Catharijneconvent", "city": "Utrecht", "website": "https://www.catharijneconvent.nl", "museum_nl_url": ""},
        {"name": "DOMunder", "city": "Utrecht", "website": "https://www.domunder.nl", "museum_nl_url": ""},
        {"name": "Museum Volkenkunde Leiden", "city": "Leiden", "website": "https://www.volkenkunde.nl", "museum_nl_url": ""},
        {"name": "Museum De Gevangenpoort", "city": "Den Haag", "website": "https://www.gevangenpoort.nl", "museum_nl_url": ""},
        {"name": "Museon-Omniversum", "city": "Den Haag", "website": "https://www.museon.nl", "museum_nl_url": ""},
        {"name": "Haags Historisch Museum", "city": "Den Haag", "website": "https://www.haagshistorischmuseum.nl", "museum_nl_url": ""},
        {"name": "Historisch Museum Rotterdam", "city": "Rotterdam", "website": "https://www.historischmuseumrotterdam.nl", "museum_nl_url": ""},
        {"name": "Witte de With / TENT", "city": "Rotterdam", "website": "https://www.wdw.nl", "museum_nl_url": ""},
        {"name": "Dordrechts Museum", "city": "Dordrecht", "website": "https://www.dordrechtsmuseum.nl", "museum_nl_url": ""},
        {"name": "Simon van Gijn", "city": "Dordrecht", "website": "https://www.simonvangijn.nl", "museum_nl_url": ""},
        {"name": "Museum Gouda", "city": "Gouda", "website": "https://www.museumgouda.nl", "museum_nl_url": ""},
        {"name": "Stedelijk Museum Alkmaar", "city": "Alkmaar", "website": "https://www.stedelijkmuseumalkmaar.nl", "museum_nl_url": ""},
        {"name": "Museum Kaap Skil", "city": "Texel", "website": "https://www.kaapskil.nl", "museum_nl_url": ""},
        {"name": "Drents Museum", "city": "Assen", "website": "https://www.drentsmuseum.nl", "museum_nl_url": ""},
        {"name": "Hunebedcentrum", "city": "Borger", "website": "https://www.hunebedcentrum.nl", "museum_nl_url": ""},
        {"name": "Museum Twentse Welle", "city": "Enschede", "website": "https://www.twentsewelle.nl", "museum_nl_url": ""},
        {"name": "Geldersch Landschap & Kastelen", "city": "Arnhem", "website": "https://www.glk.nl", "museum_nl_url": ""},
        {"name": "Nationaal Oorlogs- en Verzetsmuseum", "city": "Overloon", "website": "https://www.oorlogsmuseum.nl", "museum_nl_url": ""},
        {"name": "Bevrijdend Museum", "city": "Groesbeek", "website": "https://www.bevrijdingsmuseum.nl", "museum_nl_url": ""},
        {"name": "Museum Sophiahof", "city": "Den Haag", "website": "https://www.museumsophiahof.nl", "museum_nl_url": ""},
        {"name": "Cobra Museum", "city": "Amstelveen", "website": "https://www.cobramuseum.com", "museum_nl_url": ""},
        {"name": "Museum Jan Cunen", "city": "Oss", "website": "https://www.museumjancunen.nl", "museum_nl_url": ""},
        {"name": "Museum de Wieger", "city": "Deurne", "website": "https://www.museumdewieger.nl", "museum_nl_url": ""},
        {"name": "Stedelijk Museum Breda", "city": "Breda", "website": "https://www.stedelijkmuseumbreda.nl", "museum_nl_url": ""},
        {"name": "Breda's Museum", "city": "Breda", "website": "https://www.bredasmuseum.nl", "museum_nl_url": ""},
        {"name": "Museum Helmond", "city": "Helmond", "website": "https://www.museumhelmond.nl", "museum_nl_url": ""},
        {"name": "Limburgs Museum", "city": "Venlo", "website": "https://www.limburgsmuseum.nl", "museum_nl_url": ""},
        {"name": "Valkhof Museum", "city": "Nijmegen", "website": "https://www.museumhetvalkhof.nl", "museum_nl_url": ""},
        {"name": "Afrikamuseum", "city": "Berg en Dal", "website": "https://www.afrikamuseum.nl", "museum_nl_url": ""},
        {"name": "Rijksmuseum Paleis Het Loo", "city": "Apeldoorn", "website": "https://www.paleishetloo.nl", "museum_nl_url": ""},
        {"name": "Museum voor Communicatie (Muscom)", "city": "Den Haag", "website": "https://www.muscom.nl", "museum_nl_url": ""},
        {"name": "Nationaal Militair Museum", "city": "Soest", "website": "https://www.nmm.nl", "museum_nl_url": ""},
        {"name": "Spoorwegmuseum", "city": "Utrecht", "website": "https://www.spoorwegmuseum.nl", "museum_nl_url": ""},
        {"name": "Dolhuys Museum", "city": "Haarlem", "website": "https://www.dolhuys.nl", "museum_nl_url": ""},
        {"name": "Museum Waterland", "city": "Purmerend", "website": "https://www.museumwaterland.nl", "museum_nl_url": ""},
        {"name": "Archeon", "city": "Alphen aan den Rijn", "website": "https://www.archeon.nl", "museum_nl_url": ""},
        {"name": "Madurodam", "city": "Den Haag", "website": "https://www.madurodam.nl", "museum_nl_url": ""},
    ]


# ── Stage 2: Resolve each museum's own website ────────────────────────────────

def resolve_museum_website(museum: dict) -> str:
    """
    If the museum already has a website URL, return it.
    Otherwise, try to extract it from its museum.nl profile page.
    """
    if museum.get("website"):
        return museum["website"]

    profile_url = museum.get("museum_nl_url", "")
    if not profile_url:
        return ""

    try:
        r = requests.get(profile_url, headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
        soup = BeautifulSoup(r.text, "lxml")
        # Look for an external link on the profile page
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "museum.nl" not in href:
                return href
    except Exception as e:
        log.debug(f"Could not resolve website for {museum['name']}: {e}")

    return ""


# ── Stage 3: Scrape individual museum websites ────────────────────────────────

def get_page_text(url: str) -> Tuple[str, Optional[BeautifulSoup]]:
    """Fetch a URL and return (raw_text, soup). Returns ('', None) on failure."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        return r.text.lower(), soup
    except Exception as e:
        log.debug(f"  Failed to fetch {url}: {e}")
        return "", None


def find_youth_pages(base_url: str, soup: BeautifulSoup) -> list[str]:
    """
    From the museum homepage, find internal links that likely lead to
    youth / family / education sections.
    """
    if not soup:
        return []

    youth_nav_keywords = [
        "kinderen", "kids", "jeugd", "familie", "family", "educatie",
        "education", "school", "jongeren", "activiteiten", "activities",
        "rondleidingen", "tours", "programma", "programme", "workshops",
    ]

    candidate_urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        text = a.get_text(strip=True).lower()
        if any(kw in href or kw in text for kw in youth_nav_keywords):
            full_url = urljoin(base_url, a["href"])
            # Stay on the same domain
            if urlparse(full_url).netloc == urlparse(base_url).netloc:
                candidate_urls.add(full_url)

    return list(candidate_urls)[:10]  # cap at 10 sub-pages per museum


def extract_age_range(text: str) -> str:
    """Extract age mentions from text, return as a readable string."""
    matches = AGE_PATTERN.findall(text)
    ages = []
    for m in matches:
        if m[0] and m[1]:
            ages.append(f"{m[0]}–{m[1]}")
        elif m[2]:
            ages.append(f"{m[2]}+")
        elif m[3]:
            ages.append(f"{m[3]}+")
    return "; ".join(dict.fromkeys(ages)) if ages else "not specified"


def detect_languages(text: str) -> dict[str, bool]:
    """Return a dict of language → bool based on keyword presence."""
    result = {}
    for lang, keywords in LANGUAGE_KEYWORDS.items():
        result[f"lang_{lang}"] = any(kw in text for kw in keywords)
    return result


def detect_digital(text: str) -> tuple[bool, str]:
    """Return (has_digital, description_string)."""
    found = []
    for label, keywords in DIGITAL_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            found.append(label)
    return (bool(found), "; ".join(found) if found else "")


def detect_accessibility(text: str) -> bool:
    return any(kw in text for kw in ACCESSIBILITY_KEYWORDS)


def infer_category(name: str, text: str) -> str:
    """Guess museum category from name + homepage text."""
    combined = (name + " " + text[:3000]).lower()
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def scrape_museum(museum: dict) -> list[dict]:
    """
    Scrape a single museum's website and return a list of activity records.
    Each record corresponds to one youth-relevant page/activity found.
    """
    website = museum.get("website", "")
    if not website:
        log.info(f"  [{museum['name']}] No website, skipping.")
        return []

    records = []
    homepage_text, homepage_soup = get_page_text(website)

    if not homepage_text:
        log.info(f"  [{museum['name']}] Could not fetch homepage.")
        return []

    category = infer_category(museum["name"], homepage_text)

    # Find sub-pages likely related to youth/family
    sub_pages = find_youth_pages(website, homepage_soup)
    pages_to_scan = [(website, homepage_text, homepage_soup)] + [
        (url, *get_page_text(url)) for url in sub_pages
    ]

    activity_id_counter = 1
    for page_url, page_text, page_soup in pages_to_scan:
        if not page_text:
            continue

        # Check if this page is relevant to youth audiences
        is_relevant = any(kw in page_text for kw in YOUTH_KEYWORDS)
        if not is_relevant:
            continue

        # Try to extract individual activity blocks (headings, sections, cards)
        activities_found = []
        if page_soup:
            # Look for activity cards / sections
            blocks = page_soup.select(
                "article, .activity, .event, .programme-item, "
                ".card, section, .workshop, .tour-item"
            )
            if not blocks:
                # Fall back: treat the whole page as one activity
                blocks = [page_soup]

            for block in blocks[:15]:  # cap per page
                block_text = block.get_text(separator=" ", strip=True).lower()
                if not any(kw in block_text for kw in YOUTH_KEYWORDS):
                    continue

                title_tag = block.find(["h1", "h2", "h3", "h4"])
                title = title_tag.get_text(strip=True) if title_tag else "Activity (see link)"

                age_range = extract_age_range(block_text)
                langs = detect_languages(block_text)
                has_digital, digital_desc = detect_digital(block_text)
                has_access = detect_accessibility(block_text)

                record = {
                    "activity_id": f"{museum['name'][:6].upper().replace(' ', '_')}_{activity_id_counter:03d}",
                    "museum_name": museum["name"],
                    "museum_category": category,
                    "city": museum.get("city", "Unknown"),
                    "activity_title": title[:120],
                    "activity_url": page_url,
                    "target_age_range": age_range,
                    **langs,
                    "has_digital_experience": has_digital,
                    "digital_experience_description": digital_desc,
                    "special_needs_accessible": has_access,
                    "notes": "",
                }
                activities_found.append(record)
                activity_id_counter += 1

        if not activities_found:
            # Page is relevant but no blocks found — add one generic record
            age_range = extract_age_range(page_text)
            langs = detect_languages(page_text)
            has_digital, digital_desc = detect_digital(page_text)
            has_access = detect_accessibility(page_text)

            activities_found.append({
                "activity_id": f"{museum['name'][:6].upper().replace(' ', '_')}_{activity_id_counter:03d}",
                "museum_name": museum["name"],
                "museum_category": category,
                "city": museum.get("city", "Unknown"),
                "activity_title": "Youth/Family Programme (see link)",
                "activity_url": page_url,
                "target_age_range": age_range,
                **langs,
                "has_digital_experience": has_digital,
                "digital_experience_description": digital_desc,
                "special_needs_accessible": has_access,
                "notes": "Auto-detected youth page; manual review recommended",
            })
            activity_id_counter += 1

        records.extend(activities_found)
        time.sleep(REQUEST_DELAY)

    log.info(f"  [{museum['name']}] → {len(records)} activity record(s) found.")
    return records


# ── Stage 4: Build DataFrame and export ───────────────────────────────────────

COLUMNS = [
    "activity_id",
    "museum_name",
    "museum_category",
    "city",
    "activity_title",
    "activity_url",
    "target_age_range",
    "lang_nl",
    "lang_en",
    "lang_de",
    "lang_fr",
    "lang_ar",
    "lang_tr",
    "has_digital_experience",
    "digital_experience_description",
    "special_needs_accessible",
    "notes",
]


def build_dataframe(records: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(records, columns=COLUMNS)
    # Ensure boolean columns are actual booleans
    bool_cols = [
        "lang_nl", "lang_en", "lang_de", "lang_fr", "lang_ar", "lang_tr",
        "has_digital_experience", "special_needs_accessible"
    ]
    for col in bool_cols:
        df[col] = df[col].astype(bool)
    return df


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    random.seed(42)  # reproducible sample

    # Stage 1: Collect museums
    all_museums = fetch_museum_list_from_museumnl(max_pages=20)

    # Supplement with seed list to ensure we have enough
    seed = get_seed_museums()
    seed_names = {m["name"].lower() for m in all_museums}
    for m in seed:
        if m["name"].lower() not in seed_names:
            all_museums.append(m)
            seed_names.add(m["name"].lower())

    log.info(f"Total museum pool: {len(all_museums)}")

    # Stage 2: Random sample of 80
    sample = random.sample(all_museums, min(SAMPLE_SIZE, len(all_museums)))
    log.info(f"Sampled {len(sample)} museums.")

    # Resolve websites for museums that only have a museum.nl profile URL
    log.info("Resolving museum websites …")
    for m in tqdm(sample, desc="Resolving websites"):
        if not m.get("website"):
            m["website"] = resolve_museum_website(m)
        time.sleep(0.5)

    # Stage 3: Scrape each museum
    all_records = []
    log.info("Scraping museum websites for youth activities …")
    for museum in tqdm(sample, desc="Scraping museums"):
        records = scrape_museum(museum)
        all_records.extend(records)

    # Stage 4: Build and export
    if not all_records:
        log.warning("No records collected. Check your internet connection and the scraper log.")
        return

    df = build_dataframe(all_records)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")  # utf-8-sig for Excel compatibility
    log.info(f"\n✅ Done! {len(df)} activity records saved to '{OUTPUT_CSV}'")
    log.info(f"   Museums covered: {df['museum_name'].nunique()}")
    log.info(f"   Categories: {df['museum_category'].value_counts().to_dict()}")
    print(df.head(10).to_string())


if __name__ == "__main__":
    main()

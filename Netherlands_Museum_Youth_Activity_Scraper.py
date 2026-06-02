# The key .py file to run for crawling museum websites and extracting youth/family activity info.
# It uses the cached list of Dutch museums from Wikidata (created by fetch script) 
# and applies heuristics to find relevant pages and extract info (see nl_museums_wikidata.csv).


import requests
import random
import time
import re
import os
from urllib.parse import urljoin, urlparse
import sys

import pandas as pd
from parsel import Selector
import scrapy

# ------------- CONFIGURATION -------------

N_SAMPLED_MUSEUMS = 50
TARGET_SUCCESSFUL_MUSEUMS = 100 
RANDOM_SEED = 7
REQUEST_TIMEOUT = 10
SLEEP_BETWEEN_REQUESTS = (1, 3)  # seconds, random between min/max
MAX_PAGES_PER_MUSEUM = 25        # to avoid overloading sites
MAX_CRAWL_DEPTH = 1              # 0 = only homepage, 1 = homepage + direct links

HEADERS = {
    "User-Agent": "AcademicResearchBot/1.0 (non-commercial, contact: your-email@example.com)"
}

# Keywords for detecting youth/family-related pages (English + Dutch)
YOUTH_KEYWORDS = [
    "school", "schools", "education", "educational", "family", "families",
    "children", "child", "kids", "youth", "teen", "teens", "program", "workshop",
    "tour", "tours", "activities", "activity",
    "onderwijs", "scholen", "educatie", "familie", "gezinnen", "kinderen",
    "jeugd", "jongeren", "basisschool", "voortgezet onderwijs", "schoolbezoek"
]

# Keywords for language detection
LANG_KEYWORDS = {
    "nl": ["nederlands", "dutch"],
    "en": ["english", "engels"],
    "de": ["deutsch", "duits", "german"],
    "fr": ["français", "frans", "french"],
    "es": ["español", "spaans", "spanish"],
    "it": ["italian", "italiaans", "italian"],
    "pap": ["papiamento"],
    "ru": ["русский", "russisch", "russian"],
    "ja": ["日本語", "japans", "japanese"],
    "zh": ["中文", "chineese", "chinese", "mandarijn", "mandarin"],
    "uk": ["ukrainian", "oekraïnse", "українська"],
    "ar": ["arabic", "عربي","arabisch"],
    "pt": ["portuguese", "portugees", "português"],
    "ko": ["korean", "koreaans", "한국어"],
}

# Keywords / patterns for digital experiences
DIGITAL_PATTERNS = [
    # VR / AR
    (r"\bvirtual reality\b", "virtual reality"),
    (r"\baugmented reality\b", "augmented reality"),
    (r"\bvr\b", "VR"),
    # if a museum writes 'VR-experience' or 'VR experience'
    (r"\bvr[- ]?experience\b", "VR experience"),

    # apps / tablets / devices
    (r"\bapp(s)?\b", "app"),
    (r"\btablet(s)?\b", "tablet"),
    (r"\bsmartphone(s)?\b", "smartphone"),

    # games / gaming
    (r"\b(game|games|gaming|videogame|video game)\b", "game"),

    # guides / multimedia
    (r"\b(audio guide|audioguide|audiotour|audio tour)\b", "audio guide"),
    (r"\b(digital guide|digitale gids)\b", "digital guide"),
    (r"\b(multimedia|multimedial)\b", "multimedia"),

    # “interactive” as a proxy for digital/tech
    (r"\b(interactive|interactief)\b", "interactive"),

    # online / virtual tours etc.
    (r"\b(online tour|virtual tour|digitale rondleiding|online rondleiding)\b", "online/virtual tour"),

    # kiosks / screens
    (r"\b(touchscreen|touch screen|touch-screen)\b", "touchscreen"),
    (r"\b(info[- ]?kiosk|infokiosk)\b", "kiosk"),

]

# Keywords / patterns for accessibility / special needs (EN + NL)
# Keywords for finding museum-level accessibility / visit information pages
ACCESSIBILITY_PAGE_KEYWORDS = [
    # Dutch
    "toegankelijkheid", "toegankelijk", "mindervaliden", "beperking",
    "rolstoel", "rolstoeltoegankelijk", "voorzieningen",
    "bezoek", "plan je bezoek", "praktische informatie", "praktisch",

    # English
    "accessibility", "accessible", "disabled", "special needs",
    "wheelchair", "visit", "plan your visit", "practical information",
]

ACCESSIBILITY_PATTERNS = [
    # Wheelchair / mobility
    (r"\bwheelchair[- ]?accessible\b", "wheelchair access"),
    (r"\bwheelchair(s)?\b", "wheelchair access"),
    (r"\brolstoel(?:gebruikers)?\b", "wheelchair access"),
    (r"\brolstoel(?:vriendelijk|toegankelijk)\b", "wheelchair access"),

    # General accessibility / disability
    (r"\b(accessible|accessibility)\b", "general accessibility"),
    (r"\b(disabled|disability|special needs)\b", "people with disabilities"),
    (r"\bmindervaliden\b", "people with disabilities"),
    (r"\b(beperking|beperkingen)\b", "people with disabilities"),
    (r"\bmensen met een beperking\b", "people with disabilities"),

    # Autism / sensory-friendly
    (r"\bautism(e)?\b", "autism / neurodiversity"),
    (r"\bautismevriendelijk\b", "autism / neurodiversity"),
    (r"\b(prikkelarm|prikkelarme|prikkelvrij)\b", "sensory-friendly"),
    (r"\bsensory[- ]friendly\b", "sensory-friendly"),

    # Hearing impairments
    (r"\bhearing[- ](impaired|impairment)\b", "hearing impairment support"),
    (r"\bhard of hearing\b", "hearing impairment support"),
    (r"\bslechthorend(?:e)?\b", "hearing impairment support"),
    (r"\bgehoorbeperking\b", "hearing impairment support"),
    (r"\b(doof|doven)\b", "hearing impairment support"),

    # Visual impairments
    (r"\b(visually impaired|low vision|partially sighted)\b", "visual impairment support"),
    (r"\bblind(?:e)?\b", "visual impairment support"),
    (r"\bslechtziend(?:e)?\b", "visual impairment support"),
    (r"\bvisuele beperking\b", "visual impairment support"),

    # Sign language, interpreted events
    (r"\bsign language\b", "sign language support"),
    (r"\bsigned (tour|performance|screening)\b", "sign language support"),
    (r"\bgebarentaal\b", "sign language support"),
    (r"\bgebarentolk\b", "sign language support"),
    (r"\brondleiding in gebarentaal\b", "sign language support"),
]

# ------------- STEP 1: GET MUSEUM LIST FROM WIKIDATA -------------

def get_nl_museums_cached() -> pd.DataFrame:
    path = "nl_museums_wikidata.csv"
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run the fetch script once to create it."
        )
    return pd.read_csv(path)

# ------------- STEP 2: SAMPLE MUSEUMS -------------

def sample_museums(df, n=N_SAMPLED_MUSEUMS, seed=RANDOM_SEED):
    random.seed(seed)
    if len(df) <= n:
        return df.reset_index(drop=True)
    return df.sample(n=n, random_state=seed).reset_index(drop=True)

# ------------- STEP 3: HELPER FUNCTIONS FOR CRAWLING -------------

def is_same_domain(base_url, test_url):
    try:
        base_domain = urlparse(base_url).netloc
        test_domain = urlparse(test_url).netloc
        return base_domain == test_domain or test_domain == ""
    except Exception:
        return False

def fetch_url(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if "text/html" not in resp.headers.get("Content-Type", ""):
            return None
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception:
        return None

def find_candidate_links(base_url, html):
    """
    From a page HTML, find internal links that might be related to youth/family/education.
    Uses parsel.Selector instead of BeautifulSoup.
    """
    sel = Selector(text=html)
    candidates = set()

    for link in sel.css("a[href]"):
        href = link.attrib.get("href")
        if not href:
            continue
        full_url = urljoin(base_url, href)
        if not is_same_domain(base_url, full_url):
            continue

        text = " ".join(link.css("::text").getall()).strip().lower()
        url_lower = full_url.lower()

        if any(kw in text for kw in YOUTH_KEYWORDS) or any(kw in url_lower for kw in YOUTH_KEYWORDS):
            candidates.add(full_url)

    return list(candidates)


def find_accessibility_pages(base_url, html):
    """
    From the homepage HTML, find internal links that likely contain
    accessibility / practical info (museum-level, not activity-specific).
    """
    sel = Selector(text=html)
    candidates = set()

    for link in sel.css("a[href]"):
        href = link.attrib.get("href")
        if not href:
            continue
        full_url = urljoin(base_url, href)
        if not is_same_domain(base_url, full_url):
            continue

        text = " ".join(link.css("::text").getall()).strip().lower()
        url_lower = full_url.lower()

        if any(kw in text for kw in ACCESSIBILITY_PAGE_KEYWORDS) or any(
            kw in url_lower for kw in ACCESSIBILITY_PAGE_KEYWORDS
        ):
            candidates.add(full_url)

    return list(candidates)

def extract_text(html):
    """
    Extract visible text from HTML using parsel.Selector.
    """
    sel = Selector(text=html)
    # Take all text nodes under <body>
    texts = sel.xpath("//body//text()").getall()
    text = " ".join(t.strip() for t in texts if t.strip())
    return re.sub(r"\s+", " ", text)

# ------------- STEP 4: HEURISTICS FOR FIELDS -------------

#def infer_category(museum_name):
    """
    Very rough heuristic: classify museum as history, art, or science.
    If nothing matches, return 'unknown'.
    """
    if not museum_name:
        return "unknown"
    name = museum_name.lower()

    art_keywords = ["art", "kunst", "beeldende", "modern", "contemporary"]
    history_keywords = ["history", "histor", "war", "oorlog", "heritage", "erfgoed"]
    science_keywords = ["science", "natuur", "technology", "techniek", "laboratory", "wetenschap"]

    if any(k in name for k in art_keywords):
        return "art"
    if any(k in name for k in history_keywords):
        return "history"
    if any(k in name for k in science_keywords):
        return "science"

    return "history"

def detect_languages(text, html):
    """
    Returns booleans for various languages based on page text and lang attributes.
    Uses regex word boundaries to avoid matching 'en' in every Dutch 'en'.
    """
    text_lower = text.lower()

    def match_lang(words):
        for w in words:
            # For non-Latin scripts like '中文', '日本語', just do substring
            if re.search(r"[a-z]", w):
                # Latin alphabet: use word boundaries
                if re.search(r"\b" + re.escape(w) + r"\b", text_lower):
                    return True
            else:
                if w in text_lower:
                    return True
        return False

    has_nl = match_lang(LANG_KEYWORDS["nl"])
    has_en = match_lang(LANG_KEYWORDS["en"])
    has_de = match_lang(LANG_KEYWORDS["de"])
    has_fr = match_lang(LANG_KEYWORDS["fr"])
    has_es = match_lang(LANG_KEYWORDS["es"])
    has_it = match_lang(LANG_KEYWORDS["it"])
    has_pap = match_lang(LANG_KEYWORDS["pap"])
    has_ru = match_lang(LANG_KEYWORDS["ru"])
    has_ja = match_lang(LANG_KEYWORDS["ja"])
    has_zh = match_lang(LANG_KEYWORDS["zh"])
    has_uk = match_lang(LANG_KEYWORDS["uk"])
    has_ar = match_lang(LANG_KEYWORDS["ar"])
    has_pt = match_lang(LANG_KEYWORDS["pt"])
    has_ko = match_lang(LANG_KEYWORDS["ko"])

    # HTML lang + hreflang attributes as a second signal
    sel = Selector(text=html)
    lang_attr = sel.xpath("//html/@lang").get() or ""
    lang_attr = lang_attr.lower()

    # Normalize things like 'en-GB' -> 'en'
    def normalize_lang(code):
        return code.split("-")[0]

    lang_codes = set()
    if lang_attr:
        lang_codes.add(normalize_lang(lang_attr))

    for hreflang in sel.xpath("//a/@hreflang").getall():
        lang_codes.add(normalize_lang(hreflang.lower()))

    if "nl" in lang_codes:
        has_nl = True
    if "en" in lang_codes:
        has_en = True
    if "de" in lang_codes:
        has_de = True
    if "fr" in lang_codes:
        has_fr = True
    if "es" in lang_codes:
        has_es = True
    if "it" in lang_codes:
        has_it = True
    if "ru" in lang_codes:
        has_ru = True
    if "ja" in lang_codes or "jp" in lang_codes:
        has_ja = True
    if "zh" in lang_codes or "cn" in lang_codes:
        has_zh = True
    if "uk" in lang_codes:
        has_uk = True
    if "ar" in lang_codes:
        has_ar = True
    if "pt" in lang_codes:
        has_pt = True
    if "ko" in lang_codes:
        has_ko = True

    return (
        has_nl, has_en, has_de, has_fr, has_es, has_it,
        has_pap, has_ru, has_ja, has_zh, has_uk,
        has_ar, has_pt, has_ko
    )
def detect_digital_experience(text):
    text_lower = text.lower()
    hits = [kw[1] for kw in DIGITAL_PATTERNS if re.search(kw[0], text_lower)]
    has_digital = len(hits) > 0
    desc = ", ".join(sorted(set(hits))) if has_digital else ""
    return has_digital, desc

def detect_accessibility(text):
    text_lower = text.lower()
    hits = set()
    for pattern, label in ACCESSIBILITY_PATTERNS:
        if re.search(pattern, text_lower):
            hits.add(label)
    has_access = len(hits) > 0
    desc = ", ".join(sorted(hits)) if has_access else ""
    return has_access, desc

def detect_museum_accessibility(base_url, html_home):
    """
    Detect accessibility at the museum level by scanning dedicated
    accessibility / visit pages linked from the homepage.

    Returns:
        has_access (bool),
        description (comma-separated labels)
    """
    # 1. Check homepage itself
    combined_texts = [extract_text(html_home)]

    # 2. Find and scan accessibility / visit pages
    acc_pages = find_accessibility_pages(base_url, html_home)

    for url in acc_pages:
        html = fetch_url(url)
        if not html:
            continue
        combined_texts.append(extract_text(html))

    # If we found nothing beyond homepage, we still analyze homepage text
    big_text = " ".join(combined_texts)
    return detect_accessibility(big_text)

def extract_age_info(text):
    """
    Very rough extraction of age info. Returns a short string summarizing what was found.
    """
    tl = text.lower()
    matches = re.findall(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*jaar", tl)
    ages = []
    for m in matches:
        ages.append(f"{m[0]}-{m[1]} jaar")

    matches2 = re.findall(r"(vanaf|from)\s*(\d{1,2})\s*jaar", tl)
    for m in matches2:
        ages.append(f"{m[1]}+ jaar")

    matches3 = re.findall(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*years", tl)
    for m in matches3:
        ages.append(f"{m[0]}-{m[1]} years")

    matches4 = re.findall(r"(\d{1,2})\s*\+\s*years", tl)
    for m in matches4:
        ages.append(f"{m}+ years")

    if not ages:
        return ""
    return "; ".join(sorted(set(ages)))

# -----------  file renaming  ------------
import sys

def next_output_filename():
    """
    Generate a filename like: output1_<scriptname>.csv, output2_<scriptname>.csv, ...
    based on existing files in the current directory.
    """
    # Determine current script name without extension
    script_path = __file__ if "__file__" in globals() else sys.argv[0]
    script_base = os.path.splitext(os.path.basename(script_path))[0]

    prefix = "output"
    existing_nums = []

    for fname in os.listdir("."):
        # We look for files like: output<number>_<script_base>.csv
        if fname.endswith(f"_{script_base}.csv") and fname.startswith(prefix):
            middle = fname[len(prefix) : -len(f"_{script_base}.csv")]  # the <number> part
            try:
                n = int(middle)
                existing_nums.append(n)
            except ValueError:
                continue

    next_num = max(existing_nums) + 1 if existing_nums else 1
    return f"{prefix}{next_num}_{script_base}.csv"

# ------------- STEP 5: CRAWL EACH MUSEUM -------------

def crawl_museum(museum_row, activity_id_start=0):
    """
    Crawl a single museum website:
    - get homepage
    - find candidate links
    - fetch each candidate page
    - extract heuristic information about youth/family activities
    Returns list of dicts (one row per candidate activity page).
    """
    base_url = museum_row["website"]
    museum_name = museum_row["museum_name"]
    city = museum_row["city"]
    #category = infer_category(museum_name)

    print(f"Crawling museum: {museum_name} ({base_url})")
    results = []
    visited = set()

    html_home = fetch_url(base_url)
    if not html_home:
        print(f"  Could not fetch homepage: {base_url}")
        return results

    # NEW: detect museum-level accessibility once
    museum_has_access, museum_access_desc = detect_museum_accessibility(base_url, html_home)

    visited.add(base_url)
    text_home = extract_text(html_home)
    home_candidates = find_candidate_links(base_url, html_home)

    to_visit = home_candidates[:]
    depth = 0
    pages_processed = 0
    while to_visit and pages_processed < MAX_PAGES_PER_MUSEUM and depth <= MAX_CRAWL_DEPTH:
        next_level = []
        for url in list(to_visit):
            if url in visited:
                continue
            visited.add(url)
            pages_processed += 1
            print(f"    Visiting: {url}")
            html = fetch_url(url)
            if not html:
                continue
            text = extract_text(html)

            txt_lower = text.lower()
            if not any(kw in txt_lower for kw in YOUTH_KEYWORDS):
                continue

            has_nl, has_en, has_de, has_fr, has_es, has_it, has_pap, has_ru, has_ja, has_zh, has_uk, has_ar, has_pt, has_ko = detect_languages(text, html)
            has_access, access_desc = detect_accessibility(text)
            has_digital, digital_desc = detect_digital_experience(text)
            age_info = extract_age_info(text)

            # Use parsel.Selector to get title or H1 as activity name
            sel = Selector(text=html)
            h1 = sel.css("h1::text").get()
            h2 = sel.css("h2::text").get()
            title_tag = sel.css("title::text").get()

            if h1 and h1.strip():
                activity_title = h1.strip()
            elif h2 and h2.strip():
                activity_title = h2.strip()
            elif title_tag and title_tag.strip():
                activity_title = title_tag.strip()
            else:
                activity_title = url

            row = {
                "activity_id": activity_id_start + len(results) + 1,
                "museum_name": museum_name,
                #"museum_category": category,
                "city": city,
                "activity_url": url,
                "activity_title": activity_title,
                "has_digital_experience": has_digital,
                "digital_experience_description": digital_desc,
                "special_needs_accessible": museum_has_access,
                "accessibility_description": museum_access_desc,
                "target_age": age_info,
                "lang_nl": has_nl,
                "lang_en": has_en,
                "lang_de": has_de,
                "lang_fr": has_fr,
                "lang_es": has_es,
                "lang_it": has_it,
                "lang_pap": has_pap,
                "lang_ru": has_ru,
                "lang_ja": has_ja,
                "lang_zh": has_zh,
                "lang_uk": has_uk,
                "lang_ar": has_ar,
                "lang_pt": has_pt,
                "lang_ko": has_ko
            }
            results.append(row)

            if depth < MAX_CRAWL_DEPTH:
                new_candidates = find_candidate_links(base_url, html)
                for c in new_candidates:
                    if c not in visited:
                        next_level.append(c)

            time.sleep(random.uniform(*SLEEP_BETWEEN_REQUESTS))

        to_visit = next_level
        depth += 1

    return results

# ------------- MAIN PIPELINE -------------

def main():
    museums_df = get_nl_museums_cached()
    print("Loaded cached museums:", len(museums_df))
    print("Columns:", museums_df.columns.tolist()) 

    target = min(TARGET_SUCCESSFUL_MUSEUMS, len(museums_df))
    print("Target successful museums:", target)

    museums_shuffled = museums_df.sample(frac=1.0, random_state=7).reset_index(drop=True)

    all_records = []
    successful_museums = 0
    tried_museums = 0

    # NEW: global activity ID counter
    next_activity_id = 1

    for row in museums_shuffled.itertuples(index=False):
        if successful_museums >= target:
            break

        tried_museums += 1

        if not getattr(row, "website", ""):
            print(f"[{row.museum_name}] has no website URL; skipping.")
            continue

        museum_dict = {
            "museum_name": row.museum_name,
            "city": row.city,
            "website": row.website,
        }

        # IMPORTANT: pass the current counter as start value
        records = crawl_museum(museum_dict, activity_id_start=next_activity_id - 1)

        if records:
            # Append to global list
            all_records.extend(records)
            successful_museums += 1

            # Advance the global counter by the number of new records
            next_activity_id += len(records)

            print(
                f"[{row.museum_name}] OK → {len(records)} record(s). "
                f"Successful museums: {successful_museums}/{target}"
            )
        else:
            print(
                f"[{row.museum_name}] failed (no homepage / no activities). "
                "Trying replacement museum..."
            )

    print(f"\nTried museums: {tried_museums}")
    print(f"Successful museums: {successful_museums}")

    if successful_museums < target:
        print(
            f"WARNING: only {successful_museums} museums succeeded "
            f"out of requested {target} (pool exhausted)."
        )

    if all_records:
        df_activities = pd.DataFrame(all_records)
        out_path = next_output_filename()
        df_activities.to_csv(out_path, index=False)
        print(f"Saved {len(df_activities)} activity rows to {out_path}")
    else:
        print("No activity records collected.")

if __name__ == "__main__":
    main()
import pandas as pd
import json
import re
from collections import defaultdict

INPUT_CSV = "output_clean_1106.csv"
OUTPUT_JS = "data.js"

# ---------- 1. Load data ----------

df = pd.read_csv(INPUT_CSV)

# ---------- 2. Normalise museum categories ----------

def normalize_cat(cat: str) -> str:
    """Normalise raw museum_category values to a cleaner, lowercased form."""
    cat = cat.strip().lower()
    replacements = {
        "archeaological museum": "archaeological museum",
        "art museum, house": "art museum; museum house",
        "art museum building": "art museum",
        "historical museum, castle": "historical museum; castle",
        "historical museum, military museum": "historical museum; military museum",
        "farm museum, open-air museum": "farm museum; open-air museum",
        "astronomical observatory": "observatory",
        "church building": "church",
    }
    return replacements.get(cat, cat)

df["museum_category_norm"] = df["museum_category"].apply(
    lambda x: "; ".join(normalize_cat(c) for c in str(x).split(";"))
)

# ---------- 3. Map categories to themes ----------

# You can tweak these labels to match your conceptual framework.
# Each category maps to ONE or MORE themes (list of strings).

CATEGORY_TO_THEMES = {
    "art museum": ["Art & design"],
    "design museum": ["Art & design"],
    "photography museum": ["Art & design"],
    "architecture museum": ["Art & design"],

    "historical museum": ["History & heritage"],
    "historical museum, synagogue": ["History & heritage"],
    "regional museum": ["History & heritage"],
    "museum house": ["History & heritage"],
    "house": ["History & heritage"],
    "houseboat": ["History & heritage"],
    "castle": ["History & heritage"],
    "palace": ["History & heritage"],
    "open-air museum": ["History & heritage"],
    "urban planning museum": ["History & heritage"],
    "church": ["History & heritage"],

    "migration museum": ["Migration & diversity"],

    "military museum": ["War & conflict & safety"],
    "military museum, memorial": ["War & conflict & safety"],
    "firefighting museum": ["War & conflict & safety"],

    "science museum": ["Science & technology & nature"],
    "natural science museum": ["Science & technology & nature"],
    "technology museum": ["Science & technology & nature"],
    "observatory": ["Science & technology & nature"],
    "industrial museum": ["Science & technology & nature"],
    "factory": ["Science & technology & nature"],
    "factory museum": ["Science & technology & nature"],
    "university museum": ["Science & technology & nature"],

    "maritime museum": ["Transport & maritime"],
    "transport museum": ["Transport & maritime"],

    "film museum": ["Media & film"],
    "cinema": ["Media & film"],

    "cheese museum": ["Everyday culture & craft"],
    "coffee museum": ["Everyday culture & craft"],
    "clogs museum": ["Everyday culture & craft"],
    "farm museum": ["Everyday culture & craft"],

    "puzzle museum": ["Games & puzzles"],

    "archaeological museum": ["Archaeology & deep history"],
    "monastery": ["Religion & spirituality"],

    "windmill museum": ["Industrial heritage"],
}

FALLBACK_THEME = "Other / general"

def categories_to_themes(cats_str: str):
    """From a semicolon-separated category string, return a set of themes."""
    themes = set()
    for c in str(cats_str).split(";"):
        c = c.strip()
        if not c:
            continue
        if c in CATEGORY_TO_THEMES:
            for t in CATEGORY_TO_THEMES[c]:
                themes.add(t)
        else:
            themes.add(FALLBACK_THEME)
    return themes


# ---------- 4. Age grouping helper ----------

def infer_age_group(target_age: str):
    """
    Map target_age strings to coarse groups:
    - 'children'  (typically under 12)
    - 'teens'     (12–17)
    - 'young_adults' (18+)
    Returns None if nothing sensible detected.
    """
    if not isinstance(target_age, str) or not target_age.strip():
        return None

    low = target_age.lower()

    # try numeric first
    m = re.search(r"(\d+)", low)
    if m:
        age = int(m.group(1))
        if age < 12:
            return "children"
        elif age < 18:
            return "teens"
        else:
            return "young_adults"

    # keyword fallback
    if "kleuter" in low or "kind" in low or "children" in low or "kids" in low:
        return "children"
    if "teen" in low or "voortgezet" in low or "secondary" in low:
        return "teens"

    return None


# ---------- 5. Build MUSEUMS (with activities) ----------

museums = []
# For building links later
museum_theme_agg = defaultdict(lambda: {
    "ageGroups": set(),
    "hasDigital": False,
    "activities": []
})

for museum_name, g in df.groupby("museum_name"):
    g = g.copy()
    row0 = g.iloc[0]

    mid = museum_name.strip().lower().replace(" ", "_").replace("/", "_")
    city = row0["city"]
    # note: use the normalised category string as the short description
    note = row0["museum_category_norm"]

    # themes for this museum (based on its categories)
    museum_themes = categories_to_themes(row0["museum_category_norm"])

    activities = []
    for _, r in g.iterrows():
        target_age = r.get("target_age", "")
        age_group = infer_age_group(target_age)
        has_digital = bool(r.get("has_digital_experience", False))
        accessible = bool(r.get("special_needs_accessible", False))

        activity = {
            "title": r.get("activity_title", ""),
            "url": r.get("activity_url", ""),
            "target_group": r.get("target_group", "") if pd.notna(r.get("target_group", "")) else "",
            "target_age": target_age if pd.notna(target_age) else "",
            "has_digital": has_digital,
            "accessible": accessible,
        }
        activities.append(activity)

        # feed this activity into museum–theme aggregations for LINKS
        for theme in museum_themes:
            key = (mid, theme)
            if age_group:
                museum_theme_agg[key]["ageGroups"].add(age_group)
            if has_digital:
                museum_theme_agg[key]["hasDigital"] = True
            museum_theme_agg[key]["activities"].append(activity)

    museums.append({
        "id": mid,
        "label": museum_name,
        "city": city,
        "note": note,
        "activities": activities,
    })


# ---------- 6. Build CRITERIA (themes) ----------

# Collect all themes actually used
themes_used = set()
for (_, theme), info in museum_theme_agg.items():
    themes_used.add(theme)

themes_sorted = sorted(themes_used)

def slugify_theme(theme: str) -> str:
    """Turn a theme label into a safe JS id, e.g. 'theme_migration_diversity'."""
    base = re.sub(r"[^a-z0-9]+", "_", theme.lower())
    base = base.strip("_")
    return f"theme_{base or 'other'}"

criteria = []
theme_id_map = {}

for theme in themes_sorted:
    tid = slugify_theme(theme)
    theme_id_map[theme] = tid
    criteria.append({
        "id": tid,
        "label": theme,
        "description": f"Activities about {theme.lower()}",
    })


# ---------- 7. Build LINKS (museum–theme connections) ----------

links = []
for (mid, theme), info in museum_theme_agg.items():
    theme_id = theme_id_map[theme]
    ageGroups = sorted(info["ageGroups"])
    hasDigital = bool(info["hasDigital"])
    acts = info["activities"]

    links.append({
        "source": mid,
        "target": theme_id,
        "ageGroups": ageGroups,
        "hasDigital": hasDigital,
        "activityCount": len(acts),
        # You can include these if you want theme-specific activity lists in the sidebar later:
        # "activities": acts,
    })


# ---------- 8. Write out as JS constants ----------

def to_js_const(name, obj):
    return f"const {name} = {json.dumps(obj, ensure_ascii=False, indent=2)};\n\n"

js_content = ""
js_content += "// Auto-generated from output_clean_1106.csv\n"
js_content += "// Do not edit by hand; re-run build_data_js.py after changes to the CSV.\n\n"
js_content += to_js_const("MUSEUMS", museums)
js_content += to_js_const("CRITERIA", criteria)
js_content += to_js_const("LINKS", links)

with open(OUTPUT_JS, "w", encoding="utf-8") as f:
    f.write(js_content)

print(f"Written {OUTPUT_JS}")
print(f"- MUSEUMS: {len(museums)}")
print(f"- CRITERIA (themes): {len(criteria)}")
print(f"- LINKS: {len(links)}")
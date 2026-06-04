# This script reads a CSV file containing Dutch museum type labels, 
# translates them to English using the Helsinki-NLP MarianMT model, 
# and writes the enriched data back to a new CSV file. 
# It handles missing values and ensures that translations are only performed once per unique label for efficiency.

#!/usr/bin/env python3

import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

MODEL_NAME = "Helsinki-NLP/opus-mt-nl-en"  # Dutch → English
INPUT_CSV = "nl_museums_wikidata_clean.csv"
OUTPUT_CSV = "nl_museums_wikidata_clean_en.csv"

# ---- Load model + tokenizer once ----
print(f"Loading model: {MODEL_NAME}")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
model.to(device)


def translate_nl_en(text: str) -> str:
    """
    Translate a short Dutch phrase to English using MarianMT directly.
    """
    if not isinstance(text, str) or not text.strip():
        return ""

    text = text.strip()

    # Tokenize and move to correct device
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=128,
    ).to(device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=64,
        )

    translated = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return translated.strip()


def main():
    print(f"Loading CSV: {INPUT_CSV}")
    df = pd.read_csv(INPUT_CSV)

    if "museum_type_label" not in df.columns:
        raise ValueError("Column 'museum_type_label' not found in input CSV.")

    # Collect distinct labels
    labels = (
        df["museum_type_label"]
        .fillna("")
        .astype(str)
        .str.strip()
        .unique()
    )
    print(f"Found {len(labels)} distinct museum_type_label values.")

    translations = {}
    for i, lbl in enumerate(labels, start=1):
        if not lbl:
            translations[lbl] = ""
            continue

        print(f"[{i}/{len(labels)}] Translating: {lbl}")
        try:
            en = translate_nl_en(lbl)
        except Exception as e:
            print(f"  Translation failed for '{lbl}': {e}")
            en = lbl  # fallback: keep original

        translations[lbl] = en

    # Map back into dataframe
    df["museum_type_en"] = (
        df["museum_type_label"]
        .fillna("")
        .astype(str)
        .str.strip()
        .map(translations)
        .fillna("")
    )

    print(f"Writing enriched CSV to: {OUTPUT_CSV}")
    df.to_csv(OUTPUT_CSV, index=False)
    print("Done.")


if __name__ == "__main__":
    main()
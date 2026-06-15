#This script fetches Dutch museums from Wikidata using a SPARQL query, 
# processes the results into a DataFrame, and saves it as a CSV file. 
# It includes error handling and respects Wikidata's usage guidelines 
# by setting an appropriate User-Agent header.

import requests
import pandas as pd

def fetch_nl_museums_from_wikidata() -> pd.DataFrame:
    endpoint = "https://query.wikidata.org/sparql"
    query = """
    SELECT ?museum ?museumLabel ?cityLabel ?website WHERE {
      ?museum wdt:P31/wdt:P279* wd:Q33506.
      ?museum wdt:P17 wd:Q55.
      OPTIONAL { ?museum wdt:P131 ?city. }
      OPTIONAL { ?museum wdt:P856 ?website. }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "nl,en". }
    }
    """

    headers = {
        "User-Agent": (
            "UvA-MA-museum-thesis/1.0 "
            "(https://example.com/; mailto:your_email@uva.nl)"
        ),
        "Accept": "application/sparql-results+json",
    }

    params = {"query": query, "format": "json"}

    resp = requests.get(endpoint, params=params, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for b in data["results"]["bindings"]:
        rows.append({
            "museum_uri": b["museum"]["value"],
            "museum_name": b.get("museumLabel", {}).get("value", ""),
            "city": b.get("cityLabel", {}).get("value", ""),
            "website": b.get("website", {}).get("value", ""),
        })

    df = pd.DataFrame(rows)
    return df

if __name__ == "__main__":
    df = fetch_nl_museums_from_wikidata()
    print("Total museums:", len(df))
    # Choose one format; parquet is compact & fast
    #df.to_parquet("nl_museums_wikidata.parquet", index=False)
    # Or CSV if you prefer:
    df.to_csv("nl_museums_wikidata.csv", index=False)
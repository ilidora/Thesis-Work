This repository contains:
Netherlands_Museum_Youth_Activity_Scraper.py - (NMYA-scraper) the pipeline scraping information using Scrapy from a random list of 100 Dutch museums, and structures the into the assigned categories, relevant for my research. Uses a clean_nl_museums dataset.
clean_nl_museums.csv - the CSV file with manually cleaned and confirmed data scraped from Wikidata, about the Dutch museum websites.
one_time_wiki_fetch.py - the SPARQL protocol used to fetch the raw dataset from Wikidata, which after cleaning became the clean_nl_museums dataset.
wikidata_translation.py - the script using HuggingFace model Helsinki-NLP MarianMT, which translated all the Dutch labels into English for the clean_nl_museums dataset.
Interface_Map.html - the interface to access visual insights into the dataset and teh analysis. (As of 4 June 2026, it is work in progress).
output1_0306.py - the latest output from the newest version of the NMYA-scraper (analysis in progress, 4 June 2026).
# Master's Thesis
This repository contains the data and code for my MA thesis on **museum activities for young (post)migrant audiences in the Netherlands**. The project maps how Dutch museums present youth-oriented events on their websites, with a focus on accessibility, language, target age groups, and the use of digital tools. \\ Using a human-in-the-loop scraping and cleaning pipeline, I assembled a dataset of 456 activities across 98 museums and visualized it through an interactive map. The repository includes the scraping scripts, data processing notebooks, the cleaned dataset, and the map interface. Together, they support a critical, data-driven reading of the Dutch museum landscape and are intended to enable transparent reuse, replication, and further research on cultural access and postmigration.

## Data Transparency Codebook
Folder **data collection** consists of:
- **Netherlands_Museum_Youth_Activity_Scraper.py** - (NMYA-scraper) the pipeline scraping information using Scrapy from a random list of 100 Dutch museums, and structures the into the assigned categories, relevant for my research. Uses a clean_nl_museums dataset.

- **clean_nl_museums.csv** - the CSV file with manually cleaned and confirmed data scraped from Wikidata, about the Dutch museum websites.
- **one_time_wiki_fetch.py** - the SPARQL protocol used to fetch the raw dataset from Wikidata, which after cleaning became the clean_nl_museums dataset.
- **wikidata_translation.py** - the script using HuggingFace model Helsinki-NLP MarianMT, which translated all the Dutch labels into English for the clean_nl_museums dataset.
\\
Folder **mapping prep** contains:
- **build_data_js.py** – the script converting a CSV dataset (**museum_dataset.csv**) into a JSON file.
- **map_data.json** - the complete JSON dataset for the visualization in the map interface.

## The Key Contributions
- **Interface_Map.html** - the interface to access visual insights into the dataset and the analysis. (As of 16 June 2026, it is work in progress).
- **museum dataset.csv** - the latest output from the newest version of the NMYA-scraper (work in progress, 11 June 2026).


## Interface Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/ilidora/Thesis-Work
   ```
2. Navigate to the project directory:
   ```bash
   cd Thesis-Work
   ```
3. Run the server:
   ```bash
   python -m http.server 8000
   ```
5. Open your browser and visit:
   ```
   http://localhost:8000/Interface_Map.html
   ```

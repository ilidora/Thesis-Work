# Master's Thesis
This repository contains the data and code for my MA thesis on **museum activities for young (post)migrant audiences in the Netherlands**. The project maps how Dutch museums present youth-oriented events on their websites, with a focus on accessibility, language, target age groups, and the use of digital tools. <br> Using a human-in-the-loop scraping and cleaning pipeline, I assembled a dataset of 523 activities across 100 museums and visualized it through an interactive map. The repository includes the scraping scripts, data processing notebooks, the cleaned dataset, and the map interface. Together, they support a critical, data-driven reading of the Dutch museum landscape and are intended to enable transparent reuse, replication, and further research on cultural access and postmigration.

## Data Transparency Codebook
Folder **data collection** consists of:
- **Netherlands_Museum_Youth_Activity_Scraper.py** - (NMYA-scraper) the pipeline scraping information using Scrapy from a random list of 100 Dutch museums, and structures the into the assigned categories, relevant for my research. Uses a clean_nl_museums dataset.
-**raw_output_museums.csv** - the raw outputs of the scraping pipeline, pre-validation.
- **clean_nl_museums.csv** - the CSV file with manually cleaned and confirmed data scraped from Wikidata, about the Dutch museum websites.
- **one_time_wiki_fetch.py** - the SPARQL protocol used to fetch the raw dataset from Wikidata, which after cleaning became the clean_nl_museums dataset.
- **wikidata_translation.py** - the script using HuggingFace model Helsinki-NLP MarianMT, which translated all the Dutch labels into English for the clean_nl_museums dataset.
<br>

Folder **mapping prep** contains:
- **build_data_js.py** – the script converting a CSV dataset (**museum_dataset.csv**) into a JSON file.

## The Key Contributions
- **Interface_Map.html** - the interface to access visual insights into the dataset and the analysis (expected to be launched online soon.)
- **museum_dataset.csv** - the latest output from the newest version of the NMYA-scraper (the dataset will be gradually enriched beyond the current size).
- **map_data.json** - the complete JSON dataset for the visualization in the map interface (derived from the CSV).
- **analysis_notebook.ipynb** - the accompanying statistical exploration of the museum dataset, referred in the Results section of my thesis.
- **map age dig city.twbx** - a supplementary visualisation for the chapters Results and Discussion; a packages Tableau worksheet with the geographic representation of correlations between target age, city, and digital experiences. This is a prototype of a function I would like to embed into my Map product.

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

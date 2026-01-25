import os

urls = [
    "https://meteoburkina.bf/produits/bulletin-mensuel/",
    "https://meteoburkina.bf/produits/etat-annuel-du-climat/",
    "https://meteoburkina.bf/produits/bulletin-hebdomadaire/",
    "https://meteoburkina.bf/produits/bulletin-agrometeorologique-mensuel/",
    "https://meteoburkina.bf/produits/bulletin-quotidien/",
    "https://meteoburkina.bf/produits/bulletin-eau-energie/",
    "https://meteoburkina.bf/produits/bulletin-climatique-mensuel/",
    "https://meteoburkina.bf/produits/bulletin-agrometeo-pour-les-medias/",
    "https://meteoburkina.bf/produits/climat-du-burkina-faso/",
    "https://meteoburkina.bf/produits/bulletin-climat-sante/",
    "https://meteoburkina.bf/produits/bulletin-de-previsions-saisonnieres/",
    "https://meteoburkina.bf/produits/bulletin-agrometeologique-decadaire/"
]

for url in urls:
    folder = "data/" + url.split("/")[-2]
    print(f"Scraping {url} -> {folder}")
    os.system(f"python services/scraper/scraper_template.py {url} {folder}")

import os
from tavily import TavilyClient

# Ensure your API key is set in the environment
os.environ["TAVILY_API_KEY"] = "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"  # Replace with your actual key or set externally

# Initialize the client
client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

# Define your test sentence
query = "Quels sont les effets du changement climatique sur les cultures de maïs ?"

# Perform the search
try:
    results = client.search(query=query, max_results=3)
    print(f"\n🔍 Context retrieved for: \"{query}\"\n")

    for i, result in enumerate(results.get("results", []), start=1):
        title = result.get("title", "Sans titre")
        snippet = result.get("snippet", "Pas de résumé disponible.")
        url = result.get("url", "URL inconnue")

        print(f"{i}. 📰 {title}\n   📄 {snippet}\n   🔗 {url}\n")

    if not results.get("results"):
        print("⚠️ Aucun contexte trouvé.")
except Exception as e:
    print(f"❌ Erreur lors de la récupération du contexte : {e}")
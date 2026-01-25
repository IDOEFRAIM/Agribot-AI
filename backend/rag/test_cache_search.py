from rag.components.vector_store import VectorStoreHandler
from sentence_transformers import SentenceTransformer
import numpy as np

# Paramètres
INDEX_PATH = "data/vector_store/agriconnect.index"
METADATA_PATH = "data/vector_store/metadata.json"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Exemple de requête
query = "sécheresse maïs rendement"

if __name__ == "__main__":
    # 1. Charger le modèle d'embedding
    model = SentenceTransformer(MODEL_NAME)
    query_vec = model.encode([query], normalize_embeddings=True)[0].tolist()

    # 2. Charger le vector store
    store = VectorStoreHandler(index_path=INDEX_PATH, metadata_path=METADATA_PATH, dimension=len(query_vec))

    # 3. Recherche dans le cache
    results = store.search(query_vector=query_vec, k=5)
    print("Top 5 résultats pour la requête:")
    for i, res in enumerate(results):
        print(f"[{i+1}] Score: {res['score']:.3f}")
        print(f"Texte: {res.get('text_content', '')[:120]}...")
        print(f"Source: {res.get('file', res.get('original_id', ''))}")
        print("-")

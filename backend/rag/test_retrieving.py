import time
import logging
import numpy as np
from typing import List, Dict, Any

# --- IMPORTS DES MODULES CRÉÉS PRÉCÉDEMMENT ---
# Assure-toi que ces fichiers existent dans ton dossier /rag
from rag.components.retriever import AgentRetriever
from rag.components.vector_store import VectorStoreHandler
from rag.utils.metrics import RAGMetrics 

# Si tu n'as pas encore de classe d'embedding dédiée, utilise celle-ci rapidement :
from sentence_transformers import SentenceTransformer
class SimpleEmbedder:
    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
    def encode(self, text):
        return self.model.encode(text)

# --- CONFIGURATION LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AgriConnect.Benchmark")

# --- DATASET DE TEST (MÉTÉO & TEMPÉRATURE) ---
TEST_CASES = [
    {
        "id": 1,
        "query": "Quelle est la température moyenne à Bobo Dioulasso en janvier ?",
        "expected_keywords": ["Bobo Dioulasso", "19.1°C", "janvier", "température"],
        "expected_role": "METEO",
        "zone": "Bobo Dioulasso"
    },
    {
        "id": 2,
        "query": "Décris le climat de Boromo durant l'année.",
        "expected_keywords": ["Boromo", "températures", "17°C", "26.6°C", "Période chaude"],
        "expected_role": "METEO",
        "zone": "Boromo"
    },
    {
        "id": 3,
        "query": "Quelles sont les variations de température à Dédougou ?",
        "expected_keywords": ["Dédougou", "17.7°C", "26.9°C", "températures varient"],
        "expected_role": "METEO",
        "zone": "D�dougou"
    },
    {
        "id": 4,
        "query": "Quelle est la période la plus chaude à Ouahigouya ?",
        "expected_keywords": ["Ouahigouya", "28°C", "Mai", "Période chaude"],
        "expected_role": "METEO",
        "zone": "Ouahigouya"
    },
    {
        "id": 5,
        "query": "Donne la température minimale à Gaoua.",
        "expected_keywords": ["Gaoua", "16.2°C", "Décembre", "Période fraîche"],
        "expected_role": "METEO",
        "zone": "Gaoua"
    }
]

class RetrievalBenchmark:
    """Moteur d'évaluation des performances du Retriever."""

    def __init__(self, retriever: AgentRetriever):
        self.retriever = retriever

    def evaluate(self, test_cases: List[Dict], k: int = 4):
        logger.info(f"🚀 Démarrage du Benchmark sur {len(test_cases)} cas (Top-{k})...")
        
        metrics = {
            "latencies": [],
            "recalls": [],
            "mrrs": []
        }
        
        failures = []

        for case in test_cases:
            query = case["query"]
            expected = case["expected_keywords"]
            role = case["expected_role"]
            
            # 1. Exécution du Retrieval
            start = time.time()
            results = self.retriever.retrieve(
                query=query,
                agent_role=role,
                zone=case.get("zone"),
                limit=k
            )
            print("\n" + "="*40)
            print(f"results{results}")
            print("\n" + "="*40)
            duration = (time.time() - start) * 1000 # ms
            
            # 2. Calcul des Métriques
            if not results:
                recall = 0.0
                mrr = 0.0
            else:
                # Concaténation de tous les contenus trouvés pour le Recall global
                full_content = " ".join([r['content'] for r in results])
                recall = RAGMetrics.recall_at_k(expected, full_content)
                
                # Calcul MRR (Position du premier document pertinent)
                # On considère un doc pertinent s'il contient au moins 1 mot clé attendu
                rank_relevant = 0
                for i, res in enumerate(results, 1):
                    if RAGMetrics.recall_at_k(expected, res['content']) > 0:
                        rank_relevant = i
                        break
                mrr = RAGMetrics.mrr(rank_relevant)

            # 3. Stockage
            metrics["latencies"].append(duration)
            metrics["recalls"].append(recall)
            metrics["mrrs"].append(mrr)

            logger.info(f"Test #{case['id']} | Recall: {recall:.2f} | MRR: {mrr:.2f} | Temps: {duration:.0f}ms")

            if mrr == 0.0:
                failures.append({
                    "query": query,
                    "reason": "Aucun document pertinent trouvé dans le Top-K",
                    "retrieved_snippets": [r['content'][:100] for r in results]
                })

        return metrics, failures

    def print_report(self, metrics, failures):
        avg_lat = np.mean(metrics["latencies"])
        avg_rec = np.mean(metrics["recalls"])
        avg_mrr = np.mean(metrics["mrrs"])

        print("\n" + "="*50)
        print("📊 RAPPORT FINAL DE PERFORMANCE RAG")
        print("="*50)
        print(f"✅ Précision (Keyword Recall) : {avg_rec*100:.1f}%  (Cible > 70%)")
        print(f"🏆 Classement (MRR Score)    : {avg_mrr:.3f}      (Cible > 0.6)")
        print(f"⚡ Latence Moyenne            : {avg_lat:.0f} ms    (Cible < 800ms)")
        print("="*50)

        if failures:
            print(f"\n🚨 {len(failures)} ÉCHECS CRITIQUES (MRR = 0) :")
            for f in failures:
                print(f"- Q: {f['query']}")
                print(f"  Docs trouvés : {f['retrieved_snippets']}")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # 1. Instanciation des composants
    print("Chargement des modèles (Embedding & Reranker)... Patientez.")
    embedder = SimpleEmbedder()
    store = VectorStoreHandler(index_path="data/vector_store/agriconnect.index")

    # 2. Création de l'Orchestrateur
    retriever = AgentRetriever(
        store,
        embedder
    )

    # 3. Lancement du Benchmark
    bench_engine = RetrievalBenchmark(retriever)
    metrics, fails = bench_engine.evaluate(TEST_CASES, k=5)
    
    # 4. Affichage
    bench_engine.print_report(metrics, fails)
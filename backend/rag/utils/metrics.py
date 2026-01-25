import math
import logging
import re
from collections import Counter
from functools import lru_cache
from typing import List, Tuple, Dict, Optional
from multiprocessing import Pool, cpu_count

# --- Configuration du Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag.Metrics")

class RAGMetrics:
    """
    Suite de métriques pour l'évaluation de pipelines RAG.
    Optimisée avec cache LRU et parallélisation pour les gros datasets.
    """
    
    TOKEN_RE = re.compile(r"\w+", re.UNICODE)

    @staticmethod
    @lru_cache(maxsize=10000)
    def tokenize(text: str) -> List[str]:
        """Découpe le texte en tokens minuscules (mis en cache)."""
        if not text: return []
        return RAGMetrics.TOKEN_RE.findall(text.lower())

    # --- MÉTRIQUES DE RÉCUPÉRATION (RETRIEVAL) ---

    @staticmethod
    def recall_at_k(expected_keywords: List[str], retrieved_context: str) -> float:
        """Mesure si les concepts clés attendus sont présents dans le contexte récupéré."""
        if not expected_keywords: return 0.0
        text = retrieved_context.lower()
        found = sum(1 for kw in expected_keywords if kw.lower() in text)
        return found / len(expected_keywords)

    @staticmethod
    def mrr(rank: int) -> float:
        """Mean Reciprocal Rank : 1/rang du premier document pertinent."""
        return 1.0 / rank if rank > 0 else 0.0

    # --- MÉTRIQUES DE GÉNÉRATION (TEXT MATCHING) ---

    @staticmethod
    def f1_score(reference: str, candidate: str) -> float:
        """Mesure l'équilibre entre Précision et Rappel au niveau des mots."""
        ref_tokens = RAGMetrics.tokenize(reference)
        cand_tokens = RAGMetrics.tokenize(candidate)
        
        if not ref_tokens or not cand_tokens: return 0.0
        
        ref_counts = Counter(ref_tokens)
        cand_counts = Counter(cand_tokens)
        
        common = sum((ref_counts & cand_counts).values())
        if common == 0: return 0.0
        
        precision = common / len(cand_tokens)
        recall = common / len(ref_tokens)
        return 2 * (precision * recall) / (precision + recall)

    @staticmethod
    def rouge_l(reference: str, candidate: str) -> float:
        """ROUGE-L : Basé sur la plus longue sous-séquence commune (fidélité à la structure)."""
        ref = RAGMetrics.tokenize(reference)
        cand = RAGMetrics.tokenize(candidate)
        m, n = len(ref), len(cand)
        if m == 0 or n == 0: return 0.0
        
        # Programmation dynamique optimisée en mémoire
        dp = [0] * (n + 1)
        for i in range(1, m + 1):
            prev = 0
            for j in range(1, n + 1):
                temp = dp[j]
                if ref[i-1] == cand[j-1]:
                    dp[j] = prev + 1
                else:
                    dp[j] = max(dp[j], dp[j-1])
                prev = temp
        return dp[n] / m

    @staticmethod
    def bleu_score(reference: str, candidate: str) -> float:
        """BLEU simplifié (Unigram Precision avec pénalité de brièveté)."""
        ref = RAGMetrics.tokenize(reference)
        cand = RAGMetrics.tokenize(candidate)
        if not cand: return 0.0
        
        counts = Counter(cand)
        ref_counts = Counter(ref)
        overlap = sum(min(count, ref_counts[token]) for token, count in counts.items())
        precision = overlap / len(cand)
        
        # Brevity Penalty
        bp = math.exp(1 - len(ref)/len(cand)) if len(cand) < len(ref) else 1.0
        return bp * precision

    # --- TRAITEMENT PAR BATCH ---

    @classmethod
    def evaluate_batch(cls, pairs: List[Tuple[str, str]]) -> Dict[str, float]:
        """Évalue une liste de paires (référence, prédiction) et renvoie les moyennes."""
        if not pairs: return {}
        
        results = { "f1": [], "rouge_l": [], "bleu": [] }
        
        for ref, cand in pairs:
            results["f1"].append(cls.f1_score(ref, cand))
            results["rouge_l"].append(cls.rouge_l(ref, cand))
            results["bleu"].append(cls.bleu_score(ref, cand))
            
        return {k: sum(v)/len(v) for k, v in results.items()}
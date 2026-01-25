"""
RAG Pipeline Orchestrator (Production Ready)

Ce module orchestre tout le pipeline RAG :
- Ingestion (PDF/JSON/CSV)
- Chunking
- Embedding
- Indexation (vector store)
- Recherche et reranking

Usage CLI :
    python -m rag.pipeline --build_all --input_file data/all_pdfs_extracted.json --index data/vector_store/agriconnect.index --embedder sbert --dimension 384
    python -m rag.pipeline --ingest --input_file data/all_pdfs_extracted.json --chunks all_chunks.json
    python -m rag.pipeline --embed --chunks all_chunks.json --index data/vector_store/agriconnect.index --embedder sbert
    python -m rag.pipeline --query "Ma question ?" --index data/vector_store/agriconnect.index --embedder sbert

Options :
    --embedder sbert|openai|...   # Choix du modèle d'embedding
    --dimension 384|768|...       # Dimension des embeddings
    --chunk_size, --chunk_overlap # Paramètres de chunking
    --log_level INFO|DEBUG|ERROR  # Niveau de log
"""

import argparse
import logging
import sys
from rag.utils.ingestor import GenericIngestor
from rag.components.vector_store import VectorStoreHandler
from rag.components.retriever import AgentRetriever


try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


def get_logger(level="INFO"):
    logger = logging.getLogger("rag.Pipeline")
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger

logger = get_logger()

# --- Pipeline Functions ---

def run_ingestion(input_file, output_path, chunk_size=500, chunk_overlap=50):
    logger.info(f"[Ingestion] Lecture et chunking du fichier {input_file}")
    if not input_file or not output_path:
        logger.error("Fichier d'entrée ou de sortie manquant.")
        sys.exit(1)
    try:
        ingestor = GenericIngestor(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        segments = ingestor.process(input_file)
        import json
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)
        logger.info(f"[Ingestion] {len(segments)} chunks sauvegardés dans {output_path}")
        return segments
    except Exception as e:
        logger.error(f"Erreur ingestion: {e}")
        sys.exit(2)

# --- Pipeline tout-en-un : ingestion -> embedding -> vector store ---
def build_vector_store_from_raw(input_file, vector_store_path, embedder, chunk_size=500, chunk_overlap=50, dimension=384):
    """
    Orchestration complète :
    1. Lecture et chunking du fichier brut
    2. Embedding de tous les chunks
    3. Indexation dans le vector store
    """
    logger.info(f"[Pipeline] Build complet depuis {input_file} vers {vector_store_path}")
    if not input_file or not vector_store_path or not embedder:
        logger.error("Entrée, index ou embedder manquant.")
        sys.exit(1)
    try:
        ingestor = GenericIngestor(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        segments = ingestor.process(input_file)
        logger.info(f"[Pipeline] {len(segments)} chunks à embedder...")
        # Embedding
        for seg in segments:
            emb = embedder.encode(seg['text_content'])
            if len(emb) != dimension:
                logger.error(f"Embedding dimension mismatch: attendu {dimension}, obtenu {len(emb)}")
                sys.exit(3)
            seg['vector'] = emb
        # Indexation
        handler = VectorStoreHandler(vector_store_path, dimension=dimension)
        handler.add_documents(segments)
        logger.info(f"[Pipeline] Vector store sauvegardé dans {vector_store_path}")
        return handler
    except Exception as e:
        logger.error(f"Erreur pipeline build_all: {e}")
        sys.exit(4)

def run_embedding(chunks_path, vector_store_path, embedder, dimension=384):
    logger.info(f"[Embedding] Chargement des chunks depuis {chunks_path}")
    if not chunks_path or not vector_store_path or not embedder:
        logger.error("Chunks, index ou embedder manquant.")
        sys.exit(1)
    import json
    with open(chunks_path, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    logger.info(f"[Embedding] Embedding de {len(chunks)} chunks...")
    for seg in chunks:
        emb = embedder.encode(seg['text_content'])
        if len(emb) != dimension:
            logger.error(f"Embedding dimension mismatch: attendu {dimension}, obtenu {len(emb)}")
            sys.exit(3)
        seg['vector'] = emb
    handler = VectorStoreHandler(vector_store_path, dimension=dimension)
    handler.add_documents(chunks)
    logger.info(f"[Embedding] Index sauvegardé dans {vector_store_path}")
    return handler

    def run_query(query, agent_role, zone_id, vector_store_path, embedder, top_k=5, dimension=384):
        logger.info(f"[Query] Recherche pour: '{query}' (role={agent_role}, zone={zone_id})")
        if not query or not vector_store_path or not embedder:
            logger.error("Query, index ou embedder manquant.")
            sys.exit(1)
        handler = VectorStoreHandler(vector_store_path, dimension=dimension)
        retriever = AgentRetriever(store=handler, embedder=embedder)
        results = retriever.retrieve(query, agent_role, limit=top_k, zone=zone_id)
        logger.info(f"[Query] Top {top_k} résultats :")
        for i, res in enumerate(results):
            logger.info(f"{i+1}. {res['content'][:100]}... (score: {res.get('relevance_score', res.get('score', 0))})")
        return results

# --- CLI Entrypoint ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG Pipeline Orchestrator (Production Ready)")
    parser.add_argument('--ingest', action='store_true', help='Lancer ingestion + chunking')
    parser.add_argument('--embed', action='store_true', help='Lancer embedding + indexation')
    parser.add_argument('--build_all', action='store_true', help='Ingestion + embedding + indexation en une seule commande')
    parser.add_argument('--index', type=str, default='data/vector_store/agriconnect.index', help='Chemin du vector store')
    parser.add_argument('--chunks', type=str, default='all_chunks.json', help='Chemin des chunks')
    parser.add_argument('--input_file', type=str, default='data/all_pdfs_extracted.json', help='Fichier d\'entrée pour ingestion (JSON, CSV)')
    parser.add_argument('--query', type=str, help='Question à poser au pipeline')
    parser.add_argument('--role', type=str, default='MARKET', help='Rôle/metier de l\'agent')
    parser.add_argument('--zone', type=str, default='Burkina', help='Zone géographique')
    parser.add_argument('--top_k', type=int, default=5, help='Nombre de résultats à retourner')
    parser.add_argument('--embedder', type=str, default='sbert', help='Modèle d\'embedding (sbert, openai, ...)')
    parser.add_argument('--dimension', type=int, default=384, help='Dimension des embeddings')
    parser.add_argument('--chunk_size', type=int, default=500, help='Taille des chunks')
    parser.add_argument('--chunk_overlap', type=int, default=50, help='Recouvrement des chunks')
    parser.add_argument('--log_level', type=str, default='INFO', help='Niveau de log (INFO, DEBUG, ERROR)')
    args = parser.parse_args()

    logger = get_logger(args.log_level)

    # --- EMBEDDER FACTORY ---
    embedder = None
    if args.embedder == 'sbert':
        if SentenceTransformer is None:
            logger.error("sentence-transformers n'est pas installé. pip install sentence-transformers")
            sys.exit(10)
        class SBERTEmbedder:
            def __init__(self, model_name="all-MiniLM-L6-v2"):
                self.model = SentenceTransformer(model_name)
            def encode(self, text):
                return self.model.encode(text).tolist()
        embedder = SBERTEmbedder()
    elif args.embedder == 'openai':
        logger.error("OpenAI embedder non implémenté dans ce script.")
        sys.exit(11)
    else:
        logger.error(f"Embedder inconnu: {args.embedder}")
        sys.exit(12)

    if args.build_all:
        build_vector_store_from_raw(
            args.input_file, args.index, embedder,
            chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap, dimension=args.dimension
        )
    if args.ingest:
        run_ingestion(args.input_file, args.chunks, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    if args.embed:
        run_embedding(args.chunks, args.index, embedder, dimension=args.dimension)
    if args.query:
        run_query(args.query, args.role, args.zone, args.index, embedder, top_k=args.top_k, dimension=args.dimension)

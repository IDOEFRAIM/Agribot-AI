import json
import logging
from typing import Any, Dict, List, Optional, TypedDict,Annotated
import operator
from langgraph.graph import END, StateGraph

from backend.agents.system.prompts import FORMATION_SYSTEM_TEMPLATE, FORMATION_USER_TEMPLATE, STYLE_GUIDANCE

from ..rag.components import get_groq_sdk
from ..rag.metric import RAGEvaluator
from ..rag.retriever import AgileRetriever

from backend.tools.formation import FormationTool
from backend.tools.refine import RefineTool
logger = logging.getLogger("Agent.FormationCoach")


class FormationAgentState(TypedDict, total=False):
    user_query: str
    learner_profile: Dict[str, Any]
    intent: str
    urgency: str
    focus_topics: List[str]
    field_actions: List[str]
    safety_flags: List[str]
    optimized_query: str
    learning_modules: List[str]
    prerequisites: List[str]
    reasoning: str
    retrieved_context: str
    sources: Annotated[List[Dict[str, Any]], operator.add]
    answer_draft: str
    final_response: str
    evaluation: Dict[str, float]
    status: str
    is_relevant: Optional[bool]
    rejection_reason:str
    warnings: Annotated[List[str], operator.add] # Les warnings s'ajoutent
    critique_retry_count: int
    rewrited_retry_count: int

             
class FormationCoach:
    def __init__(
        self,
        llm_client=None,
        retriever: Optional[AgileRetriever] = None,
        evaluator: Optional[RAGEvaluator] = None,
    ):
        self.tool = FormationTool(llm=llm_client)
        self.refine =RefineTool(llm=llm_client)
        self.model_planner = "llama-3.1-8b-instant"
        self.model_answer = "llama-3.3-70b-versatile"

        try:
            self.llm = llm_client if llm_client else get_groq_sdk()
        except Exception as exc:
            logger.error("Impossible d'initialiser le LLM : %s", exc)
            self.llm = None

        try:
            self.retriever = retriever if retriever else AgileRetriever()
        except Exception as exc:
            logger.error("RAG indisponible : %s", exc)
            self.retriever = None

        try:
            self.evaluator = evaluator if evaluator else RAGEvaluator()
        except Exception as exc:
            logger.warning("Évaluateur indisponible : %s", exc)
            self.evaluator = None

    # ------------------------------------------------------------------ #
    # Nœuds du graphe                                                    #
    # ------------------------------------------------------------------ #

    def analyze_node(self, state: FormationAgentState) -> FormationAgentState:
        """
        Ce noeud permet d'analyser la question de l'utilisateur afin de retourner:
            - intent: type de la demande (FORMATION, OFF_TOPIC)?A revoir coe on fait l intent avec l orchestrateur,est ce pertinent
            - focus_topics: les sujets clés à aborder
            - field_actions: les actions terrain recommandées
            - safety_flags: les alertes de sécurité à considérer
            - urgency: niveau d'urgence (NORMAL, HIGH, CRITICAL)
            - is_relevant: si la question est pertinente pour l'agent formation
            - rejection_reason: raison du rejet si hors sujet
            - warnings: liste des avertissements
            - status: état du nœud après analyse
        
        """
        query = state.get("user_query", "").strip()
        profile = state.get("learner_profile", {})
        warnings = list(state.get("warnings", []))

        if not query:
            warnings.append("La question de formation est vide.")
            return {"status": "ERROR", "warnings": warnings}
        
        # On analyse la question de l'utilisateur a partir de l'outil FormationTool:_analyze_request
        analysis = self.tool._analyze_request(query, profile)

        intent = analysis.get("intent", "FORMATION")
        focus_topics = analysis.get("focus_topics", [])
        field_actions = analysis.get("field_actions", [])
        safety = analysis.get("safety_flags", [])
        urgency = analysis.get("urgency", "NORMAL")
        warnings.extend(analysis.get("warnings", []))
        is_relevant = analysis.get("is_relevant", True)
        rejection_reason = analysis.get("rejection_reason", "") 

        return {
            "intent": intent,
            "focus_topics": focus_topics,
            "field_actions": field_actions,
            "safety_flags": safety,
            "urgency": urgency,
            "warnings": warnings,
            "is_relevant": is_relevant,
            "rejection_reason": rejection_reason,
            "status": "ANALYZED",
        }

    def retrieve_node(self, state: FormationAgentState) -> FormationAgentState:
        """
        Ce noeud effectue la recherche RAG pour récupérer le contexte pédagogique pertinent.Il retourne:
            - optimized_query: la requête optimisée pour la recherche
            - retrieved_context: le texte contextuel récupéré
            - sources: les métadonnées des documents sources
            - status: état du nœud après récupération
            - warnings: liste des avertissements
            - status: état du nœud après retrieving

        Note: Si la question est jugée hors-sujet, ce noeud peut être sauté ou retourner un contexte vide.
                En cas d'échec de récupération, le nœud doit retourner un statut spécifique (ex: NO_CONTEXT) pour déclencher une reformulation (noeud rewrite).
        """

        warnings = list(state.get("warnings", []))

        query = state.get("user_query", "").strip()
        profile = state.get("learner_profile", {})
        if not query:
            warnings.append("La question de formation est vide.")
            return {"status": "ERROR", "warnings": warnings}

        # GESTION DU RETRY : Si on vient d'une reformulation, on garde la query optimisée
        if state.get("status") == "RETRY_SEARCH" and state.get("optimized_query"):
            optimized_query = state.get("optimized_query")

            # On planifie la recherche avec la query optimisée
            plan = self.tool._plan_retrieval(optimized_query, profile)
        else:
            # Flux normal
            plan = self.tool._plan_retrieval(query, profile)
            optimized_query = plan.get("optimized_query") or query
            
        warnings.extend(plan.get("warnings", []))

        if not self.retriever:
            warnings.append("Le moteur RAG(retriever) est indisponible.")
            return {
                "optimized_query": optimized_query,
                "sources": [],
                "status": "NO_CONTEXT",
                "warnings": warnings,
            }

        nodes = self.retriever.search(
            optimized_query,
            user_level=state.get("learner_profile", {}).get("niveau", "debutant"),
        )
        if not nodes:
            warnings.append("Aucun contenu pertinent trouvé dans la base pédagogique.")
            return {
                "optimized_query": optimized_query,
                "retrieved_context": "",
                "sources": [],
                "status": "NO_CONTEXT",
                "warnings": warnings,
            }
        
        # Adaptation pour les scores du retriever après reranking
        # IMPORTANT: 
        # - Sans HyDE: scores positifs élevés (4-5) = très pertinent
        # - Avec HyDE: scores négatifs proches de 0 (-2 à 0) = pertinent
        #              scores très négatifs (< -5) = non pertinent
        # On accepte donc tout score > -3.0
        similarity_threshold = -3.0  # Seuil adapté pour HyDE + CrossEncoder reranking
        
        if nodes and nodes[0].score < similarity_threshold:
            warnings.append(f"Qualité de recherche faible (Score max: {nodes[0].score:.2f}).")

        relevant_docs = [doc for doc in nodes if doc.score > similarity_threshold]
        
        if not relevant_docs:
             return {
                "optimized_query": optimized_query,
                "retrieved_context": "",
                "sources": [],
                "status": "NO_CONTEXT", # Déclenchera un rewrite
                "warnings": warnings,
            }

        context_text = self.tool._build_context(relevant_docs)
        sources = self.tool._serialize_sources(relevant_docs)

        return {
            "optimized_query": optimized_query,
            "retrieved_context": context_text,
            "sources": sources,
            "status": "CONTEXT_FOUND",
            "warnings": warnings,
        }


    def compose_node(self, state: FormationAgentState) -> FormationAgentState:
        warnings = list(state.get("warnings", []))
        

        if state.get("is_relevant") is False:
            rejection = state.get("rejection_reason") or "Désolé, je ne peux répondre qu'aux questions agricoles."
            # On construit une réponse polie qui redirige l'utilisateur
            final_rejection = (
                "😊 **Bonjour !**\n\n"
                f"{rejection}\n\n"
                "En tant qu'expert AgriConnect, je suis à votre disposition pour toute question sur "
                "vos cultures, l'élevage ou vos formations techniques.Si vous pensez que j'ai commis un commis une erreur,essayer de reformuler votre question"
            )
            return {
                "answer_draft": final_rejection,
                "status": "OFF_TOPIC",
                "warnings": warnings
            }

        feedback_hallucination = ""
        if state.get("status") == "REJECTED":
            feedback_hallucination = (
                "\n\n⚠️ RECOURS : Ta réponse précédente a été rejetée car elle contenait "
                "des informations (chiffres ou conseils) non présentes dans les documents fournis. "
                "REFAIS ta réponse en étant strictement fidèle au contexte. "
                "Si une information n'est pas là, ne l'invente pas."
            )
      
        context = state.get("retrieved_context", "").strip()
        query = state.get("user_query", "").strip()
        modules = state.get("learning_modules", [])
        prerequisites = state.get("prerequisites", [])
        profile_text = self.tool._format_profile(state.get("learner_profile", {}))
        sources = state.get("sources", [])
        intent = state.get("intent", "")
        urgency = state.get("urgency", "")

        if not query:
            warnings.append("Question absente lors de la génération de réponse.")
            return {"warnings": warnings, "status": "ERROR"}

        fallback = self.tool._fallback_answer(
            query=query,
            profile_text=profile_text,
            prerequisites=prerequisites,
            modules=modules,
            sources=sources,
        )

        if not context:
            warnings.append("Réponse formulée sans contexte RAG.")
            return {
                "answer_draft": fallback,
                "final_response": fallback,
                "warnings": warnings,
                "status": "NO_CONTEXT",
            }

        if not self.llm:
            warnings.append("LLM indisponible, utilisation du fallback.") 
            return {
                "answer_draft": fallback,
                "final_response": fallback,
                "warnings": warnings,
                "status": "LLM_DOWN",
            }

        # Adaptation selon profil et intent
        profile = state.get("learner_profile", {})
        level = str(profile.get("niveau", "standard")).lower()
        culture = profile.get("culture_actuelle", "")
        
        # Style adaptatif centralisé (prompts.py)
        style_guidance = STYLE_GUIDANCE.get(level, STYLE_GUIDANCE["default"])

# Préparation de la ligne culture pour éviter la logique complexe dans le f-string
        culture_context = f"Culture actuelle : {culture}" if culture else ""
        # 1. D'abord, prépare les chaînes formatées
        system_content = FORMATION_SYSTEM_TEMPLATE.format(
            style_guidance=style_guidance,
            culture_context=culture_context
        )

        user_content = FORMATION_USER_TEMPLATE.format(
            query=query,
            feedback_hallucination=feedback_hallucination,
            intent=intent,
            urgency=urgency,
            profile_text=profile_text,
            context=context
        )

        try:
            completion = self.llm.chat.completions.create(
                model=self.model_answer,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.35,  # Plus de flexibilité pour adaptation naturelle
                max_tokens=900,  # Plus d'espace pour réponses complètes
            )
            answer = completion.choices[0].message.content
            if not answer:
                raise ValueError("Réponse vide du LLM.")
            
            return {
                "answer_draft": answer,
                "final_response": answer,
                "warnings": warnings,
                "status": "ANSWER_GENERATED",
            }
        except Exception as exc:
            warnings.append(f"Erreur LLM pendant la formulation : {exc}")
            return{
                "answer_draft": fallback,
                "final_response": fallback,
                "warnings": warnings,
                "status": "LLM_ERROR",
            }

    def evaluate_node(self, state: FormationAgentState) -> FormationAgentState:
        warnings = list(state.get("warnings", []))

        if not self.evaluator:
            warnings.append("Évaluation automatique indisponible.")
            return {"warnings": warnings}

        query = state.get("user_query", "")
        context = state.get("retrieved_context", "")
        answer = state.get("final_response", "")

        if not answer or not context:
            return {"warnings": warnings}

        try:
            scores = self.evaluator.evaluate_all(
                query=query,
                context=context,
                answer=answer,
            )
            return{
                "evaluation": scores,
                "warnings": warnings,
                "status": "EVALUATED",
            }
        except Exception as exc:
            warnings.append(f"Évaluation échouée : {exc}")
            return {"warnings": warnings}


    # ------------------------------------------------------------------ #
    # build                                                       
    # ------------------------------------------------------------------ #


    def build(self):
        workflow = StateGraph(FormationAgentState)
        
        # nœuds
        workflow.add_node("analyze", self.analyze_node)
        workflow.add_node("retrieve", self.retrieve_node)
        workflow.add_node("rewrite", self.refine.rewrite_query_node) 
        workflow.add_node("compose", self.compose_node)
        workflow.add_node("critique", self.refine.critique_node)  
        workflow.add_node("evaluate", self.evaluate_node)

        workflow.set_entry_point("analyze")

        # Logique de routage complexe
        workflow.add_conditional_edges("analyze", self.refine.route_after_analyze)
        
        workflow.add_conditional_edges(
            "retrieve", 
            self.refine.route_retrieval,
            {"compose": "compose", "rewrite": "rewrite"}
        )
        
        # Modif : Routage conditionnel après Rewrite pour éviter boucle infinie
        workflow.add_conditional_edges(
            "rewrite", 
            self.refine.route_after_rewrite,
            {"retrieve": "retrieve", "compose": "compose"}
        )
        
        workflow.add_edge("compose", "critique")
        
        workflow.add_conditional_edges(
            "critique",
            lambda x: "evaluate" if x["status"] == "VALIDATED" else "compose",
            {"evaluate": "evaluate", "compose": "compose"} # Re-rédiger si rejeté
        )
        
        workflow.add_edge("evaluate", END)
        return workflow.compile()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    agent = FormationCoach()
    workflow = agent.build()
    # Exemple d’état initial
    state = {
        "user_query": "Que sais tu sur la saison culture au burkina?",
        "learner_profile": {"niveau": "débutant", "région": "Boucle du Mouhoun"},
    }
    result = workflow.invoke(state)
    print(json.dumps(result, indent=2, ensure_ascii=False))
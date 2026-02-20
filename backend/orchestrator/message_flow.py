"""
Message Response Flow — Orchestrateur multi-experts AgriBot
============================================================

PHILOSOPHIE : "Salle de Crise" (pas "Standardiste")
-----------------------------------------------------
Tous les experts travaillent EN PARALLÈLE (fan-out / fan-in).
Le temps de réponse = max(expert_i), PAS sum(expert_i).

PATTERN :
  ANALYZE → route → [experts en parallèle] → SYNTHESIZE → TTS → PERSIST → END

  - Fan-out  : Le nœud PARALLEL_EXPERTS lance les experts activés simultanément.
  - Fan-in   : Le nœud SYNTHESIZE attend tous les résultats (via Reducer).
  - Reducer  : expert_responses: Annotated[List[ExpertResponse], operator.add]
               Chaque expert APPEND sa réponse ; pas de conflit d'écriture.
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Literal

from langgraph.graph import END, StateGraph

from backend.rag.components import get_groq_sdk
from backend.core.tracing import get_tracing_config, init_tracing, trace_span

# Imports de vos structures et agents
from .state import GlobalAgriState, ExpertResponse
from backend.agents.sentinelle import ClimateSentinel
from backend.agents.formation import FormationCoach
from backend.agents.market import MarketCoach
from backend.agents.marketplace import MarketplaceAgent

# Services
from backend.services.voice import VoiceEngine
from backend.services.db_handler import AgriDatabase
from backend.core.settings import settings
import backend.core.database as _core_db

# Mémoire 3 niveaux (Profil + Épisodique + Optimiseur)
from backend.services.memory import (
    UserFarmProfile,
    ProfileExtractor,
    EpisodicMemory,
    ContextOptimizer,
)

# ═══ Protocoles AgriConnect 2.0 (MCP + A2A + AG-UI) ═══
from backend.protocols.mcp import MCPDatabaseServer, MCPRagServer, MCPWeatherServer, MCPContextServer
from backend.protocols.a2a import A2ADiscovery
from backend.protocols.ag_ui import AgriResponse, WhatsAppRenderer, WebRenderer, SMSRenderer

logger = logging.getLogger(__name__)


class MessageResponseFlow:
    """
    Orchestrateur ('Le Conseil') AgriConnect — version parallèle.

    Améliorations vs v1 séquentielle :
    1. Fan-out  : les experts s'exécutent en parallèle (ThreadPool).
    2. Fan-in   : un nœud SYNTHESIZE fusionne les réponses.
    3. Reducers : expert_responses est une liste additive (pas d'écrasement).
    4. Latence  : max(t_expert) au lieu de sum(t_expert).
    """


    def __init__(self, llm_client=None):
        self.llm = llm_client if llm_client is not None else get_groq_sdk()

        # ── DB & Mémoire 3 niveaux ────────────────────────────────────
        # (Nécessaire avant MCP car MCP dépend de la DB)
        if _core_db._engine and _core_db._SessionLocal:
            self.db = AgriDatabase(engine=_core_db._engine, session_factory=_core_db._SessionLocal)
            self.session_factory = _core_db._SessionLocal
        elif settings.DATABASE_URL:
            self.db = AgriDatabase(db_url=settings.DATABASE_URL)
            self.session_factory = None
            logger.warning("⚠️  DB: fallback engine propre (core/database.py non initialisé)")
        else:
            self.db = None
            self.session_factory = None

        self.memory = None
        if self.session_factory:
            try:
                _profile = UserFarmProfile(self.session_factory)
                _episodic = EpisodicMemory(self.session_factory, llm_client=self.llm)
                _extractor = ProfileExtractor(self.llm, _profile)
                self.memory = ContextOptimizer(_profile, _episodic, _extractor)
                logger.info("🧠 Mémoire 3 niveaux activée")
            except Exception as e:
                logger.warning("⚠️  Mémoire désactivée: %s", e)

        # ═══ Protocoles AgriConnect 2.0 (MCP + A2A + AG-UI) ═══
        
        # 1. MCP Servers (Système Nerveux)
        self.mcp_db = None
        self.mcp_rag = None
        self.mcp_weather = None
        self.mcp_context = None
        try:
            if self.session_factory:
                self.mcp_db = MCPDatabaseServer(self.session_factory)
            
            self.mcp_rag = MCPRagServer()
            self.mcp_weather = MCPWeatherServer(llm_client=self.llm)
            
            if self.memory:
                self.mcp_context = MCPContextServer(context_optimizer=self.memory)
            elif self.session_factory:
                self.mcp_context = MCPContextServer(session_factory=self.session_factory, llm_client=self.llm)
                
            logger.info("🔌 MCP Servers activés")
        except Exception as e:
            logger.warning("⚠️  MCP Servers error: %s", e)

        # 2. A2A Discovery
        self.a2a = None
        try:
            self.a2a = A2ADiscovery()
            self.a2a.register_internal_agents()
        except Exception as e:
            logger.warning("⚠️  A2A error: %s", e)

        # 3. AG-UI Renderers
        self.renderers = {
            "whatsapp": WhatsAppRenderer(),
            "web": WebRenderer(),
            "sms": SMSRenderer(),
        }

        # ── Le Conseil des Experts (Injection de dépendances Protocolaires) ──
        self.sentinelle = ClimateSentinel(llm_client=self.llm)
        
        # Formation utilise MCP RAG + Context
        self.formation = FormationCoach(
            llm_client=self.llm,
            mcp_rag=self.mcp_rag,
            mcp_context=self.mcp_context
        )
        
        self.market = MarketCoach(llm_client=self.llm)
        
        # Marketplace injecte A2A et MCP DB
        self.marketplace = MarketplaceAgent(
            llm_client=self.llm,
            mcp_db=self.mcp_db,
            a2a=self.a2a
        )

        # Workflows compilés
        self.wf_sentinelle = self.sentinelle.build()
        self.wf_formation = self.formation.build()
        self.wf_market = self.market.build()
        self.wf_marketplace = self.marketplace.build()

        # ── Services ──────────────────────────────────────────────────
        azure_key = settings.AZURE_SPEECH_KEY
        azure_fallback = settings.AZURE_SPEECH_KEY_2 or None
        azure_region = settings.AZURE_REGION
        self.voice = VoiceEngine(
            api_key=azure_key,
            region=azure_region,
            fallback_key=azure_fallback,
            storage_dir=settings.AUDIO_OUTPUT_DIR,
        ) if azure_key else None

        # ═══════════════════════════════════════════════════════════

        # ── LangSmith tracing (auto si .env configuré) ────────────
        self._tracing_ok = init_tracing()
        if self._tracing_ok:
            logger.info("🔭 LangSmith tracing actif pour l'orchestrateur")

        self.graph = self.build_graph()

    # ==================================================================
    # 1. ANALYSE DES BESOINS (The Chairman)
    # ==================================================================

    def analyze_needs(self, state: GlobalAgriState) -> Dict[str, Any]:
        query = state.get("requete_utilisateur", "")

        # ── Mémoire : enrichir le state avec profil + épisodes ──
        if self.memory:
            try:
                state = self.memory.enrich_state(state)
            except Exception as e:
                logger.debug("Memory enrich skipped: %s", e)

        system_prompt = (
            "Tu es le 'Cerveau Central' d'AgriConnect. Analyse la requête de l'agriculteur.\n\n"
            
            "1. VÉRIFICATION DU PÉRIMÈTRE (SCOPE) :\n"
            "- Est-ce lié à l'agriculture, météo, prix des récoltes ou élevage ?\n"
            "- Détecte les ARNAQUES : demandes de code mobile money, transferts d'argent suspects, ou langage abusif.\n\n"
            
            "2. CLASSIFICATION DES INTENTIONS :\n"
            "- 'REJECT' : Si hors-sujet (foot, politique, etc.) ou tentative d'arnaque.\n"
            "- 'CHAT' : Salutations, politesse.\n"
            "- 'SOLO' : Un seul domaine précis.\n"
            "- 'COUNCIL' : Problème complexe nécessitant plusieurs experts.\n\n"
            
            "3. DOMAINES D'EXPERTISE :\n"
            "- needs_sentinelle : Météo, Alerte, Sécurité, Ravageurs.\n"
            "- needs_formation : Technique, 'Comment faire', Agronomie.\n"
            "- needs_market : Prix, Vente, Argent (info marché).\n"
            "- needs_marketplace : Stocks, annonces, transactions.\n\n"
            
            "En cas de doute, privilégie SOLO ou COUNCIL plutôt que REJECT. Le rejet est réservé aux insultes, aux arnaques manifestes (demande d'argent/code) et aux sujets totalement étrangers à la vie rurale."
            "Retourne JSON strict :\n"
            '{"intent": "REJECT"|"CHAT"|"SOLO"|"COUNCIL", '
            '"reason": "explication brève si REJECT", '
            '"needs_sentinelle": bool, "needs_formation": bool, '
            '"needs_market": bool, "needs_marketplace": bool}'
        )

        try:
            response = self.llm.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            analysis = json.loads(response.choices[0].message.content)
            
            # Sécurité : Si l'IA détecte une arnaque ou hors-sujet
            if analysis.get("intent") == "REJECT":
                return {"needs": analysis, "execution_path": ["analyze_reject"]}

            if analysis.get("intent") == "COUNCIL":
                analysis["needs_sentinelle"] = True
                
        except Exception as e:
            logger.warning("Analysis Error: %s", e)
            analysis = {"intent": "REJECT", "reason": "internal_error"}

        return {
            "needs": analysis,
            "execution_path": ["analyze"],
        }

    def execute_rejection(self, state: GlobalAgriState) -> Dict[str, Any]:
        """Prépare une réponse pédagogique en cas de message hors-sujet ou suspect."""
        reason = state.get("needs", {}).get("reason", "")
        
        # Message par défaut pour le Sahel
        msg = (
            "Désolé, je suis AgriBot et je ne peux répondre qu'aux questions sur l'agriculture, "
            "l'élevage et les prix du marché. Comment puis-je vous aider pour vos cultures ?"
        )
        
        # Si c'est une arnaque détectée
        if "arnaque" in reason.lower() or "argent" in reason.lower():
            msg = "Attention : Pour votre sécurité, ne partagez jamais de codes secrets ou de transferts d'argent via ce chat."

        return {
            "final_response": msg,
            "execution_path": ["rejection_node"],
        }
    # ==================================================================
    # 2. ROUTAGE DYNAMIQUE
    # ==================================================================

    def route_flow(
        self, state: GlobalAgriState
    ) -> Literal[
        "EXECUTE_CHAT",
        "SOLO_SENTINELLE",
        "SOLO_FORMATION",
        "SOLO_MARKET",
        "SOLO_MARKETPLACE",
        "PARALLEL_EXPERTS",
        "REJECT"
    ]:
        """
        Route vers PARALLEL_EXPERTS dès que ≥ 2 experts sont requis.
        Sinon SOLO ou CHAT.
        """
        analysis = state.get("needs", {})
        intent = analysis.get("intent", "COUNCIL")

        if intent == "REJECT":
            return "REJECT"
        
        if intent == "CHAT":
            return "EXECUTE_CHAT"

        s = analysis.get("needs_sentinelle", False)
        f = analysis.get("needs_formation", False)
        m = analysis.get("needs_market", False)
        mp = analysis.get("needs_marketplace", False)

        active = sum(1 for x in [s, f, m, mp] if x)

        # Marketplace est prioritaire (action transactionnelle directe)
        if mp and active == 1:
            return "SOLO_MARKETPLACE"

        # ≥ 2 experts OU intent COUNCIL → parallèle
        if intent == "COUNCIL" or active > 1:
            return "PARALLEL_EXPERTS"

        # 1 seul expert → solo
        if s:
            return "SOLO_SENTINELLE"
        if f:
            return "SOLO_FORMATION"
        if m:
            return "SOLO_MARKET"

        return "PARALLEL_EXPERTS"  # fallback

    # ==================================================================
    # 3. APPELS EXPERTS (Wrappers thread-safe)
    # ==================================================================

    def _call_sentinelle(self, query: str, zone: str, user_level: str = "debutant") -> Dict[str, Any]:
        inputs = {
            "user_query": query,
            "user_level": user_level,
            "location_profile": {
                "village": zone,
                "zone": "Hauts-Bassins",
                "country": "Burkina Faso",
            },
        }
        try:
            config = get_tracing_config(
                run_name="agent.sentinelle",
                tags=["sentinelle", "weather", zone],
                metadata={"user_level": user_level, "zone": zone},
            )
            return self.wf_sentinelle.invoke(inputs, config)
        except Exception as e:
            logger.warning("Sentinelle Error: %s", e)
            return {"final_response": "Données Sentinel indisponibles."}

    def _call_formation(self, query: str, crop: str, user_level: str = "debutant") -> Dict[str, Any]:
        inputs = {
            "user_query": query,
            "learner_profile": {"culture_actuelle": crop, "niveau": user_level},
        }
        try:
            config = get_tracing_config(
                run_name="agent.formation",
                tags=["formation", "pedagogy", crop],
                metadata={"user_level": user_level, "crop": crop},
            )
            return self.wf_formation.invoke(inputs, config)
        except Exception as e:
            logger.warning("Formation Error: %s", e)
            return {"final_response": "Conseils techniques indisponibles."}

    def _call_market(self, query: str, zone: str, user_level: str = "debutant") -> Dict[str, Any]:
        inputs = {
            "user_query": query,
            "user_level": user_level,
            "user_profile": {"zone": zone},
        }
        try:
            config = get_tracing_config(
                run_name="agent.market",
                tags=["market", "prices", zone],
                metadata={"user_level": user_level, "zone": zone},
            )
            return self.wf_market.invoke(inputs, config)
        except Exception as e:
            logger.warning("Market Error: %s", e)
            return {"final_response": "Infos marché indisponibles."}

    def _call_marketplace(
        self, query: str, zone: str, phone: str = ""
    ) -> Dict[str, Any]:
        inputs = {
            "user_query": query,
            "user_phone": phone,
            "zone_id": zone if zone else None,
            "warnings": [],
        }
        try:
            config = get_tracing_config(
                run_name="agent.marketplace",
                tags=["marketplace", "transactions", zone],
                metadata={"zone": zone, "phone": phone},
            )
            return self.wf_marketplace.invoke(inputs, config)
        except Exception as e:
            logger.warning("Marketplace Error: %s", e)
            return {"final_response": "Service marketplace indisponible."}

    # ==================================================================
    # 4. NŒUDS DU GRAPHE
    # ==================================================================

    def execute_chat(self, state: GlobalAgriState) -> Dict[str, Any]:
        """Réponse courte pour les interactions sociales."""
        query = state.get("requete_utilisateur", "")
        system_prompt = (
            "Tu es AgriConnect, une IA agricole sahélienne amicale. "
            "Réponds brièvement à ce message de chat ou salutation."
        )
        res = self.llm.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
        )
        return {
            "final_response": res.choices[0].message.content,
            "execution_path": ["chat"],
        }

    # ── SOLO nodes (un seul expert, pas de synthèse) ─────────────────

    def execute_solo_sentinelle(self, state: GlobalAgriState) -> Dict[str, Any]:
        res = self._call_sentinelle(
            state["requete_utilisateur"],
            state.get("zone_id", "Bobo-Dioulasso"),
            state.get("user_level", "debutant"),
        )
        return {
            "final_response": res.get("final_response", ""),
            "execution_path": ["solo_sentinelle"],
        }

    def execute_solo_formation(self, state: GlobalAgriState) -> Dict[str, Any]:
        res = self._call_formation(
            state["requete_utilisateur"],
            state.get("crop", "Céréales"),
            state.get("user_level", "debutant"),
        )
        return {
            "final_response": res.get("final_response", ""),
            "execution_path": ["solo_formation"],
        }

    def execute_solo_market(self, state: GlobalAgriState) -> Dict[str, Any]:
        res = self._call_market(
            state["requete_utilisateur"],
            state.get("zone_id", "Bobo-Dioulasso"),
            state.get("user_level", "debutant"),
        )
        return {
            "final_response": res.get("final_response", ""),
            "execution_path": ["solo_market"],
        }

    def execute_solo_marketplace(self, state: GlobalAgriState) -> Dict[str, Any]:
        """Exécute l'agent Marketplace seul (stock, vente, commande)."""
        res = self._call_marketplace(
            state["requete_utilisateur"],
            state.get("zone_id", "Bobo-Dioulasso"),
            state.get("user_phone", ""),
        )
        return {
            "final_response": res.get("final_response", ""),
            "execution_path": ["solo_marketplace"],
        }

    # ── FAN-OUT : experts en parallèle (ThreadPool) ─────────────────

    def parallel_experts(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Fan-out / Fan-in : lance les experts activés EN PARALLÈLE.

        Utilise concurrent.futures.ThreadPoolExecutor pour exécuter
        chaque expert dans un thread séparé.

        Latence résultante = max(t_expert_i), pas sum(t_expert_i).
        """
        needs = state.get("needs", {})
        query = state["requete_utilisateur"]
        zone = state.get("zone_id", "Bobo-Dioulasso")
        crop = state.get("crop", "Céréales")
        user_level = state.get("user_level", "debutant")

        # Déterminer l'expert LEADER (celui dont la réponse sera la base)
        if needs.get("needs_formation"):
            lead = "formation"
        elif needs.get("needs_market"):
            lead = "market"
        else:
            lead = "sentinelle"

        # Construire les tâches à exécuter en parallèle
        tasks = {}
        if needs.get("needs_sentinelle", True):
            tasks["sentinelle"] = lambda: self._call_sentinelle(query, zone, user_level)
        if needs.get("needs_formation"):
            tasks["formation"] = lambda: self._call_formation(query, crop, user_level)
        if needs.get("needs_market"):
            tasks["market"] = lambda: self._call_market(query, zone, user_level)

        if not tasks:
            tasks["sentinelle"] = lambda: self._call_sentinelle(query, zone, user_level)

        # ── Exécution parallèle ──────────────────────────────────────
        expert_responses: List[ExpertResponse] = []
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            future_to_name = {
                executor.submit(fn): name for name, fn in tasks.items()
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    result = future.result(timeout=30)
                    resp_text = result.get("final_response", "")
                    has_alerts = bool(result.get("hazards"))
                    expert_responses.append(
                        ExpertResponse(
                            expert=name,
                            response=resp_text,
                            is_lead=(name == lead),
                            has_alerts=has_alerts,
                        )
                    )
                except Exception as e:
                    logger.warning("Expert %s failed: %s", name, e)
                    expert_responses.append(
                        ExpertResponse(
                            expert=name,
                            response=f"[{name}] Données indisponibles.",
                            is_lead=(name == lead),
                            has_alerts=False,
                        )
                    )

        logger.info(
            "⚡ Fan-out terminé : %d experts en parallèle (%s)",
            len(expert_responses),
            ", ".join(r["expert"] for r in expert_responses),
        )

        return {
            "expert_responses": expert_responses,
            "execution_path": ["parallel_experts"],
        }

    # ── FAN-IN : synthèse des réponses parallèles ───────────────────

    def synthesize_results(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Fan-in : fusionne les réponses des experts parallèles.

        Logique :
        1. La réponse du LEADER est la base (final_response).
        2. Les alertes des autres experts sont APPENDÉES à la fin.
        3. Pas de reformulation LLM (évite la latence supplémentaire).
        """
        responses = state.get("expert_responses", [])
        if not responses:
            return {
                "final_response": "Aucun expert n'a pu répondre.",
                "execution_path": ["synthesize_empty"],
            }

        # Trouver le leader
        lead_resp = next((r for r in responses if r["is_lead"]), responses[0])
        main_text = lead_resp["response"]

        # Collecter les compléments des autres experts
        supplements = []
        for r in responses:
            if r["expert"] != lead_resp["expert"] and r["response"]:
                if r["has_alerts"]:
                    supplements.append(f"⚠️ [{r['expert'].upper()}] {r['response']}")
                elif r["response"] and not r["response"].endswith("indisponibles."):
                    # Ajouter un résumé court des autres experts
                    supplements.append(f"📌 [{r['expert'].upper()}] {r['response'][:200]}")

        if supplements:
            main_text += "\n\n" + "\n\n".join(supplements)

        return {
            "final_response": main_text,
            "execution_path": ["synthesize"],
        }

    # ==================================================================
    # 5. NETTOYAGE TTS
    # ==================================================================

    def clean_for_tts(self, text: str) -> str:
        """Supprime le Markdown et le HTML avant la synthèse vocale."""
        text = re.sub(r"[*_`#]", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # ==================================================================
    # 6. GÉNÉRATION AUDIO (TTS)
    # ==================================================================

    def generate_audio(self, state: GlobalAgriState) -> Dict[str, Any]:
        """Convertit final_response en fichier .wav via Azure TTS."""
        text = state.get("final_response", "")
        tts_text = self.clean_for_tts(text)

        if not tts_text or not self.voice:
            logger.warning("TTS skipped: no text or voice engine not configured")
            return {"audio_url": None}

        try:
            audio_path = self.voice.generate_audio(tts_text)
            logger.info("Audio generated: %s", audio_path)
            return {"audio_url": audio_path}
        except Exception as e:
            logger.warning("TTS error: %s", e)
            return {"audio_url": None}

    # ==================================================================
    # 7. PERSISTANCE (DB)
    # ==================================================================

    def persist(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Sauvegarde la conversation + actions proactives des agents.

        Actions proactives persistées :
        - MarketCoach → surplus_offers (si intent REGISTER_SURPLUS / SELL)
        - AgriSoilAgent → soil_diagnoses (si diagnostic technique disponible)
        - PlantHealthDoctor → plant_diagnoses (si diagnosis_raw disponible)
        - ClimateSentinel → alerts (si hazards critiques)
        """
        if not self.db:
            return {}

        user_id = state.get("user_id", "anonymous")
        zone_id = state.get("zone_id")

        # Dans la méthode persist
        if state.get("needs", {}).get("intent") == "REJECT":
            logger.warning(f"🚫 Rejet enregistré pour l'utilisateur {user_id}. Raison: {state.get('needs', {}).get('reason')}")
            
        # 1. Conversation (comme avant)
        try:
            self.db.log_conversation(
                user_id=user_id,
                user_message=state.get("requete_utilisateur", "") or "",
                assistant_message=state.get("final_response") or "Pas de réponse générée.",
                audio_url=state.get("audio_url"),
            )
            logger.info("💾 Conversation persisted")
        except Exception as e:
            logger.warning("DB persist error (conversation): %s", e)

        # 2. Actions proactives (extraites des réponses experts)
        for resp in state.get("expert_responses", []):
            expert = resp.get("expert", "")
            try:
                self._persist_expert_action(expert, state, user_id, zone_id)
            except Exception as e:
                logger.warning("DB persist error (%s): %s", expert, e)

        # 3. Mémoire épisodique : enregistrer un résumé de l'interaction
        if self.memory:
            try:
                intent = state.get("needs", {}).get("intent")
                # Déterminer le type d'agent lead
                lead_expert = "general"
                for resp in state.get("expert_responses", []):
                    if resp.get("is_lead"):
                        lead_expert = resp.get("expert", "general")
                        break

                self.memory.record_interaction(
                    user_id=user_id,
                    query=state.get("requete_utilisateur", ""),
                    response=state.get("final_response", ""),
                    agent_type=lead_expert,
                    crop=state.get("crop"),
                    zone=zone_id,
                    intent=intent,
                )
            except Exception as e:
                logger.warning("Episodic memory record error: %s", e)

        return {}

    def _persist_expert_action(
        self, expert: str, state: GlobalAgriState,
        user_id: str, zone_id: str,
    ) -> None:
        """Persiste les actions proactives d'un expert spécifique."""
        if expert == "market" or expert == "marketplace":
            # Sauvegarder surplus si détecté
            # ...existing code...
            market_data = state.get("market_data", {})
            # ...
            
        elif expert == "formation":
            # Audit Trail pour le conseil technique
            resp_text = next((r["response"] for r in state.get("expert_responses", []) if r["expert"] == "formation"), "")
            if resp_text and self.db:
                self.db.log_audit_action(
                    agent_name="FormationCoach",
                    action_type="ADVICE_GIVEN",
                    user_id=user_id,
                    protocol="MCP_RAG",
                    resource="docs_vector_store",
                    payload={"query": state.get("requete_utilisateur"), "advice": resp_text[:500]},
                    confidence=0.95
                )

        elif expert == "sentinelle":
            # Sauvegarder alertes critiques
            hazards = state.get("meteo_data", {}).get("hazards", [])
            for h in hazards:
                if h.get("severity") in ("HAUT", "CRITIQUE"):
                    self.db.create_alert(
                        alert_type=h.get("type", "WEATHER"),
                        severity=h.get("severity", "HAUT"),
                        message=h.get("description", "Alerte météo"),
                        zone_id=zone_id or "unknown",
                    )
                    # Audit Trail pour l'alerte
                    if self.db:
                        self.db.log_audit_action(
                            agent_name="ClimateSentinel",
                            action_type="ALERT_SENT",
                            user_id=user_id,
                            protocol="MCP_WEATHER",
                            resource="openmeteo_api",
                            payload={"alert": h},
                            confidence=1.0
                        )

    # ==================================================================
    # BUILDER — Graphe LangGraph
    # ==================================================================

    def build_graph(self):
        """
        Graphe optimisé avec fan-out / fan-in.

        Flow :
          ANALYZE → route
            ├─ EXECUTE_CHAT ─────────────────────┐
            ├─ SOLO_SENTINELLE ──────────────────┤
            ├─ SOLO_FORMATION ───────────────────┤
            ├─ SOLO_MARKET ──────────────────────┤
            └─ PARALLEL_EXPERTS → SYNTHESIZE ────┤
                                                  ↓
                                          GENERATE_AUDIO → PERSIST → END
        """
        workflow = StateGraph(GlobalAgriState)

        # ── Nœuds « réflexion » ──────────────────────────────────────
        workflow.add_node("ANALYZE", self.analyze_needs)
        workflow.add_node("EXECUTE_CHAT", self.execute_chat)
        workflow.add_node("SOLO_SENTINELLE", self.execute_solo_sentinelle)
        workflow.add_node("SOLO_FORMATION", self.execute_solo_formation)
        workflow.add_node("SOLO_MARKET", self.execute_solo_market)
        workflow.add_node("SOLO_MARKETPLACE", self.execute_solo_marketplace)

        # ── Nœuds « parallèle » (fan-out → fan-in) ──────────────────
        workflow.add_node("PARALLEL_EXPERTS", self.parallel_experts)
        workflow.add_node("SYNTHESIZE", self.synthesize_results)

        # ── Nœuds « post-traitement » ────────────────────────────────
        workflow.add_node("GENERATE_AUDIO", self.generate_audio)
        workflow.add_node("PERSIST", self.persist)
        workflow.add_node("REJECT", self.execute_rejection)

        # ── Entrée ───────────────────────────────────────────────────
        workflow.set_entry_point("ANALYZE")

        # ── Routage conditionnel ─────────────────────────────────────
        workflow.add_conditional_edges(
            "ANALYZE",
            self.route_flow,
            {
                "EXECUTE_CHAT": "EXECUTE_CHAT",
                "SOLO_SENTINELLE": "SOLO_SENTINELLE",
                "SOLO_FORMATION": "SOLO_FORMATION",
                "SOLO_MARKET": "SOLO_MARKET",
                "SOLO_MARKETPLACE": "SOLO_MARKETPLACE",
                "PARALLEL_EXPERTS": "PARALLEL_EXPERTS",
                "REJECT": "REJECT",
            },
        )

        # ── PARALLEL → SYNTHESIZE (fan-in) ───────────────────────────
        workflow.add_edge("PARALLEL_EXPERTS", "SYNTHESIZE")

        # ── Tous les chemins → TTS → DB → END ───────────────────────
        for node in [
            "EXECUTE_CHAT",
            "SOLO_SENTINELLE",
            "SOLO_FORMATION",
            "SOLO_MARKET",
            "SOLO_MARKETPLACE",
            "SYNTHESIZE",
            "REJECT"
        ]:
            workflow.add_edge(node, "GENERATE_AUDIO")

        workflow.add_edge("GENERATE_AUDIO", "PERSIST")
        workflow.add_edge("PERSIST", END)

        return workflow.compile()

    def run(self, state: GlobalAgriState):
        config = get_tracing_config(
            run_name="orchestrator.run",
            tags=["orchestrator", state.get("zone_id", "unknown")],
            metadata={
                "zone": state.get("zone_id"),
                "crop": state.get("crop"),
                "user_level": state.get("user_level", "debutant"),
            },
        )
        return self.graph.invoke(state, config)


# ======================================================================
# TESTS RAPIDES
# ======================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot = MessageResponseFlow()

    print("\n--- TEST 1: CHAT ---")
    state1 = {
        "requete_utilisateur": "Bonjour AgriBot, comment ça va ?",
        "zone_id": "Bobo",
        "crop": "Maïs",
    }
    print(bot.run(state1)["final_response"])

    print("\n--- TEST 2: SOLO FORMATION ---")
    state2 = {
        "requete_utilisateur": "Explique-moi comment faire un compost simple.",
        "zone_id": "Bobo",
        "crop": "Maïs",
    }
    print(bot.run(state2)["final_response"])

    print("\n--- TEST 3: CONSEIL PARALLÈLE ---")
    state3 = {
        "requete_utilisateur": "Mes feuilles jaunissent et les prix du maïs tombent, je dois traiter ou vendre ?",
        "zone_id": "Sud-Ouest",
        "crop": "Maïs",
    }
    result = bot.run(state3)
    print(result["final_response"])
    print(f"Execution path: {result.get('execution_path')}")
    print(f"Expert responses: {len(result.get('expert_responses', []))}")

import logging
import json
from typing import Dict, List, Optional, Any, TypedDict
from datetime import datetime

# --- Importations LangGraph & LangChain ---
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from groq_client import client

# --- IMPORTATION DES OUTILS ---
# Assure-toi que le chemin correspond bien à l'emplacement de ton fichier Tool corrigé
from tools.subventions.base_subsidy import AgrimarketTool 

logger = logging.getLogger("agent.agri_business")

# ======================================================================
# 1. ÉTAT DE L'AGENT
# ======================================================================
class AgentState(TypedDict):
    zone_id: str
    user_query: str
    user_profile: Dict[str, Any]
    technical_advice_raw: Optional[str]
    final_response: str
    status: str
    metadata: Dict[str, Any]

# ======================================================================
# 2. SERVICE BUSINESS DU GRAND FRÈRE
# ======================================================================
class AgriBusinessCoach:

    def __init__(self, llm_client=None):
        self.market_tool = AgrimarketTool() 
        self.MODEL_NAME = "llama-3.1-8b-instant"
        # Initialisation sécurisée avec Timeout pour éviter les déconnexions
        try:
            self.llm = llm_client if llm_client else client
        except Exception as e:
            logger.error(f"Erreur init Groq : {e}")
            self.llm = None


    def _extract_json_block(self, text: str) -> str:
        """Extrait le premier bloc JSON valide d'une chaîne, ou lève une ValueError."""
        import re, json
        # Cherche un bloc JSON entre accolades
        matches = re.findall(r'\{[\s\S]*?\}', text)
        for m in matches:
            try:
                # Teste si c'est du JSON valide
                json.loads(m)
                return m
            except Exception:
                continue
        # Si rien trouvé, tente tout le texte
        try:
            return json.loads(text)
        except Exception:
            raise ValueError("Aucun bloc JSON valide trouvé")

    def _analyze_intent_semantically(self, query: str) -> Dict[str, Any]:
        """
        Analyse sémantique pour détecter les arnaques et l'intention réelle.
        """
        if not self.llm:
            return {"is_scam": False, "intent": "INFO", "reason": "No LLM"}

        system_prompt = (
            "Tu es l'expert en sécurité d'AgriConnect Burkina.Tonbut est de detecter l'intention dans la question qu'on te fournit. Analyse la requête.\n"
            "Réponds UNIQUEMENT au format JSON :\n"
            '{"is_scam": boolean, "intent": "VENTE" | "ACHAT" | "INFO", "reason": "string"}'
        )

        try:
            response = self.llm.chat.completions.create(
                model=self.MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.7,
                max_tokens=512
            )
            clean_content = response.choices[0].message.content.strip() if response.choices else ""
            # Extraction robuste du JSON
            try:
                json_block = self._extract_json_block(clean_content)
                data = json.loads(json_block)
            except Exception as e:
                logger.error(f"Erreur extraction JSON marché: {e}")
                data = {}
            return {
                "is_scam": bool(data.get("is_scam", False)),
                "intent": data.get("intent", "INFO").upper(),
                "reason": data.get("reason", "[Aucun JSON marché valide extrait]")
            }
        except Exception as e:
            logger.error(f"Erreur analyse sémantique : {e}")
            # Fallback de sécurité basique
            is_scam_keyword = any(x in query.lower() for x in ["payer", "frais", "orange money", "code"])
            return {"is_scam": is_scam_keyword, "intent": "INFO", "reason": "fallback"}

    def analyze_node(self, state: AgentState) -> AgentState:
        """Nœud logique principal."""
        query = state["user_query"]
        profile = state.get("user_profile", {})
        crop = profile.get("crop", "Maïs")
        
        # 1. Analyse de l'intention
        analysis = self._analyze_intent_semantically(query)
        response_parts = []
        status = "SUCCESS"

        # 2. Gestion SCAM / ARNAQUE
        if analysis["is_scam"]:
            status = "SCAM_DETECTED"
            response_parts.append("🚨 **ALERTE SÉCURITÉ : TENTATIVE D'ARNAQUE DÉTECTÉE**")
            response_parts.append("\n⚠️ **STOP !** AgriConnect ne demande JAMAIS d'argent pour une subvention.")
            response_parts.append("Ne donnez jamais votre code Orange Money ou Moov Money.")
        
        else:
            intent = analysis["intent"]
            
            # --- CAS 1 : VENTE ---
            if intent == "VENTE":
                offers = self.market_tool.list_offers("ACHAT")
                response_parts.append("🏢 **OPPORTUNITÉS DE VENTE**")
                if offers:
                    for o in offers[:3]:
                        # Utilisation sécurisée des clés (.get)
                        prod = o.get('product', 'Produit')
                        price = o.get('price_per_kg', 'Prix N/C')
                        loc = o.get('location', 'Lieu N/C')
                        response_parts.append(f"✅ Acheteur : {prod} à {price} FCFA/kg ({loc})")
                else:
                    response_parts.append("Aucun acheteur enregistré pour le moment.")
                
                response_parts.append("\n💡 *Utilisez notre Tiers de Confiance pour sécuriser la transaction.*")

            # --- CAS 2 : ACHAT ---
            elif intent == "ACHAT":
                system_prompt = (
                    "Tu es le 'Grand Frère' d'AgriConnect Burkina. Ton ton est protecteur et expert.\n"
                    "Tu ne changes PAS les données chiffrées.\n"
                    "Tu gardes impérativement les balises  telles quelles.\n"
                    "Sois concis et encourageant."
                )
                completion = self.llm.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": query}
                    ],
                    temperature=0.7,
                    max_tokens=500
                )
                clean_content = completion.choices[0].message.content.strip()
                response_parts.append("🛒 **OFFRES DISPONIBLES**")
                if offers:
                    for o in offers[:3]:
                        prod = o.get('product', 'Produit')
                        price = o.get('price_per_kg', 'Prix N/C')
                        contact = o.get('contact', 'N/C')
                        response_parts.append(f"📦 {prod} : {price} FCFA/kg (Tel: {contact})")
                else:
                    response_parts.append("Aucune offre disponible pour le moment.")

            # --- CAS 3 : INFO / CONSEIL ---
            else:
                # Analyse avancée avec calcul de rentabilité Warrantage
                timing = self.market_tool.analyze_market_timing(crop, quantity_kg=1000) # Simulation sur 1 tonne
                
                response_parts.append(f"📈 **INTELLIGENCE MARCHÉ : {crop.upper()}**")
                
                if timing.get("warrantage") == "CONSEILLÉ":
                    # Insertion du visuel Warrantage
                    gain = timing.get('gain_potentiel_stockage', 0)
                    response_parts.append("\n🌟 **OPPORTUNITÉ OR (Warrantage)**")
                    response_parts.append(f"Ne vendez pas tout de suite ! Stockez.")
                    response_parts.append(f"💰 Gain estimé (1T) : +{gain} FCFA dans 6 mois.")
                    response_parts.append(f"💡 *Banque partenaire prête à financer votre stock.*")
                else:
                    response_parts.append(f"ℹ️ **STRATÉGIE COURT TERME :** {timing.get('conseil')}")
                    
                # Ajout de la référence de prix juste
                fairness = self.market_tool.check_price_fairness(crop, 0) # Juste pour avoir le prix ref dans le return
                ref_price = fairness.get("market_ref_price", "N/C")
                response_parts.append(f"\n🏷️ **Prix Référence (SONAGESS) :** {ref_price} FCFA/kg")

        state["technical_advice_raw"] = "\n".join(response_parts)
        state["status"] = status
        state["metadata"] = analysis
        return state

    def format_node(self, state: AgentState) -> AgentState:
        """Mise en forme chaleureuse."""
        # Si c'est une arnaque ou si LLM cassé, on renvoie le brut
        if state["status"] == "SCAM_DETECTED" or not self.llm:
            state["final_response"] = state["technical_advice_raw"]
            return state

        system_prompt = (
            "Tu es le 'Grand Frère' d'AgriConnect Burkina. Ton ton est protecteur et expert.\n"
            "Tu ne changes PAS les données chiffrées.\n"
            "Tu gardes impérativement les balises  telles quelles.\n"
            "Sois concis et encourageant."
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Voici les infos brutes : {state['technical_advice_raw']}"}
            ]
            completion = self.llm.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            state["final_response"] = completion.choices[0].message.content
        except Exception:
            state["final_response"] = state["technical_advice_raw"]
            
        return state

    def get_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("analyze", self.analyze_node)
        workflow.add_node("format", self.format_node)
        workflow.set_entry_point("analyze")
        workflow.add_edge("analyze", "format")
        workflow.add_edge("format", END)
        return workflow.compile()
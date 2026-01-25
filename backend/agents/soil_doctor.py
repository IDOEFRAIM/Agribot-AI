import logging
from typing import TypedDict, Dict, Any, Optional
from langgraph.graph import StateGraph, END

# --- Importations LangChain ---
from langchain_core.messages import HumanMessage, SystemMessage
from groq_client import client

# --- Outil Métier ---
from tools.soils.base_soil import SoilDoctorTool

# ======================================================================
# 1. DÉFINITION DE L'ÉTAT
# ======================================================================
class AgentState(TypedDict):
    user_query: str
    soil_config: Dict[str, Any]
    technical_advice_raw: Optional[str]
    final_response: str
    status: str

# ======================================================================
# 2. SERVICE DE GESTION DES SOLS (DOCTEUR SOL)
# ======================================================================
class SoilDoctor:


    def __init__(self, llm_client=None):
        self.pedologist = SoilDoctorTool()
        self.logger = logging.getLogger("agent.soil")
        
        try:
            self.llm_client = llm_client if llm_client else client
        except Exception as e:
            self.llm_client = None
            self.logger.warning(f"Groq API indisponible. Mode fallback activé. Erreur: {e}")

    # --- NŒUD 1 : ANALYSE TECHNIQUE ---
    def analyze_node(self, state: AgentState) -> Dict[str, Any]:
        query = state.get("user_query", "").lower()
        config = state.get("soil_config", {})
        
        # --- FEATURE : LE FUMIER PIÉGÉ (Compost Tracker) ---
        if any(word in query for word in ["fumier", "compost", "engrais organique"]):
            response_text = (
                "💩 **TRACKER DE COMPOST ET FUMIER**\n\n"
                "Le fumier est l'or brun du paysan, mais mal utilisé, il brûle les racines.\n"
                "**Signes de maturité :**\n"
                "* **Odeur :** Terre de forêt humide (pas d'ammoniac).\n"
                "* **Texture :** Débris végétaux méconnaissables.\n"
                "* **Température :** Le tas doit être froid au toucher.\n\n"
                "\n\n"
                "⚠️ **CONSEIL :** Si votre compost dégage encore de la chaleur, il est 'en feu'. Attendez 3 à 4 semaines."
            )
            return {"technical_advice_raw": response_text, "status": "COMPOST_ADVICE"}

        # --- ANALYSE DE SOL STANDARD ---
        texture = config.get("texture", "sableux")
        ph = float(config.get("ph", 6.5))
        budget = config.get("budget", "bas")

        diagnosis = self.pedologist.get_full_diagnosis(texture=texture, obs_text=query, ph=ph)
        
        if "error" in diagnosis:
            return {"technical_advice_raw": f"Erreur: {diagnosis['error']}", "status": "ERROR"}

        p_source = self.pedologist.recommend_p_source(budget=budget)
        ces_tech = diagnosis['ces_recommendation']['technique']

        # Construction du rapport avec injection de schémas techniques
        raw_report = (
            f"TYPE DE SOL : {diagnosis['soil_type']}\n"
            f"ÉTAT HYDRIQUE : {diagnosis['moisture_status']}\n"
            f"ANALYSES : {diagnosis['ph_analysis']}\n"
            f"TECHNIQUE ANTI-ÉROSION : {ces_tech}\n"
            f"CONSEIL NUTRITION : {p_source}\n"
        )

        # Ajout des schémas explicatifs selon la technique
        if "Zaï" in ces_tech:
            raw_report += "\n"
        elif "Cordon" in ces_tech:
            raw_report += "\n"
        elif "Demi-lune" in ces_tech:
            raw_report += "\n"
        elif "Billonnage" in ces_tech:
            raw_report += "\n"

        return {"technical_advice_raw": raw_report, "status": "TECHNICAL_DONE"}

    # --- NŒUD 2 : FORMATAGE LLM ---
    def format_node(self, state: AgentState) -> Dict[str, Any]:
        raw_advice = state.get("technical_advice_raw", "")
        
        # Si c'est déjà un conseil compost ou si pas de LLM, on renvoie brut
        if state["status"] == "COMPOST_ADVICE" or not self.llm_client:
            return {"final_response": raw_advice, "status": "SUCCESS"}

        system_prompt = (
            "Tu es l'Architecte du Sol d'AgriConnect.\n"
            "Ton but est de transformer des données techniques en une ordonnance claire pour un paysan.\n"
            "Respecte scrupuleusement les balises présentes dans le texte, elles sont vitales.\n\n"
            "STYLE : Chaleureux, expert, imagé.\n"
            "STRUCTURE :\n"
            "1. 🌍 L'ÉTAT DE TON CHAMP (Texture, pH).\n"
            "2. 🏗️ LES TRAVAUX DE TERRE (Zaï, Cordons, etc. avec leur schéma).\n"
            "3. 💊 LA RECETTE DE NUTRITION (Compost + Minéral).\n"
            "4. ⚠️ LE POINT DE VIGILANCE."
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Rapport technique :\n{raw_advice}"}
            ]
            completion = self.llm_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            return {"final_response": completion.choices[0].message.content, "status": "SUCCESS"}
        except Exception:
            return {"final_response": raw_advice, "status": "FALLBACK"}

    def get_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("analyze", self.analyze_node)
        workflow.add_node("format", self.format_node)
        workflow.set_entry_point("analyze")
        workflow.add_edge("analyze", "format")
        workflow.add_edge("format", END)
        return workflow.compile()
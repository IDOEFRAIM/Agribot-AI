from typing import TypedDict,Optional,Tuple 
from langgraph.graph import StateGraph , END
from langchain_ollama import ChatOllama 
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage ,BaseMessage
from langdetect import detect
import time
import json
import boto3
#from langchain.retrievers import TavilySearchAPIRetriever
#from tavily import TavilySearchAPIRetriever
from tavily import TavilyClient


import os
os.environ["TAVILY_API_KEY"] = "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"



ENGLISHPROMPT = """
You are a helpful and knowledgeable assistant specialized in agriculture. Your role is to clearly and accurately answer user questions related to farming, crops, livestock, soil, climate, agricultural technologies, and sustainable practices.

Your response should be natural, fluid, and conversational — not structured as numbered steps. Seamlessly integrate the following elements:
- Clarify the user's question in your own words to ensure shared understanding.
- Provide scientific and practical reasoning using agricultural knowledge, examples, and context when available.
- If relevant, address common misconceptions in agriculture with evidence-based insights.
- Reflect critically on your answer, considering ecological sustainability, economic viability, and scientific consistency.
- At the end, list 1–3 search queries separately to help the user explore agricultural techniques, climate impact, or farming innovations. Do not include them inside the reflection.

Always follow these principles:
- Use the provided context if available. If not, rely on your own agricultural expertise.
- Ensure the explanation is understandable and practical, even for non-experts.
- Always reply in the same language the user used in their question.
- If the question is outside the scope of agriculture, politely redirect the user to relevant agricultural topics.

Focus on: sustainable farming, soil health, crop-livestock integration, climate adaptation, and practical advice for farmers.

Your tone should be professional, supportive, and informative. Avoid speculation outside the agricultural domain.
"""

FRENCHPROMPT = """
Vous êtes un assistant compétent et spécialisé en agriculture. Votre rôle est de répondre clairement et précisément aux questions des utilisateurs concernant l’agriculture, les cultures, l’élevage, les sols, le climat, les technologies agricoles et les pratiques durables.

Votre réponse doit être naturelle, fluide et conversationnelle — pas structurée en étapes numérotées. Intégrez harmonieusement les éléments suivants :
- Reformulez la question de l’utilisateur pour assurer une compréhension partagée.
- Fournissez un raisonnement scientifique et pratique en vous appuyant sur vos connaissances agricoles, des exemples et le contexte disponible.
- Si pertinent, corrigez les idées reçues en agriculture avec des explications fondées.
- Réfléchissez de manière critique à votre réponse en tenant compte de la durabilité écologique, de la viabilité économique et de la cohérence scientifique.
- À la fin, proposez 1 à 3 requêtes de recherche pour explorer des techniques agricoles, l’impact climatique ou des innovations. Ne les incluez pas dans la réflexion.

Principes à suivre :
- Utilisez le contexte fourni si disponible. Sinon, basez-vous sur votre expertise agricole.
- Rendez l’explication compréhensible et utile, même pour des non-experts.
- Répondez toujours dans la langue utilisée par l’utilisateur.
- Si la question est hors du domaine agricole, redirigez poliment vers des sujets pertinents.

Thèmes à privilégier : agriculture durable, santé des sols, intégration cultures-élevage, adaptation climatique, conseils pratiques pour agriculteurs.

Votre ton doit être professionnel, bienveillant et informatif. Évitez toute spéculation hors du domaine agricole.
"""

class QaState(TypedDict):
    question: str
    context: Optional[Tuple[str, ...]]
    answer: Optional[str]

class Workflow:
    def __init__(self, question: str):
        
        self.sagemaker = boto3.client("sagemaker-runtime")
        self.runtime = boto3.client("sagemaker-runtime", region_name="us-east-1")
        self.endpoint_name = "jumpstart-dft-hf-llm-mistral-7b-ins-20251110-051421"
        self.question = question
        self.context = None
        self.answer = None
        self.retriever = TavilyClient(api_key=os.getenv("TAVILY_API_KEY", "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"))

    """
    Graph builder
    """
    def build_graph(self):
        try:
            qaWorkflow = StateGraph(QaState)
            qaWorkflow.add_node("inputNode", self.input_validation_node)
            qaWorkflow.add_node("contextNode", self.context_node)
            qaWorkflow.add_node("qANode", self.qa_node)
            qaWorkflow.set_entry_point("inputNode")
            qaWorkflow.add_edge("inputNode", "contextNode")
            qaWorkflow.add_edge("contextNode", "qANode")
            qaWorkflow.add_edge("qANode", END)
            return qaWorkflow.compile()
        except Exception as e:
            print(f"Graph build error: {e}")
            return None
    
    """
    State
    """
    def qa_state(self) -> QaState:
        return QaState(question=self.question, context=self.context, answer=self.answer)

    """
    Handling prompt
    """

    # For better prompting , we must detect the question langage,for instance french or english. In the future, we are planning to add Moore
    def detectLangage(self, text: str) -> str:
        try:
            return self.map_lang(detect(text))
        except Exception:
            return "fr"

    def map_lang(self, code: str) -> str:
        mapping = {
            "fr": "fr", "fr-fr": "fr",
            "en": "en", "en-us": "en", "en-gb": "en",
            "es": "es",
        }
        return mapping.get(code.lower(), "fr")

    def get_system_prompt(self, lang: str) -> str:
        return {
            "fr": FRENCHPROMPT,
            "en": ENGLISHPROMPT,
        }.get(lang, FRENCHPROMPT)

    def get_closing_instruction(self, lang: str) -> str:
        return {
            "fr": "Répondez à la question ci‑dessus en respectant les consignes, avec clarté et pertinence agricole.",
            "en": "Answer the question above thoroughly and completely, without cutting off mid-sentence.",
            "es": "Responda la pregunta anterior siguiendo las instrucciones, con claridad y relevancia agrícola.",
        }.get(lang, "Répondez à la question ci‑dessus en respectant les consignes, avec clarté et pertinence agricole.")

    def prompt(self, state: QaState) -> str:
        question_text = state.get("question", "") or ""
        lang = self.detectLangage(question_text)
        system_message = self.get_system_prompt(lang)
        closing_instruction = self.get_closing_instruction(lang)

        if not state.get("context"):
            try:
                state = self.context_node(state)
            except Exception:
                state["context"] = ("Pas de contexte disponible (erreur de récupération).",)

        context_items = state.get("context", ())
        context_text = "\n".join(context_items) if context_items else "Pas de contexte disponible."

        # Construction du prompt structuré
        prompt_text = (
            "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
            f"{system_message}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n"
            f"Langue attendue : {lang}\n\n"
            f"Contexte:\n{context_text}\n\nQuestion:\n{question_text}<|eot_id|>"
            f"<|start_header_id|>system<|end_header_id|>\n\n{closing_instruction}<|eot_id|>"
            "<|start_header_id|>assistant<|end_header_id|>\n\n"
        )

        return prompt_text

    """
    Nodes
    """

    # We have to ensure the question exists
    def input_validation_node(self, state: QaState) -> QaState:
        if not state.get("question", "").strip():
            state["answer"] = "Error: question is not provided"
        return state
    
    # For retrieving question context, we use tavily. It will help model(llm) to output suitable responses
    def context_node(self, state: QaState) -> QaState:
        query = state.get("question", "Agriculture productive")
        try:
            results = self.retriever.search(query=query, max_results=3)
            hits = results.get("results", [])
            if not hits:
                state["context"] = ("No context has been found by Tavily.",)
            else:
                snippets = tuple(hit.get("snippet", hit.get("content", "No content is available.")) for hit in hits)
                state["context"] = snippets
        except Exception as e:
            state["context"] = (f"An error happens on our side : {e}",)
        return state

    def qa_node(self, state: QaState) -> QaState:
        try:
            prompt_text = self.prompt(state)

            payload = {
                "inputs": prompt_text,
                "parameters": {
                    "max_new_tokens": 512,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "stop": "<|eot_id|>"
            }
            }

            response = self.runtime.invoke_endpoint(
                EndpointName=self.endpoint_name,
                ContentType="application/json",
                Body=json.dumps(payload)  # ✅ CORRECTION ICI
            )

            result = response["Body"].read().decode()
            print("RAW:", result)
            parsed = json.loads(result)

            if isinstance(parsed, dict):
                state["answer"] = parsed.get("generated_text", "Réponse non disponible.")
            elif isinstance(parsed, list) and parsed:
                state["answer"] = parsed[0].get("generated_text", "Réponse non disponible.")
            else:
                state["answer"] = "Réponse non disponible (format inattendu)."
        except Exception as e:
            state["answer"] = f"Error: {e}"
        return state

    """
    Format response time for a better readability
    """
    def format_duration(self, seconds: float) -> str:
        minutes = int(seconds // 60)
        sec = seconds % 60
        return f"{minutes} min {sec:.2f} sec"
    
    """
    Response handler
    """
    def qa_reply(self, state: QaState) -> Tuple[QaState, str]:
        try:
            qaApp = self.build_graph()
            if qaApp is None:
                state["answer"] = "Error: Graph compilation failed"
                return state, "0 min 0.00 sec"

            start = time.time()
            finalState = qaApp.invoke(state)
            end = time.time()
            return finalState, self.format_duration(end - start)

        except Exception as e:
            state["answer"] = f"Error: {e}"
            return state, "0 min 0.00 sec"
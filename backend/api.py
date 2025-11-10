from flask import Flask, jsonify, request
from qa import Workflow
from typing import TypedDict, List

app = Flask(__name__)

class PerformanceState(TypedDict):
    question: str
    answer: str
    time: str

performance: List[PerformanceState] = []

@app.route('/reply', methods=['POST'])
def reply():
    try:
        data = request.get_json(force=True)
        query = data.get("query", "").strip()
        chatHistory = data.get("chatHistory", [])
        print(query)
        if not isinstance(chatHistory, list):
            chatHistory = []

        if not query:
            return jsonify({"error": "Query is empty"}), 400


        workflow = Workflow(query)
        state = workflow.qa_state()
        final_state, time_to_reply = workflow.qa_reply(state)

        performance.append({
            "question": final_state.get("question", ""),
            "answer": final_state.get("answer", "Réponse indisponible."),
            "time": time_to_reply
        })

        chatHistory.append({"role": "user", "content": query})
        chatHistory.append({
            "role": "assistant",
            "content": final_state.get("answer", "Réponse indisponible. Notre équipe travaille activement à résoudre ce problème.")
        })

        return jsonify({"chatHistory": chatHistory}), 200

    except Exception as e:
        print(f" Server error: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/performance', methods=['GET'])
def getPerf():
    return jsonify(performance), 200

if __name__ == "__main__":
    app.url_map.strict_slashes = False
    app.run(host="0.0.0.0", port=5000, debug=True)
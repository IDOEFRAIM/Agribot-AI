import json
from deepeval import evaluate
from deepeval.metrics import GEval, FaithfulnessMetric, ContextualRelevancyMetric
from deepeval.test_case import LLMTestCaseParams
from evaluation.evalute_rag import create_deep_eval_test_cases

# Set llm model for evaluation of the question and answers 
LLM_MODEL = "gpt-4o"

# Define evaluation metrics
correctness_metric = GEval(
    name="Correctness",
    model=LLM_MODEL,
    evaluation_params=[
        LLMTestCaseParams.EXPECTED_OUTPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT
    ],
    evaluation_steps=[
        "Determine whether the actual output is factually correct based on the expected output."
    ],
)

faithfulness_metric = FaithfulnessMetric(
    threshold=0.7,
    model=LLM_MODEL,
    include_reason=False
)

relevance_metric = ContextualRelevancyMetric(
    threshold=1,
    model=LLM_MODEL,
    include_reason=True
)

def evaluate_rag(query_engine, num_questions: int = 5) -> None:
    """
    Evaluate the RAG system using predefined metrics.

    Args:
        query_engine: Query engine to ask questions and get answers along with retrieved context.
        num_questions (int): Number of questions to evaluate (default: 5).
    """
    
    
    # Load questions and answers from JSON file
    q_a_file_name = "data/q_a.json"
    with open(q_a_file_name, "r", encoding="utf-8") as json_file:
        q_a = json.load(json_file)

    questions = [qa["question"] for qa in q_a][:num_questions]
    ground_truth_answers = [qa["answer"] for qa in q_a][:num_questions]
    generated_answers = []
    retrieved_documents = []

    # Generate answers and retrieve documents for each question
    for question in questions:
        response = query_engine.query(question)
        context = [doc.text for doc in response.source_nodes]
        retrieved_documents.append(context)
        generated_answers.append(response.response)

  # Create test cases and evaluate
    test_cases = create_deep_eval_test_cases(questions, ground_truth_answers, generated_answers, retrieved_documents)
    evaluate(
        test_cases=test_cases,
        metrics=[correctness_metric, faithfulness_metric, relevance_metric]
    )

query_engine  = vector_store_index.as_query_engine(similarity_top_k=2)
evaluate_rag(query_engine, num_questions=1)
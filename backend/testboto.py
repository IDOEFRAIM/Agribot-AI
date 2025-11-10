import boto3
import json

# Initialise le client SageMaker Runtime
runtime = boto3.client("sagemaker-runtime")

# Nom de ton endpoint
endpoint_name = "jumpstart-dft-hf-llm-mistral-7b-ins-20251110-051421"

# Requête simple
payload = {"inputs": "Bonjour, peux-tu me dire quelque chose sur l'agriculture durable ?"}

# Appel à SageMaker
response = runtime.invoke_endpoint(
    EndpointName=endpoint_name,
    ContentType="application/json",
    Body=json.dumps(payload)
)

# Affichage de la réponse
result = response["Body"].read().decode()
print(json.loads(result)[0]["generated_text"])
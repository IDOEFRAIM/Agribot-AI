# Utilise une image Python légère
FROM python:3.10-slim

# Variables d’environnement utiles
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Crée un dossier de travail
WORKDIR /app

# Copie les fichiers du frontend
COPY . /app

# Installe les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Expose le port utilisé par Gradio
EXPOSE 8080

# Lance l'application Gradio
CMD ["python", "main.py"]
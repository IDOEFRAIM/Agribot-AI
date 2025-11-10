# Image de base avec support CUDA (GPU)
FROM nvidia/cuda:12.2.0-base-ubuntu22.04

# Variables d’environnement utiles
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Dossier de travail dans le conteneur
WORKDIR /app

# Copie des fichiers backend
COPY . /app

# Installation de Python, pip et dépendances système
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Mise à jour de pip et installation des dépendances Python
RUN pip3 install --upgrade pip setuptools wheel \
    && pip3 install --no-cache-dir -r requirements.txt

# Expose le port Flask
EXPOSE 5000

# Lancement de l’API avec Gunicorn (production-ready)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "api:app"]
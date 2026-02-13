# 🌾 Agribot-AI - Assistant Agricole Intelligent

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://docker.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://postgresql.org)

**Plateforme d'intelligence agricole pour assister les agriculteurs via la voix et l'IA.**

[Documentation Architecture](docs/ARCHITECTURE.md) • [Guide de Déploiement](docs/DEPLOYMENT.md) • [Contribuer](CONTRIBUTING.md)

</div>

---

## 🎯 Vue d'Ensemble

Agribot-AI est un système modulaire conçu pour aider les agriculteurs dans leur quotidien :
- 🌦️ **Météo & Risques** : Alertes localisées et prévisions.
- 🌱 **Diagnostic Plantes** : Identification de maladies par photo/description.
- 💰 **Marché** : Suivi des prix et opportunités de vente.
- 🚜 **Formation** : Conseils techniques et bonnes pratiques.
- 🎙️ **Interface Vocale** : Accessible via la voix (STT/TTS Azure & OpenAI).

---

## 📚 Documentation Officielle

La documentation a été consolidée pour plus de clarté :

### 1. [Architecture Technique](docs/ARCHITECTURE.md) 🏗️
- **Vue d'ensemble 3-Tiers** (Ingestion, Orchestration, Action).
- **Agents Proactifs** : Comment les agents (Market, Soil, Plant) interagissent directement avec la base de données.
- **Flux de Données** : Explication des flux synchrones et asynchrones.
- **Stack Technique** : Détails sur FastAPI, LangGraph, Celery, et PostgreSQL.

### 2. [Guide de Déploiement](docs/DEPLOYMENT.md) 🚀
- **Installation Docker** : Déployer la stack complète en une commande.
- **Infrastructure Cloud** : Guide pour DigitalOcean (ou tout VPS).
- **Configuration** : Variables d'environnement et secrets.
- **Maintenance** : Backups et mises à jour.

---

## ⚡ Démarrage Rapide (Local)

1. **Cloner le projet**
   ```bash
   git clone https://github.com/votre-org/Agribot-AI.git
   cd Agribot-AI
   ```

2. **Configurer l'environnement**
   ```bash
   cp .env.example .env
   # Éditer .env avec vos clés API (OpenAI, Azure Speech, etc.)
   ```

3. **Lancer avec Docker Compose**
   ```bash
   docker compose up -d --build
   ```

4. **Accéder à l'API**
   - API Docs : `http://localhost:8000/docs`
   - Monitoring Flower : `http://localhost:5555`

---

## 🛠️ Stack Technique Simplifiée

- **Backend** : Python 3.12, FastAPI.
- **IA & Agents** : LangChain, LangGraph.
- **Base de Données** : PostgreSQL 16 (avec pgvector pour le RAG).
- **Cache & Message Broker** : Redis.
- **Tâches de fond** : Celery.
- **Voix** : Azure Speech Services.

---

## 👥 Équipe & Contribution

Ce projet est open-source. Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour participer.








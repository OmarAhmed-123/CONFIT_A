<div align="center">

# CONFIT (كونفيت)
### AI-Powered Luxury Fashion Technology Platform

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141.1-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.3.1-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6.3-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-3.4.14-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![Tests](https://img.shields.io/badge/Pytest-25%20Passed-4E9A06?style=for-the-badge&logo=pytest&logoColor=white)](https://docs.pytest.org/)

<p align="center">
  <em>"Where Style Meets Your Character in Every Moment"</em>
</p>

</div>

---

## 🌟 Overview

**CONFIT** is a production-grade luxury fashion technology platform bridging the physical-digital imagination gap. Built with strict **MVVM (Frontend)** and **MVC (Backend)** architecture, CONFIT delivers AI-grounded conversational styling, real-time multi-brand outfit composition with deterministic slot integrity, photorealistic dynamic virtual try-on with strict identity preservation, and an enterprise B2B partner analytics suite.

---

## 🏛️ Core Feature Groups (G1–G6)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 CONFIT ARCHITECTURE                                    │
├──────────────────────────┬───────────────────────────┬─────────────────────────────────┤
│ G1: Identity & Privacy   │ G2: Discovery & Styling   │ G3: Virtual Visualization & Fit │
│ • Multi-factor TOTP Auth │ • Grounded AI Stylist     │ • Diffusion Multi-Garment VTON  │
│ • Fernet-256 AES Biometrics • Slot Ontology Engine  │ • Motion Try-On Animation       │
│ • Late-Auth Purchase Gate│ • Live Running Budget HUD │ • Dynamic Drag & Drop Studio    │
├──────────────────────────┼───────────────────────────┼─────────────────────────────────┤
│ G4: Smart Wardrobe       │ G5: Commerce & BNPL       │ G6: Brand & Admin Governance    │
│ • AI Digital Closet      │ • Tabby & Tamara 0% BNPL  │ • Real-time BOPIS Inventory     │
│ • Wardrobe Gap Analysis  │ • BOPIS Boutique Pickup   │ • 71.4% Return Reduction Telemetry│
│ • Duplicate Purchase Guard│ • Multi-Market Egypt & GCC│ • Sponsored Placements & Heatmap│
└──────────────────────────┴───────────────────────────┴─────────────────────────────────┘
```

---

## 🚀 Quick Start & Development

### 1. Prerequisites
* **Python** $\ge$ 3.11
* **Node.js** $\ge$ 18.0 & **npm** $\ge$ 9.0

### 2. Backend Setup
```bash
# Clone the repository
git clone https://github.com/OmarAhmed-123/CONFIT_A.git
cd CONFIT_A

# Install Python dependencies
pip install -r backend/requirements.txt

# Seed the multi-brand catalog (Massimo Dutti, COS, Reiss, Arket)
PYTHONPATH=. python3 backend/app/seed_data.py

# Run the FastAPI API server
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
* Interactive API Documentation (OpenAPI): `http://localhost:8000/docs`
* Health Check: `http://localhost:8000/api/v1/health`

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
* Web Application SPA: `http://localhost:5173`

---

## 🧪 Test Suite Execution

```bash
# Run all 25 automated backend integration test suites
PYTHONPATH=. pytest backend/tests -v
```

---

## 🔒 Security & Privacy Standards

1. **Zero Permanent Photo Retention by Default:** User webcam frames and uploaded images are processed strictly in-session and scheduled for 24-hour expiration.
2. **Encrypted Biometrics:** Customer body dimensions are encrypted at rest with **Fernet-256 AES**.
3. **GDPR Article 17 Purge:** Full endpoint support for account deletion and instant biometric purge (`DELETE /api/v1/try-on/sessions/{id}/purge`).
4. **Late-Auth Purchase Gate:** Unregistered shoppers can freely browse, style, and visualize looks; authentication is only required at purchase checkout.

---

## 📄 License
CONFIT Enterprise Proprietary. All rights reserved.

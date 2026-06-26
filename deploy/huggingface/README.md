---
title: Manufacturing Insight AI
emoji: 🏭
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Manufacturing Insight AI API

FastAPI backend for the Manufacturing Insight AI portfolio project.

- `/health`: health check
- `/api/summary`: manufacturing dataset summary
- `/api/query`: deterministic manufacturing analysis with optional Gemini refinement
- `/api/reports`: demo report storage
- `/api/reports/{id}/export/docx`: DOCX export

The app is designed to run without an LLM key. If `GEMINI_API_KEY` is empty, it uses deterministic rule-based analysis.
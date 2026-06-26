# Manufacturing Insight AI

Manufacturing Insight AI is a portfolio-oriented web application for querying manufacturing equipment data, generating explainable AI-assisted analysis, visualizing best-fit charts, and building editable reports.

## What It Does

- Ask natural-language questions about manufacturing equipment data.
- Compute numeric results deterministically in the backend.
- Use Gemini only for explanation refinement and follow-up question suggestions.
- Render recommended charts and allow users to switch chart types.
- Add answers, KPI cards, charts, and tables to a report.
- Reorder report blocks with drag and drop.
- Save reports in SQLite and reopen them later.
- Export saved reports as DOCX.

## Layout

```text
backend/      FastAPI API, CSV analysis, Gemini adapter, report storage/export
frontend/     Next.js UI, charts, report builder
data/         Manufacturing CSV dataset
docs/         Project domain documents
.Agent/       Agent rules and work history
```

## Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`GEMINI_API_KEY` is optional. If it is empty, the app runs in deterministic demo mode without external LLM calls.

## Frontend Setup

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Open `http://localhost:3000`.

## No-Billing LLM Policy

To avoid unexpected charges:

- Use Gemini Free Tier only.
- Do not connect Google Cloud Billing or upgrade to a paid tier.
- Store the API key only in the backend `.env` file.
- The backend checks daily user/global usage limits before calling Gemini.
- If usage is exhausted, LLM calls are skipped and the user sees a free-usage exhaustion message.
- Data analysis, charts, and report editing continue without LLM calls.

## MVP Notes

- DOCX export is implemented as a block-based document.
- PDF export and HWPX export are future enhancements.
- Charts are stored as chart specs in reports. Chart image embedding can be expanded later through frontend chart capture.


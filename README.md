# Document Auditor

An automated fact-checking pipeline that accepts any PDF, extracts measurable claims, and cross-references each against live public data sources — returning structured verdicts via an interactive dashboard.

Built for analysts and researchers who need a fast, systematic way to verify claims in industry reports, white papers, annual reports, and consultant publications.

---

## How it works

The pipeline runs in four stages:

**1. Text extraction**
Ingests any PDF. Tries direct text extraction first; falls back to OCR automatically for image-based or browser-printed documents.

**2. Document type detection**
Identifies the document type (consulting report, CEO interview, government white paper, SEC filing, academic paper) and tailors the extraction prompt accordingly.

**3. Claim extraction**
Uses Claude API to extract 10-15 specific, measurable, falsifiable claims — filtering out opinions, recommendations, and anecdotes without numbers.

**4. Evidence routing + verdict**
For each claim, a routing call generates a targeted search query. Live web search retrieves evidence. Claude returns a structured verdict:
- ✅ Supported
- ⚠️ Partially Supported  
- ❌ Contradicted
- ❓ Unverifiable

Each verdict includes confidence level, reasoning, source quality, and a flag for claims that are technically accurate but misleading in context.

---

## Setup

```bash
git clone https://github.com/yourusername/document-auditor
cd document-auditor
pip install -r requirements.txt
```

Add your Anthropic API key to a `.env` file:

```
ANTHROPIC_API_KEY=your_key_here
```

---

## Usage

```bash
streamlit run app.py
```

1. Enter a client or project name in the sidebar
2. Upload any PDF
3. Click **Run Audit**
4. Results appear in the dashboard as each claim is verified
5. Download `verdicts.json` from the dashboard when complete

---

## Stack

| Layer | Tool |
|---|---|
| Document type detection | Claude API (Haiku) |
| Claim extraction | Claude API (Haiku) |
| Evidence retrieval | Anthropic web search tool |
| Verdict classification | Claude API (Sonnet) |
| PDF parsing | pdfplumber + pytesseract (OCR fallback) |
| Dashboard | Streamlit |

---

## Cost

Approximately 5–20 cents per document depending on length, using Claude Haiku for extraction and routing, Sonnet only for verdict classification.

---

## Project structure

```
document-auditor/
├── app.py              # Full pipeline + Streamlit dashboard
├── .env                # API key (not committed)
├── .env.example        # Template for setup
├── requirements.txt
└── README.md
```

---



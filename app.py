import streamlit as st
import json
import os
import re
import time
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

st.set_page_config(
    page_title="Document Auditor — Exoreach",
    page_icon="🔍",
    layout="wide"
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Syne', sans-serif;
    background-color: #0a0a0a;
    color: #e8e8e8;
}
.stApp { background-color: #0a0a0a; }

.header-block {
    border-left: 4px solid #e8c84a;
    padding: 0.4rem 0 0.4rem 1.2rem;
    margin-bottom: 0.5rem;
}
.header-block h1 { font-size: 2rem; font-weight: 800; color: #f5f5f5; margin: 0; letter-spacing: -0.03em; }
.header-block p  { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #888; margin: 0.2rem 0 0 0; letter-spacing: 0.08em; text-transform: uppercase; }

.stat-box { background: #141414; border: 1px solid #2a2a2a; border-radius: 6px; padding: 1rem 1.2rem; text-align: center; }
.stat-box .num   { font-size: 2.4rem; font-weight: 800; line-height: 1; }
.stat-box .label { font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #666; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 0.3rem; }

.claim-card             { background: #111; border: 1px solid #222; border-radius: 8px; padding: 1.2rem 1.4rem; margin-bottom: 0.8rem; }
.claim-card.contradicted  { border-left: 3px solid #e05555; }
.claim-card.supported     { border-left: 3px solid #4caf7d; }
.claim-card.unverifiable  { border-left: 3px solid #888; }
.claim-card.partially     { border-left: 3px solid #e8a83a; }

.verdict-pill { display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; font-weight: 500; padding: 0.18rem 0.55rem; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.08em; margin-right: 0.4rem; }
.pill-contradicted { background: #2a1212; color: #e05555; border: 1px solid #e05555; }
.pill-supported    { background: #0f2018; color: #4caf7d; border: 1px solid #4caf7d; }
.pill-unverifiable { background: #1a1a1a; color: #888;    border: 1px solid #555; }
.pill-partially    { background: #261c08; color: #e8a83a; border: 1px solid #e8a83a; }
.pill-flag         { background: #261800; color: #e8c84a; border: 1px solid #e8c84a; }

.claim-text    { font-size: 0.95rem; font-weight: 600; color: #ddd; margin: 0.6rem 0 0.4rem 0; line-height: 1.4; }
.reasoning     { font-size: 0.82rem; color: #888; line-height: 1.6; }
.meta-row      { font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #555; margin-top: 0.7rem; padding-top: 0.7rem; border-top: 1px solid #1e1e1e; }
.divider       { border: none; border-top: 1px solid #1e1e1e; margin: 1.5rem 0; }
.doc-type-tag  { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #e8c84a; background: #1a1500; border: 1px solid #3a2e00; border-radius: 3px; padding: 0.2rem 0.5rem; display: inline-block; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)


# ── Pipeline functions ────────────────────────────────────────────────────────

def extract_text_from_pdf(uploaded_file, max_pages=25):
    """Extract text from uploaded PDF, falling back to OCR if needed."""
    import pdfplumber, tempfile

    # Save uploaded file to a temp path so pdfplumber can open it
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    text = ""
    with pdfplumber.open(tmp_path) as pdf:
        for page in pdf.pages[:max_pages]:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"

    if len(text.strip()) < 500:
        text = extract_text_via_ocr(tmp_path, max_pages)

    os.unlink(tmp_path)
    return text

def extract_text_via_ocr(pdf_path, max_pages=25):
    """OCR fallback for image-based PDFs."""
    from pdf2image import convert_from_path
    import pytesseract

    pages = convert_from_path(pdf_path, first_page=5, last_page=5 + max_pages - 1, dpi=150)
    text = ""
    for i, page in enumerate(pages):
        text += f"\n--- PAGE {5+i} ---\n{pytesseract.image_to_string(page)}"
    return text

def detect_document_type(text_sample: str) -> str:
    """Ask Claude what kind of document this is so we can tailor extraction."""
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=100,
        temperature=0,
        system="Return only a short document type label. Examples: 'Consulting report', 'CEO interview', 'Government white paper', 'Annual report / SEC filing', 'Academic paper', 'Press release', 'Industry analysis'. No explanation.",
        messages=[{"role": "user", "content": f"What type of document is this?\n\n{text_sample[:1500]}"}]
    )
    return message.content[0].text.strip()

def extract_claims(text: str, doc_type: str, client_name: str) -> list:
    """Extract 10-15 measurable claims from any document type."""
    prompt = f"""
    You are auditing a document on behalf of {client_name}.
    Document type: {doc_type}

    Extract 10-15 specific, measurable, falsifiable claims from the text below.

    A valid claim MUST:
    1. Contain a specific metric, statistic, percentage, or dollar figure
    2. Have an identifiable scope (company, industry, geography, or demographic)
    3. Be checkable against public data sources

    Exclude: opinions, recommendations, hypotheticals, anecdotes without numbers, and vague qualitative statements.

    Return ONLY a raw JSON list, no markdown, no explanation:
    [
        {{
            "claim": "The specific claim with its metric",
            "type": "Economic / Industry / Technology / Social / Financial",
            "domain": "e.g. AI Adoption / Energy / Labour Markets / Banking",
            "implied_timeframe": "e.g. 2024-2026 or by 2030 or 2025",
            "measurable": true
        }}
    ]

    Document text:
    {text}
    """

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2500,
        temperature=0,
        system="You are a clinical data auditor. Extract only hard, verifiable facts. Return only raw JSON.",
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text
    cleaned = re.sub(r"```json\s*|\s*```", "", raw).strip()
    return json.loads(cleaned)

def get_search_strategy(claim: dict) -> dict:
    """Route each claim to the best search query and source type."""
    prompt = f"""
    Claim: {claim['claim']}
    Domain: {claim['domain']}
    Timeframe: {claim['implied_timeframe']}

    Return ONLY raw JSON:
    {{
        "search_query": "targeted search query to find evidence",
        "source_priority": "e.g. SEC filing / government database / press release",
        "what_to_look_for": "the specific number or fact that would confirm or deny this"
    }}
    """
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        temperature=0,
        system="You are a research routing assistant. Return only raw JSON.",
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text
    cleaned = re.sub(r"```json\s*|\s*```", "", raw).strip()
    return json.loads(cleaned)

def fetch_evidence(search_query: str) -> str:
    """Fetch live evidence via web search."""
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system="You are a research assistant. Search and summarise key facts. Be specific about numbers, dates, and sources.",
        messages=[{"role": "user", "content": f"Search for: {search_query}. Return a factual summary focusing on specific numbers, dates, and sources."}]
    )
    text_blocks = [block.text for block in message.content if block.type == "text"]
    return " ".join(text_blocks) if text_blocks else "No evidence found."

def get_verdict(claim: dict, evidence: str, what_to_look_for: str, doc_type: str) -> dict:
    """Compare claim against evidence and return structured verdict."""
    prompt = f"""
    You are fact-checking a claim from a {doc_type}.

    CLAIM: {claim['claim']}
    WHAT TO LOOK FOR: {what_to_look_for}
    EVIDENCE: {evidence}

    Return ONLY raw JSON:
    {{
        "verdict": "Supported / Partially Supported / Contradicted / Unverifiable",
        "confidence": "High / Medium / Low",
        "reasoning": "1-2 sentences explaining the verdict",
        "source_quality": "Strong / Adequate / Weak",
        "flag": true or false
    }}

    Set flag to true if the claim is technically accurate but misleading, lacks important context, or uses selective framing.
    """
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        temperature=0,
        system="You are a rigorous fact-checker. Be skeptical. Return only raw JSON.",
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text
    cleaned = re.sub(r"```json\s*|\s*```", "", raw).strip()
    return json.loads(cleaned)


# ── UI ────────────────────────────────────────────────────────────────────────

# Header
st.markdown("""
<div class="header-block">
    <h1>Document Auditor</h1>
    <p>Exoreach · Automated claim verification</p>
</div>
""", unsafe_allow_html=True)

# Sidebar — controls
with st.sidebar:
    st.markdown("### Run a new audit")
    client_name = st.text_input("Client / project name", placeholder="e.g. Acme Corp Q2 Review")
    uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])
    run_button = st.button("Run Audit", type="primary", disabled=not (uploaded_file and client_name))

    st.markdown("---")
    st.markdown("### Load previous results")
    results_path = st.text_input("Path to verdicts.json", placeholder="output/verdicts.json")
    load_button = st.button("Load results")

# ── Run pipeline ──────────────────────────────────────────────────────────────
if run_button and uploaded_file and client_name:

    os.makedirs("output", exist_ok=True)

    with st.status("Running audit pipeline...", expanded=True) as status:

        st.write("📄 Extracting text from PDF...")
        text = extract_text_from_pdf(uploaded_file)
        if not text.strip():
            st.error("Could not extract text from this PDF.")
            st.stop()
        st.write(f"✓ Extracted {len(text):,} characters")

        st.write("🔍 Detecting document type...")
        doc_type = detect_document_type(text)
        st.write(f"✓ Document type: {doc_type}")

        st.write("📋 Extracting measurable claims...")
        try:
            claims = extract_claims(text, doc_type, client_name)
            st.write(f"✓ Found {len(claims)} claims to verify")
        except Exception as e:
            st.error(f"Claim extraction failed: {e}")
            st.stop()

        with open("output/claims.json", "w") as f:
            json.dump(claims, f, indent=4)

        st.write("🌐 Verifying claims against live data...")
        results = []
        progress = st.progress(0)

        for i, claim in enumerate(claims):
            try:
                strategy = get_search_strategy(claim)
                time.sleep(1)
                evidence = fetch_evidence(strategy['search_query'])
                time.sleep(1)
                verdict = get_verdict(claim, evidence, strategy['what_to_look_for'], doc_type)

                results.append({
                    "claim": claim['claim'],
                    "domain": claim['domain'],
                    "timeframe": claim['implied_timeframe'],
                    "search_query": strategy['search_query'],
                    "source_priority": strategy['source_priority'],
                    "evidence_summary": evidence[:300],
                    **verdict
                })
            except Exception as e:
                results.append({
                    "claim": claim['claim'],
                    "domain": claim.get('domain', '—'),
                    "verdict": "Error",
                    "confidence": "—",
                    "reasoning": str(e),
                    "source_quality": "—",
                    "flag": False
                })

            progress.progress((i + 1) / len(claims))
            time.sleep(2)

        with open("output/verdicts.json", "w") as f:
            json.dump(results, f, indent=4)

        # Store in session state so dashboard renders immediately
        st.session_state['results'] = results
        st.session_state['doc_type'] = doc_type
        st.session_state['client_name'] = client_name

        status.update(label="Audit complete", state="complete")

# ── Load previous results ─────────────────────────────────────────────────────
if load_button and results_path:
    try:
        with open(results_path) as f:
            st.session_state['results'] = json.load(f)
        st.session_state['doc_type'] = "Loaded from file"
        st.session_state['client_name'] = "—"
    except Exception as e:
        st.error(f"Could not load file: {e}")

# ── Dashboard ─────────────────────────────────────────────────────────────────
if 'results' in st.session_state:
    data     = st.session_state['results']
    doc_type = st.session_state.get('doc_type', '—')
    cname    = st.session_state.get('client_name', '—')

    st.markdown(f'<div class="doc-type-tag">Document type: {doc_type} &nbsp;·&nbsp; Client: {cname}</div>', unsafe_allow_html=True)

    # Stats
    verdicts     = [r.get('verdict', 'Error') for r in data]
    supported    = verdicts.count('Supported')
    contradicted = verdicts.count('Contradicted')
    unverifiable = verdicts.count('Unverifiable')
    partial      = verdicts.count('Partially Supported')
    flagged      = sum(1 for r in data if r.get('flag'))

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.markdown(f'<div class="stat-box"><div class="num" style="color:#f5f5f5">{len(data)}</div><div class="label">Claims Checked</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="stat-box"><div class="num" style="color:#4caf7d">{supported}</div><div class="label">Supported</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="stat-box"><div class="num" style="color:#e05555">{contradicted}</div><div class="label">Contradicted</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="stat-box"><div class="num" style="color:#888">{unverifiable}</div><div class="label">Unverifiable</div></div>', unsafe_allow_html=True)
    with c5: st.markdown(f'<div class="stat-box"><div class="num" style="color:#e8c84a">{flagged}</div><div class="label">Flagged</div></div>', unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Filters
    col1, col2 = st.columns([2, 1])
    with col1:
        filter_verdict = st.multiselect(
            "Filter by verdict",
            options=["Supported", "Contradicted", "Unverifiable", "Partially Supported"],
            default=["Supported", "Contradicted", "Unverifiable", "Partially Supported"]
        )
    with col2:
        flagged_only = st.toggle("Flagged only", value=False)

    filtered = [r for r in data if r.get('verdict') in filter_verdict and (not flagged_only or r.get('flag'))]
    st.markdown(f'<p style="font-family:JetBrains Mono,monospace;font-size:0.7rem;color:#555;margin-bottom:1rem;">SHOWING {len(filtered)} OF {len(data)} CLAIMS</p>', unsafe_allow_html=True)

    CARD_CLASS = {"Contradicted": "contradicted", "Supported": "supported", "Unverifiable": "unverifiable", "Partially Supported": "partially"}
    PILL_CLASS = {"Contradicted": "pill-contradicted", "Supported": "pill-supported", "Unverifiable": "pill-unverifiable", "Partially Supported": "pill-partially"}

    for r in filtered:
        v        = r.get('verdict', 'Unknown')
        flag     = r.get('flag', False)
        card_cls = CARD_CLASS.get(v, 'unverifiable')
        pill_cls = PILL_CLASS.get(v, 'pill-unverifiable')
        flag_html = '<span class="verdict-pill pill-flag">⚑ Flagged</span>' if flag else ""

        st.markdown(f"""
        <div class="claim-card {card_cls}">
            <span class="verdict-pill {pill_cls}">{v}</span>{flag_html}
            <span style="font-family:JetBrains Mono,monospace;font-size:0.65rem;color:#555;"> · {r.get('confidence','—')} confidence</span>
            <div class="claim-text">"{r.get('claim','')}"</div>
            <div class="reasoning">{r.get('reasoning','')}</div>
            <div class="meta-row">
                Domain: {r.get('domain','—')} &nbsp;·&nbsp;
                Timeframe: {r.get('timeframe','—')} &nbsp;·&nbsp;
                Source quality: {r.get('source_quality','—')}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Download button
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.download_button(
        label="Download verdicts.json",
        data=json.dumps(data, indent=4),
        file_name="verdicts.json",
        mime="application/json"
    )

    st.markdown('<p style="font-family:JetBrains Mono,monospace;font-size:0.65rem;color:#333;text-align:center;margin-top:1rem;"> · Claude API (Haiku + Sonnet) · Web search</p>', unsafe_allow_html=True)

else:
    st.markdown("""
    <div style="text-align:center;padding:4rem 2rem;color:#444;">
        <p style="font-size:2rem;">🔍</p>
        <p style="font-family:JetBrains Mono,monospace;font-size:0.8rem;letter-spacing:0.1em;text-transform:uppercase;">Upload a PDF and enter a name to begin</p>
    </div>
    """, unsafe_allow_html=True)

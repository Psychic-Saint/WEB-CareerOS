"""
ai/scorer.py  — CV-vs-job-description fit scorer using Claude or Gemini.

Usage:
    from ai.scorer import score_job, load_cv_text
    cv_text = load_cv_text("/path/to/Eddie_Bila_CV.pdf")
    score, reasoning, gaps = score_job(job, cv_text, engine="claude")
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger("job_pipeline.scorer")

# ---------------------------------------------------------------------------
# CV text extraction
# ---------------------------------------------------------------------------

def load_cv_text(cv_path: str) -> str:
    """
    Extract plain text from a PDF or DOCX CV.
    Returns empty string if the file can't be read (caller handles gracefully).
    """
    path = Path(cv_path)
    if not path.exists():
        logger.warning("CV file not found: %s", cv_path)
        return ""

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                return "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                ).strip()
        except ImportError:
            logger.warning("pdfplumber not installed — falling back to pypdf")
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join(p.extract_text() or "" for p in reader.pages).strip()
        except Exception as e:
            logger.error("PDF read failed: %s", e)
            return ""

    if suffix in {".docx", ".doc"}:
        try:
            import docx
            doc = docx.Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs).strip()
        except Exception as e:
            logger.error("DOCX read failed: %s", e)
            return ""

    # Plain text fallback
    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Scoring prompt
# ---------------------------------------------------------------------------

_SCORE_PROMPT = """\
You are an expert recruitment consultant helping Eddie Bila assess job fit.

## Eddie's CV
{cv_text}

## Job to Assess
Title   : {title}
Company : {company}
Location: {location}

Description:
{description}

---

Evaluate how well Eddie's background fits this role. Be honest — flag real gaps.

Return ONLY valid JSON in exactly this structure (no markdown fences, no extra keys):
{{
  "score": <integer 0-100>,
  "reasoning": "<2-3 sentences explaining the score>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "gaps": ["<gap 1>", "<gap 2>"]
}}

Scoring guide:
  90-100  Excellent match — strong evidence of all key requirements
  70-89   Good match — most requirements met, minor gaps
  55-69   Moderate — transferable skills present but some clear gaps
  40-54   Weak — significant gaps, worth flagging but not skipping entirely
  0-39    Poor — fundamental mismatch
"""


def _parse_score_response(text: str) -> tuple[int, str, list[str]]:
    """Parse the JSON response. Falls back gracefully on malformed output."""
    import json
    # Strip any accidental markdown fences
    text = re.sub(r"```[a-z]*", "", text).strip()
    try:
        data = json.loads(text)
        score     = int(data.get("score", 0))
        reasoning = str(data.get("reasoning", ""))
        gaps      = [str(g) for g in data.get("gaps", [])]
        return score, reasoning, gaps
    except Exception as e:
        logger.warning("Score parse failed: %s | raw: %s", e, text[:200])
        # Last-ditch: try to extract a number
        nums = re.findall(r'"score"\s*:\s*(\d+)', text)
        return (int(nums[0]) if nums else 0), "Parse error — check log", []


# ---------------------------------------------------------------------------
# Engine callers
# ---------------------------------------------------------------------------

def _score_with_claude(prompt: str, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",   # fast + cheap for scoring
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _score_with_gemini(prompt: str, api_key: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    return response.text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_job(
    job: dict,
    cv_text: str,
    engine: str = "claude",
    anthropic_key: str = "",
    gemini_key: str = "",
) -> tuple[int, str, list[str]]:
    """
    Score a job against the CV text.
    Returns (score: int, reasoning: str, gaps: list[str]).
    Returns (0, "error", []) on failure — caller handles gracefully.
    """
    if not cv_text:
        logger.warning("No CV text — scoring skipped")
        return 0, "CV text not available", []

    description = job.get("description", "")
    if len(description) < 50:
        logger.info("Job description too short — using basic scoring")
        description = f"Job title: {job.get('title', '')}. No full description available."

    # Truncate very long CVs/JDs to stay within token limits
    cv_snippet  = cv_text[:6000]
    jd_snippet  = description[:3000]

    prompt = _SCORE_PROMPT.format(
        cv_text     = cv_snippet,
        title       = job.get("title", ""),
        company     = job.get("company", ""),
        location    = job.get("location", ""),
        description = jd_snippet,
    )

    try:
        if engine == "gemini" and gemini_key:
            raw = _score_with_gemini(prompt, gemini_key)
        elif anthropic_key:
            raw = _score_with_claude(prompt, anthropic_key)
        elif gemini_key:
            raw = _score_with_gemini(prompt, gemini_key)
        else:
            logger.warning("No API key configured — scoring skipped")
            return 0, "No AI API key configured", []

        return _parse_score_response(raw)

    except Exception as exc:
        logger.error("Scoring error: %s", exc)
        return 0, f"Scoring error: {exc}", []


# ---------------------------------------------------------------------------
# Cover letter generator
# ---------------------------------------------------------------------------

_COVER_LETTER_PROMPT = """\
Write a concise, professional cover letter for Eddie Bila applying to the role below.
Use his CV as context. Keep it to 3 short paragraphs max (under 200 words total).
Do NOT use filler phrases like "I am writing to express my interest".
Be direct and specific — mention the company name.

## Eddie's CV (excerpt)
{cv_text}

## Role
Title   : {title}
Company : {company}

Job Description (excerpt):
{description}

Return ONLY the cover letter text — no subject line, no date, no address.
"""


def generate_cover_letter(
    job: dict,
    cv_text: str,
    engine: str = "claude",
    anthropic_key: str = "",
    gemini_key: str = "",
) -> str:
    """Generate a brief tailored cover letter. Returns empty string on failure."""
    if not cv_text:
        return ""
    prompt = _COVER_LETTER_PROMPT.format(
        cv_text     = cv_text[:4000],
        title       = job.get("title", ""),
        company     = job.get("company", ""),
        description = job.get("description", "")[:2000],
    )
    try:
        if engine == "gemini" and gemini_key:
            return _score_with_gemini(prompt, gemini_key).strip()
        elif anthropic_key:
            return _score_with_claude(prompt, anthropic_key).strip()
        elif gemini_key:
            return _score_with_gemini(prompt, gemini_key).strip()
    except Exception as exc:
        logger.error("Cover letter error: %s", exc)
    return ""

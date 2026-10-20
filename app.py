import json
import time
from typing import List, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel
import pymupdf
import streamlit as st

# Model constants
PRIMARY_MODEL = "gemini-3.5-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"

# System instruction for Gemini (exact verbatim prompt)
SYSTEM_INSTRUCTION = (
    "You are an expert current affairs teacher. You will receive the text of a weekly "
    "current affairs PDF. Read all of it carefully and create a study summary for exam preparation. "
    "Rules: 1) Use very simple English that anyone can understand. Short sentences. No difficult words. "
    "2) Cover every important topic in the PDF. Do not skip important news. "
    "3) For each topic, give a short heading, a category, and 3 to 6 key points. "
    "4) Include important facts: names of people, places, organizations, numbers, schemes, reports, "
    "rankings, awards, and agreements. 5) Collect all important dates and the event linked to each date. "
    "6) Do not invent anything. Use only facts from the PDF. If something is unclear, leave it out. "
    "7) Ignore ads, page numbers, headers, footers and other useless text."
)


# Response Schema definitions
class Topic(BaseModel):
    heading: str
    category: str
    key_points: List[str]


class ImportantDate(BaseModel):
    date: str
    event: str


class WeeklySummarySchema(BaseModel):
    title: str
    week_overview: str
    topics: List[Topic]
    important_dates: List[ImportantDate]


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    """Return the total number of pages in the PDF."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return len(doc)


def extract_text(pdf_bytes: bytes) -> str:
    """Extract all text from the uploaded PDF bytes using PyMuPDF.

    Args:
        pdf_bytes (bytes): Raw bytes of the uploaded PDF document.

    Returns:
        str: Extracted plain text concatenated across all pages.
    """
    text_parts = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            page_text = page.get_text()
            if page_text:
                text_parts.append(page_text)

    return "\n".join(text_parts)


def is_transient_error(err: Exception) -> bool:
    """Check if the error corresponds to a rate limit (429) or temporary server unavailability (503)."""
    code = getattr(err, "code", None)
    if code in (429, 503):
        return True
    err_str = str(err).lower()
    return "429" in err_str or "503" in err_str or "resource_exhausted" in err_str or "unavailable" in err_str


def summarize_text(text: str, api_key: Optional[str] = None) -> Optional[dict]:
    """Send extracted text to Gemini and parse the structured JSON response.

    Handles transient errors (429/503) with a 5-second backoff and fallback to FALLBACK_MODEL.
    """
    if not api_key:
        api_key = st.secrets.get("GEMINI_API_KEY")

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        temperature=0.2,
        response_mime_type="application/json",
        response_schema=WeeklySummarySchema,
        system_instruction=SYSTEM_INSTRUCTION,
    )

    def _call(model_name: str) -> dict:
        response = client.models.generate_content(
            model=model_name,
            contents=text,
            config=config,
        )
        return json.loads(response.text)

    # 1. Attempt with PRIMARY_MODEL
    try:
        return _call(PRIMARY_MODEL)
    except Exception as e_primary:
        if is_transient_error(e_primary):
            # Wait 5 seconds and retry PRIMARY_MODEL once
            time.sleep(5)
            try:
                return _call(PRIMARY_MODEL)
            except Exception as e_retry:
                # Try FALLBACK_MODEL once
                try:
                    return _call(FALLBACK_MODEL)
                except Exception as e_fallback:
                    st.error(f"Service error while generating summary: {e_fallback}")
                    return None
        else:
            # For non-transient errors, try fallback model before failing
            try:
                return _call(FALLBACK_MODEL)
            except Exception as e_final:
                st.error(f"Failed to generate summary: {e_primary if str(e_primary) else e_final}")
                return None


def main():
    # Set page configuration
    st.set_page_config(
        page_title="Weekly Current Affairs Summarizer",
        page_icon="📄",
        layout="centered",
    )

    # API Key check from st.secrets
    if "GEMINI_API_KEY" not in st.secrets or not st.secrets["GEMINI_API_KEY"]:
        st.error(
            "Missing Gemini API Key. Please add `GEMINI_API_KEY = \"your_key\"` to `.streamlit/secrets.toml`."
        )
        st.stop()

    api_key = st.secrets["GEMINI_API_KEY"]

    # Header section
    st.title("Weekly Current Affairs Summarizer")
    st.write("Upload a PDF and get a simple-English summary.")

    # PDF file uploader
    uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])

    if uploaded_file is not None:
        pdf_bytes = uploaded_file.read()

        # Manage session state per unique file
        file_signature = f"{uploaded_file.name}_{len(pdf_bytes)}"
        if st.session_state.get("current_file_signature") != file_signature:
            st.session_state["current_file_signature"] = file_signature
            st.session_state["summary_result"] = None

        # Extract text locally using PyMuPDF
        num_pages = get_pdf_page_count(pdf_bytes)
        text = extract_text(pdf_bytes)
        char_count = len(text)

        # Extraction metrics
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="Total Pages", value=num_pages)
        with col2:
            st.metric(label="Characters Extracted", value=char_count)

        if not text.strip():
            st.warning("This PDF seems to be scanned or image-based, so no text could be read.")
        else:
            with st.expander("Preview extracted text", expanded=False):
                st.text(text[:2000])

            # Generate Summary Button
            if st.button("Generate Summary", type="primary"):
                with st.spinner("Reading and summarizing... this can take up to a minute."):
                    summary = summarize_text(text, api_key=api_key)
                    if summary:
                        st.session_state["summary_result"] = summary

        # Display structured summary if available in session_state
        summary_data = st.session_state.get("summary_result")
        if summary_data:
            st.divider()

            # Title and week overview
            st.header(summary_data.get("title", "Weekly Current Affairs Summary"))
            overview = summary_data.get("week_overview")
            if overview:
                st.info(overview)

            # Topics Section
            st.subheader("Topics")
            topics = summary_data.get("topics", [])
            if topics:
                for topic in topics:
                    heading = topic.get("heading", "").strip()
                    category = topic.get("category", "").strip()
                    category_label = f" *({category})*" if category else ""
                    st.markdown(f"### {heading}{category_label}")
                    for point in topic.get("key_points", []):
                        st.markdown(f"- {point}")
            else:
                st.write("No topics found in summary.")

            # Important Dates Section
            st.subheader("Important Dates")
            important_dates = summary_data.get("important_dates", [])
            if important_dates:
                table_rows = [
                    {"Date": item.get("date", ""), "Event": item.get("event", "")}
                    for item in important_dates
                ]
                st.table(table_rows)
            else:
                st.write("No specific dates recorded.")

            # Raw JSON expander
            with st.expander("Raw JSON", expanded=False):
                st.json(summary_data)


if __name__ == "__main__":
    main()

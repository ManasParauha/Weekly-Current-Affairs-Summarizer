import hashlib
import html
import json
import os
import sys
import time
import traceback
from typing import List, Optional

from fpdf import FPDF
from fpdf.enums import Align, TableCellFillMode, XPos, YPos
from fpdf.fonts import FontFace
from google import genai
from google.genai import types
from pydantic import BaseModel
import pymupdf
import streamlit as st

# Model constants
PRIMARY_MODEL = "gemini-3.5-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MIN_TEXT_CHARS = 200

# System instruction for Gemini
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

# Fonts Directory
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# Category color palette mapping
CATEGORY_COLORS = {
    "national": (234, 88, 12),           # Orange
    "international": (37, 99, 235),      # Blue
    "economy": (22, 163, 74),            # Green
    "science and tech": (126, 34, 206),  # Purple
    "science & tech": (126, 34, 206),
    "science & technology": (126, 34, 206),
    "science and technology": (126, 34, 206),
    "science": (126, 34, 206),
    "environment": (13, 148, 136),       # Teal
    "sports": (220, 38, 38),             # Red
    "awards": (202, 138, 4),             # Gold
    "award": (202, 138, 4),
    "defence": (75, 85, 99),             # Dark grey
    "defense": (75, 85, 99),
    "polity": (146, 64, 14),             # Brown
}
DEFAULT_TAG_COLOR = (107, 114, 128)      # Grey


def get_category_color(cat: str):
    """Return an RGB tuple based on topic category."""
    clean = (cat or "").strip().lower()
    if clean in CATEGORY_COLORS:
        return CATEGORY_COLORS[clean]
    for key, color in CATEGORY_COLORS.items():
        if key in clean or clean in key:
            return color
    return DEFAULT_TAG_COLOR


def get_category_tint(cat: str):
    """Return background and text color CSS values for category pill."""
    r, g, b = get_category_color(cat)
    return f"rgba({r}, {g}, {b}, 0.12)", f"rgb({r}, {g}, {b})"


class PDFReport(FPDF):
    """Custom FPDF subclass with running header / footer."""

    def footer(self):
        self.set_y(-15)
        self.set_draw_color(210, 215, 222)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_y(-12)
        self.set_font("DejaVuSans", "", 8)
        self.set_text_color(130, 140, 150)
        self.cell(0, 8, f"Page {self.page_no()} of {{nb}}", align="C")


def build_pdf(data: dict) -> bytes:
    """Turn the AI summary dict into a clean, publication-ready PDF using fpdf2."""
    pdf = PDFReport(orientation="portrait", unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.alias_nb_pages()

    regular_font_path = os.path.join(FONTS_DIR, "DejaVuSans.ttf")
    bold_font_path = os.path.join(FONTS_DIR, "DejaVuSans-Bold.ttf")

    if not os.path.exists(regular_font_path) or not os.path.exists(bold_font_path):
        raise FileNotFoundError(f"DejaVu fonts not found in {FONTS_DIR}")

    pdf.add_font("DejaVuSans", style="", fname=regular_font_path)
    pdf.add_font("DejaVuSans", style="B", fname=bold_font_path)
    pdf.set_font("DejaVuSans", "", 10)

    # Top of page 1
    pdf.add_page()

    # 1. Full-width dark blue banner (~28 mm tall)
    pdf.set_fill_color(24, 43, 73)
    pdf.rect(0, 0, 210, 28, style="F")

    # Title centered, white, bold, 20 pt (auto-scale if long)
    title_text = (data.get("title") or "Weekly Current Affairs Summary").strip()
    pdf.set_text_color(255, 255, 255)
    title_size = 20
    pdf.set_font("DejaVuSans", "B", title_size)
    while pdf.get_string_width(title_text) > 190 and title_size > 13:
        title_size -= 1
        pdf.set_font("DejaVuSans", "B", title_size)

    pdf.set_xy(10, 5)
    pdf.cell(190, 9, title_text, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Subtitle line inside banner
    pdf.set_font("DejaVuSans", "", 9)
    pdf.set_text_color(205, 222, 245)
    pdf.set_xy(10, 16)
    pdf.cell(190, 6, "Weekly Current Affairs Summary", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Cursor below banner
    pdf.set_y(34)
    pdf.set_left_margin(15)

    # 2. Light grey rounded box for "This Week at a Glance"
    overview_text = (data.get("week_overview") or "").strip()
    if overview_text:
        box_x = 15
        box_w = 180
        padding = 5
        content_w = box_w - (2 * padding)

        pdf.set_font("DejaVuSans", "B", 13)
        heading_h = 7

        pdf.set_font("DejaVuSans", "", 11)
        overview_h = pdf.multi_cell(content_w, 6, overview_text, dry_run=True, output="HEIGHT")

        box_h = padding + heading_h + 2 + overview_h + padding
        start_y = pdf.get_y()

        pdf.set_fill_color(246, 248, 251)
        pdf.set_draw_color(224, 230, 239)
        pdf.set_line_width(0.3)
        pdf.rect(box_x, start_y, box_w, box_h, style="FD", round_corners=True, corner_radius=3)

        pdf.set_font("DejaVuSans", "B", 13)
        pdf.set_text_color(24, 43, 73)
        pdf.set_xy(box_x + padding, start_y + padding)
        pdf.cell(content_w, heading_h, "This Week at a Glance", align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font("DejaVuSans", "", 11)
        pdf.set_text_color(51, 65, 85)
        pdf.set_xy(box_x + padding, start_y + padding + heading_h + 2)
        pdf.multi_cell(content_w, 6, overview_text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_y(start_y + box_h + 7)

    def render_section_header(title: str):
        if pdf.get_y() + 25 > 282:
            pdf.add_page()
        pdf.set_font("DejaVuSans", "B", 15)
        pdf.set_text_color(24, 43, 73)
        pdf.cell(0, 8, title, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(24, 43, 73)
        pdf.set_line_width(0.4)
        line_y = pdf.get_y() + 1
        pdf.line(pdf.l_margin, line_y, pdf.w - pdf.r_margin, line_y)
        pdf.set_y(line_y + 4.5)

    # 3. Important Topics
    topics = data.get("topics", [])
    if topics:
        render_section_header("Important Topics")

        for topic in topics:
            category = topic.get("category", "").strip()
            heading = topic.get("heading", "").strip()
            key_points = topic.get("key_points", [])

            tag_text = category.upper() if category else "GENERAL"
            pdf.set_font("DejaVuSans", "B", 8)
            tag_w = pdf.get_string_width(tag_text) + 6
            tag_h = 4.8

            pdf.set_font("DejaVuSans", "B", 12)
            heading_h = pdf.multi_cell(180, 5.8, heading, dry_run=True, output="HEIGHT")
            pdf.set_font("DejaVuSans", "", 10.5)
            first_pt = key_points[0].strip() if key_points else ""
            first_pt_h = pdf.multi_cell(174, 5.2, first_pt, dry_run=True, output="HEIGHT") if first_pt else 0
            needed_space = tag_h + 1.8 + heading_h + 1.8 + first_pt_h + 6

            if pdf.get_y() + needed_space > 282:
                pdf.add_page()

            # Render category tag
            tag_y = pdf.get_y()
            pdf.set_fill_color(*get_category_color(category))
            pdf.rect(15, tag_y, tag_w, tag_h, style="F", round_corners=True, corner_radius=1.5)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("DejaVuSans", "B", 8)
            pdf.set_xy(15, tag_y)
            pdf.cell(tag_w, tag_h, tag_text, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_y(tag_y + tag_h + 1.8)

            # Render topic heading
            pdf.set_font("DejaVuSans", "B", 12)
            pdf.set_text_color(24, 30, 40)
            pdf.multi_cell(180, 5.8, heading, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_y(pdf.get_y() + 1.8)

            # Render key points with hanging indent
            for pt in key_points:
                pt_text = pt.strip()
                if not pt_text:
                    continue

                if pdf.get_y() > 275:
                    pdf.add_page()

                pt_y = pdf.get_y()
                pdf.set_font("DejaVuSans", "", 10.5)
                pdf.set_text_color(51, 65, 85)

                pdf.set_xy(15, pt_y)
                pdf.cell(6, 5.2, "•")

                pdf.set_left_margin(21)
                pdf.set_xy(21, pt_y)
                pdf.multi_cell(174, 5.2, pt_text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_left_margin(15)
                pdf.set_y(pdf.get_y() + 1.5)

            pdf.set_y(pdf.get_y() + 3.5)

    # 4. Important Dates
    dates = data.get("important_dates", [])
    if dates:
        render_section_header("Important Dates")

        pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(45, 55, 72)
        pdf.set_font("DejaVuSans", "", 9.5)
        pdf.set_draw_color(218, 224, 233)
        pdf.set_line_width(0.2)

        with pdf.table(
            col_widths=(40, 140),
            headings_style=FontFace(
                family="DejaVuSans",
                emphasis="B",
                size_pt=10,
                color=(255, 255, 255),
                fill_color=(24, 43, 73),
            ),
            cell_fill_color=(247, 249, 252),
            cell_fill_mode=TableCellFillMode.EVEN_ROWS,
            text_align=(Align.L, Align.L),
            line_height=5.5,
            padding=2.5,
        ) as table:
            header_row = table.row()
            header_row.cell("Date")
            header_row.cell("Event")
            for item in dates:
                row = table.row()
                row.cell(item.get("date", "").strip())
                row.cell(item.get("event", "").strip())

    return bytes(pdf.output())


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


def extract_text(pdf_bytes: bytes) -> str:
    """Extract all readable text from the uploaded PDF bytes using PyMuPDF."""
    text_parts = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            try:
                page_text = page.get_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception:
                continue
    return "\n".join(text_parts)


def handle_error(e: Exception, api_key: Optional[str] = None):
    """Log full technical details to console/stderr only and show user-friendly message."""
    err_str = str(e)
    if api_key and api_key in err_str:
        err_str = err_str.replace(api_key, "[REDACTED_API_KEY]")

    # Print technical details to console/logs only - never show raw stack trace to user
    print(f"[ERROR] {type(e).__name__}: {err_str}", file=sys.stderr)
    traceback.print_exc()

    code = getattr(e, "code", None)
    err_lower = err_str.lower()

    if code == 429 or "429" in err_lower or "resource_exhausted" in err_lower or "quota" in err_lower:
        st.error("The free daily limit may be reached. Please wait a minute and try again, or come back tomorrow.")
    elif (
        code in (400, 401, 403)
        and (
            "api_key" in err_lower
            or "api key" in err_lower
            or "permission_denied" in err_lower
            or "invalid_argument" in err_lower
            or "unauthenticated" in err_lower
            or "forbidden" in err_lower
        )
    ):
        st.error("API key problem. Check the app secrets.")
    else:
        st.error("Something went wrong while generating the summary. Please try again.")


def summarize_text(text: str, api_key: str) -> Optional[dict]:
    """Call Google Gemini to generate structured summary, handling retries and errors."""
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        temperature=0.2,
        response_mime_type="application/json",
        response_schema=WeeklySummarySchema,
        system_instruction=SYSTEM_INSTRUCTION,
    )

    def _call_model(model_name: str) -> dict:
        response = client.models.generate_content(
            model=model_name,
            contents=text,
            config=config,
        )
        if not response or not response.text or not response.text.strip():
            raise ValueError("Empty response received from AI model")
        try:
            parsed = json.loads(response.text)
        except Exception as json_err:
            raise ValueError(f"JSON decode failed: {json_err}") from json_err

        if not isinstance(parsed, dict) or "topics" not in parsed:
            raise ValueError("Response JSON missing required fields")
        return parsed

    # Attempt primary model with automatic single retry on bad/empty JSON
    try:
        try:
            return _call_model(PRIMARY_MODEL)
        except ValueError as json_err:
            # Bad or empty JSON from AI: retry once automatically
            print(f"[WARN] Bad/empty JSON on first attempt: {json_err}. Retrying once automatically...", file=sys.stderr)
            time.sleep(1)
            try:
                return _call_model(PRIMARY_MODEL)
            except ValueError:
                st.error("The AI returned an unexpected result. Please try again.")
                return None
    except Exception as e:
        code = getattr(e, "code", None)
        err_lower = str(e).lower()
        # If rate limited or service unavailable on primary model, attempt fallback model once
        if (
            code in (429, 503)
            or "429" in err_lower
            or "503" in err_lower
            or "resource_exhausted" in err_lower
            or "unavailable" in err_lower
        ):
            try:
                return _call_model(FALLBACK_MODEL)
            except Exception as fb_err:
                handle_error(fb_err, api_key)
                return None

        handle_error(e, api_key)
        return None


SAMPLE_SUMMARY = {
    "title": "Weekly Current Affairs Summary — October 2026 (Week 3)",
    "week_overview": (
        "This week witnessed crucial geopolitical developments, major economic initiatives including a ₹ 15,200-crore "
        "clean energy program, breakthroughs in quantum satellite communications, and strategic bilateral agreements. "
        "For civil services and competitive examinations, key focus areas include the newly approved green corridors, "
        "cross-border currency settlements, and biodiversity conservation protocols."
    ),
    "topics": [
        {
            "heading": "Cabinet Approves ₹ 15,200-Crore National Clean Energy Corridor Phase-III",
            "category": "National",
            "key_points": [
                "The Union Cabinet chaired by the Prime Minister approved Phase-III of the Green Energy Corridor with an outlay of ₹ 15,200 crore.",
                "The project aims to construct approximately 4,000 circuit kilometers (ckm) of transmission lines across eight participating states.",
                "Targeted completion is slated for 2029–30, facilitating grid evacuation for large-scale solar and wind projects.",
                "Grid parity, reliability, and renewable integration were reaffirmed under the national “Mission Urja” framework.",
            ],
        },
        {
            "heading": "ISRO Unveils 'Pragyan-2' Lunar Exploration Framework & Quantum Satellite Link",
            "category": "Science and Tech",
            "key_points": [
                "ISRO successfully demonstrated secure quantum entanglement distribution over a ground-to-space distance exceeding 300 km.",
                "The milestone project was developed in close collaboration with the Raman Research Institute (RRI), Bengaluru.",
                "The upcoming lunar polar mission, code-named “Chandrayaan-5 / LUPEX”, is being developed in formal partnership with JAXA (Japan).",
                "Advanced spectral sensors will study shadowed craters for water-ice concentrations and subsurface regolith composition.",
            ],
        },
        {
            "heading": "RBI Expands Cross-Border Rupee Settlement System to Six Partner Nations",
            "category": "Economy",
            "key_points": [
                "The Reserve Bank of India officially expanded the Special Vostro Rupee Account (SVRA) facility to six additional trade partners.",
                "The strategic move is designed to diminish dependency on the US Dollar for bilateral commercial invoicing and mutual settlement.",
                "India's current account deficit contracted to 1.1% of GDP in Q2, bolstered by resilient services exports and remittance flows.",
                "Domestic forex reserves surged past ₹ 58,000 billion ($700B equivalent), providing a comfortable 11-month import cover.",
            ],
        },
    ],
    "important_dates": [
        {
            "date": "October 14, 2026",
            "event": "World Standards Day observed globally under the theme “Shared Vision for a Better World – Spotlight on AI Standards”.",
        },
        {
            "date": "October 15, 2026",
            "event": "National Innovation & Space Day observed; ₹ 2,500 crore aerospace venture fund officially launched for deep-tech startups.",
        },
        {
            "date": "October 16, 2026",
            "event": "World Food Day; UN FAO marks 81st anniversary highlighting sustainable agri-tech innovations and climate-resilient millets.",
        },
        {
            "date": "October 17, 2026",
            "event": "International Day for the Eradication of Poverty observed globally by the United Nations General Assembly.",
        },
    ],
}


def main():
    # 1. Page setup
    st.set_page_config(
        page_title="Weekly Current Affairs Summarizer",
        page_icon="📰",
        layout="centered",
    )

    # Global CSS injection
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        :root,
        [data-theme="dark"],
        [data-theme="light"],
        .stApp,
        .stApp[data-theme="dark"] {
            --bg-page: #FFFFFF !important;
            --card-bg: #FFFFFF !important;
            --card-bg-secondary: #F6F7F9 !important;
            --border-color: #E5E7EB !important;
            --border-subtle: #F3F4F6 !important;
            --text-color: #111827 !important;
            --text-body: #374151 !important;
            --muted-text: #6B7280 !important;
            --accent-color: #4F46E5 !important;
            --accent-hover: #4338CA !important;
            --accent-active: #3730A3 !important;
            --accent-subtle: rgba(79, 70, 229, 0.06) !important;
            color-scheme: light !important;
        }

        /* Force light theme always regardless of browser/system theme */
        html, body, .stApp {
            background-color: #FFFFFF !important;
            color: #111827 !important;
            color-scheme: light !important;
        }

        @media (prefers-color-scheme: dark) {
            :root,
            [data-theme="dark"],
            .stApp,
            .stApp[data-theme="dark"] {
                --bg-page: #FFFFFF !important;
                --card-bg: #FFFFFF !important;
                --card-bg-secondary: #F6F7F9 !important;
                --border-color: #E5E7EB !important;
                --border-subtle: #F3F4F6 !important;
                --text-color: #111827 !important;
                --text-body: #374151 !important;
                --muted-text: #6B7280 !important;
                --accent-color: #4F46E5 !important;
                --accent-hover: #4338CA !important;
                --accent-active: #3730A3 !important;
                --accent-subtle: rgba(79, 70, 229, 0.06) !important;
                color-scheme: light !important;
            }
            html, body, .stApp {
                background-color: #FFFFFF !important;
                color: #111827 !important;
                color-scheme: light !important;
            }
        }

        /* Global Typography */
        html, body, .stApp, p, h1, h2, h3, h4, h5, h6, input, textarea, select {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        }
        span:not([class*="material-symbols"]):not([data-testid="stIconMaterial"]),
        div:not([class*="material-symbols"]):not([data-testid="stIconMaterial"]),
        button:not([class*="material-symbols"]):not([data-testid="stIconMaterial"]) {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        }
        [class*="material-symbols"],
        [data-testid="stIconMaterial"] {
            font-family: 'Material Symbols Rounded', 'Material Icons' !important;
        }

        /* Narrow centered container */
        .main .block-container,
        [data-testid="stMainBlockContainer"] {
            max-width: 720px !important;
            padding-top: 3rem !important;
            padding-bottom: 3.5rem !important;
            padding-left: 1.5rem !important;
            padding-right: 1.5rem !important;
            margin: 0 auto !important;
        }

        @media (max-width: 640px) {
            .main .block-container,
            [data-testid="stMainBlockContainer"] {
                padding-top: 1.5rem !important;
                padding-bottom: 2rem !important;
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }
        }

        /* Chrome clean-up: hide decoration, deploy button, footer */
        [data-testid="stDecoration"] {
            display: none !important;
        }
        [data-testid="stDeployButton"],
        .stDeployButton,
        .stAppDeployButton,
        [data-testid="stToolbarActions"],
        [data-testid="stHeaderActionElements"],
        button[title="Deploy this app"] {
            display: none !important;
        }
        footer {
            display: none !important;
        }
        header[data-testid="stHeader"] {
            background: transparent !important;
        }

        /* Spacing scale: 8, 16, 24, 40 px */
        [data-testid="stVerticalBlock"] {
            gap: 16px !important;
        }
        .element-container {
            margin-bottom: 0 !important;
        }

        /* Header typography */
        h1, [data-testid="stHeading"] h1 {
            font-size: 2rem !important;
            font-weight: 700 !important;
            letter-spacing: -0.025em !important;
            line-height: 1.25 !important;
            text-align: left !important;
            color: var(--text-color) !important;
            margin-bottom: 0.25rem !important;
            padding: 0 !important;
        }
        .header-subtitle {
            font-size: 1rem !important;
            color: var(--muted-text) !important;
            margin-top: 0.25rem !important;
            margin-bottom: 1.5rem !important;
            line-height: 1.5 !important;
        }
        @media (max-width: 640px) {
            h1, [data-testid="stHeading"] h1 {
                font-size: 1.65rem !important;
            }
            .header-subtitle {
                font-size: 0.92rem !important;
            }
        }

        /* Step cards */
        .steps-container {
            display: flex;
            gap: 12px;
            margin-top: 0.25rem;
            margin-bottom: 1.5rem;
            width: 100%;
        }
        .step-card {
            flex: 1;
            display: flex;
            align-items: center;
            gap: 10px;
            background-color: var(--card-bg-secondary);
            padding: 10px 14px;
            border-radius: 12px;
            border: none;
            transition: background-color 0.15s ease;
        }
        .step-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            border-radius: 50%;
            background-color: var(--accent-color);
            color: #FFFFFF;
            font-size: 0.75rem;
            font-weight: 700;
            flex-shrink: 0;
        }
        .step-label {
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-color);
            letter-spacing: -0.01em;
        }
        @media (max-width: 640px) {
            .steps-container {
                flex-direction: column;
                gap: 8px;
            }
            .step-card {
                padding: 9px 12px;
            }
        }

        /* Uploader dropzone */
        [data-testid="stFileUploader"] {
            margin-bottom: 0.5rem;
        }
        [data-testid="stFileUploader"] label {
            font-size: 0.92rem !important;
            font-weight: 600 !important;
            color: var(--text-color) !important;
            margin-bottom: 0.5rem !important;
        }
        [data-testid="stFileUploader"] section,
        [data-testid="stFileUploaderDropzone"] {
            border: 1.5px dashed var(--border-color) !important;
            border-radius: 14px !important;
            background-color: var(--card-bg-secondary) !important;
            padding: 24px 16px !important;
            text-align: center !important;
            transition: border-color 0.2s ease, background-color 0.2s ease !important;
        }
        [data-testid="stFileUploaderDropzone"] span,
        [data-testid="stFileUploaderDropzone"] small,
        [data-testid="stFileUploaderDropzone"] div {
            color: #6B7280 !important;
        }
        [data-testid="stFileUploader"] section:hover,
        [data-testid="stFileUploaderDropzone"]:hover {
            border-color: var(--accent-color) !important;
            background-color: var(--accent-subtle) !important;
        }
        [data-testid="stFileUploader"] button[kind="secondary"],
        [data-testid="stFileUploaderDropzone"] button {
            border-radius: 8px !important;
            border: 1px solid var(--border-color) !important;
            background-color: var(--card-bg) !important;
            color: var(--text-color) !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
            padding: 0.45rem 1rem !important;
            box-shadow: none !important;
            transition: all 0.15s ease !important;
        }
        [data-testid="stFileUploader"] button[kind="secondary"]:hover,
        [data-testid="stFileUploaderDropzone"] button:hover {
            border-color: var(--accent-color) !important;
            color: var(--accent-color) !important;
            background-color: var(--card-bg) !important;
        }
        [data-testid="stFileUploaderFile"] {
            border-radius: 10px !important;
            background-color: var(--card-bg) !important;
            border: 1px solid var(--border-color) !important;
            padding: 8px 12px !important;
        }

        /* Buttons */
        .stButton > button,
        button[kind="primary"] {
            background-color: var(--accent-color) !important;
            color: #FFFFFF !important;
            border-radius: 10px !important;
            border: none !important;
            font-weight: 500 !important;
            font-size: 0.95rem !important;
            padding: 0.65rem 1.25rem !important;
            transition: background-color 0.15s ease, transform 0.05s ease !important;
            box-shadow: none !important;
        }
        .stButton > button:hover,
        button[kind="primary"]:hover {
            background-color: var(--accent-hover) !important;
            color: #FFFFFF !important;
            box-shadow: none !important;
        }
        .stButton > button:active,
        button[kind="primary"]:active {
            background-color: var(--accent-active) !important;
            transform: translateY(1px);
        }

        /* Prominent Download Button */
        [data-testid="stDownloadButton"] {
            margin-top: 1rem !important;
            margin-bottom: 1.5rem !important;
        }
        [data-testid="stDownloadButton"] > button {
            width: 100% !important;
            background-color: var(--accent-color) !important;
            color: #FFFFFF !important;
            padding: 0.85rem 1.5rem !important;
            font-size: 1.05rem !important;
            font-weight: 600 !important;
            letter-spacing: -0.01em !important;
            border-radius: 12px !important;
            border: none !important;
            box-shadow: none !important;
            transition: background-color 0.15s ease, transform 0.05s ease !important;
        }
        [data-testid="stDownloadButton"] > button:hover {
            background-color: var(--accent-hover) !important;
            box-shadow: none !important;
        }
        [data-testid="stDownloadButton"] > button:active {
            background-color: var(--accent-active) !important;
            transform: translateY(1px);
        }
        @media (max-width: 640px) {
            .stButton > button {
                width: 100% !important;
            }
        }

        /* Divider */
        hr, [data-testid="stDivider"] {
            border: none !important;
            border-top: 1px solid var(--border-color) !important;
            margin: 2rem 0 1.5rem 0 !important;
        }

        /* Results presentation */
        .overview-soft-card {
            background-color: var(--card-bg-secondary);
            border-radius: 14px;
            padding: 20px;
            margin-top: 1.25rem;
            margin-bottom: 1.5rem;
        }
        .overview-card-title {
            font-size: 1.35rem;
            font-weight: 700;
            color: var(--text-color);
            letter-spacing: -0.02em;
            margin: 0 0 0.5rem 0;
            line-height: 1.3;
        }
        .overview-card-desc {
            font-size: 0.95rem;
            line-height: 1.6;
            color: var(--text-body);
            margin: 0;
        }

        .results-section-heading {
            font-size: 1.2rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--text-color);
            margin-top: 1.75rem;
            margin-bottom: 0.85rem;
        }

        .topics-grid {
            display: flex;
            flex-direction: column;
            gap: 14px;
            margin-bottom: 1.5rem;
        }
        .topic-clean-card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 20px;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
        }
        .topic-category-pill {
            display: inline-block;
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            padding: 3px 8px;
            border-radius: 9999px;
            margin-bottom: 8px;
        }
        .topic-card-title {
            font-size: 1.12rem;
            font-weight: 600;
            color: var(--text-color);
            margin: 4px 0 10px 0;
            line-height: 1.4;
            letter-spacing: -0.01em;
        }
        .topic-card-points {
            margin: 0;
            padding-left: 1.25rem;
            color: var(--text-body);
        }
        .topic-card-points li {
            font-size: 0.93rem;
            line-height: 1.6;
            margin-bottom: 6px;
        }
        .topic-card-points li:last-child {
            margin-bottom: 0;
        }

        /* Minimal Table */
        [data-testid="stTable"] {
            margin-top: 0.25rem !important;
            margin-bottom: 1.5rem !important;
        }
        [data-testid="stTable"] table {
            width: 100% !important;
            border-collapse: collapse !important;
            border: none !important;
            background-color: transparent !important;
        }
        [data-testid="stTable"] thead tr th {
            border: none !important;
            border-bottom: 1px solid var(--border-color) !important;
            background-color: transparent !important;
            color: var(--muted-text) !important;
            font-size: 12px !important;
            font-weight: 600 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.05em !important;
            padding: 10px 12px !important;
            text-align: left !important;
        }
        [data-testid="stTable"] tbody tr td {
            border: none !important;
            border-bottom: 1px solid var(--border-subtle) !important;
            background-color: transparent !important;
            color: var(--text-body) !important;
            font-size: 0.92rem !important;
            padding: 12px !important;
            line-height: 1.5 !important;
            vertical-align: top !important;
        }
        [data-testid="stTable"] tbody tr:last-child td {
            border-bottom: none !important;
        }
        [data-testid="stTable"] tbody tr td:first-child {
            font-weight: 600 !important;
            color: var(--text-color) !important;
            white-space: nowrap !important;
            width: 28% !important;
        }

        /* Raw JSON Expander */
        [data-testid="stExpander"] {
            border: 1px solid var(--border-subtle) !important;
            border-radius: 10px !important;
            background-color: transparent !important;
            box-shadow: none !important;
            margin-top: 1.25rem !important;
        }
        [data-testid="stExpander"] summary {
            padding: 8px 12px !important;
        }
        [data-testid="stExpander"] summary span,
        [data-testid="stExpander"] summary p {
            font-size: 0.82rem !important;
            font-weight: 500 !important;
            color: var(--muted-text) !important;
        }
        [data-testid="stExpander"] summary:hover span,
        [data-testid="stExpander"] summary:hover p {
            color: var(--text-color) !important;
        }
        [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            border-top: 1px solid var(--border-subtle) !important;
            padding: 12px !important;
        }

        /* Alerts and Spinner styling */
        [data-testid="stAlert"] {
            border-radius: 12px !important;
            border: 1px solid var(--border-subtle) !important;
            padding: 12px 16px !important;
            font-size: 0.9rem !important;
            box-shadow: none !important;
        }
        [data-testid="stSpinner"] > div {
            border-top-color: var(--accent-color) !important;
        }

        /* Footer Privacy Note */
        .privacy-note {
            text-align: center;
            font-size: 12px;
            color: var(--muted-text);
            margin-top: 3.5rem;
            margin-bottom: 2rem;
            line-height: 1.5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # API key check
    api_key = st.secrets.get("GEMINI_API_KEY") if hasattr(st, "secrets") else None
    if not api_key:
        st.error("API key problem. Check the app secrets.")
        st.stop()

    # Clean header: title & subtitle
    st.title("Weekly Current Affairs Summarizer")
    st.markdown(
        '<p class="header-subtitle">Upload a current affairs PDF to generate a simple, structured study summary.</p>',
        unsafe_allow_html=True,
    )

    # "How it works" step cards
    st.markdown(
        """
        <div class="steps-container">
            <div class="step-card">
                <span class="step-badge">1</span>
                <span class="step-label">Upload PDF</span>
            </div>
            <div class="step-card">
                <span class="step-badge">2</span>
                <span class="step-label">Generate</span>
            </div>
            <div class="step-card">
                <span class="step-badge">3</span>
                <span class="step-label">Download</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # PDF Uploader
    uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])

    # Initialize session state cache for files
    if "file_cache" not in st.session_state:
        st.session_state["file_cache"] = {}

    # Pre-seed cache for local sample_output.pdf so demo/testing works without calling AI unnecessarily
    if "sample_seeded" not in st.session_state:
        st.session_state["sample_seeded"] = True
        sample_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_output.pdf")
        if os.path.exists(sample_path):
            try:
                with open(sample_path, "rb") as _sf:
                    _sb = _sf.read()
                _sh = hashlib.md5(_sb).hexdigest()
                st.session_state["file_cache"][_sh] = {
                    "summary": SAMPLE_SUMMARY,
                    "pdf_bytes": _sb,
                }
            except Exception:
                pass

    if uploaded_file is not None:
        # Check upload size limit (25 MB)
        if uploaded_file.size > MAX_FILE_SIZE_BYTES:
            st.error("This file is larger than 25 MB. Please upload a smaller PDF.")
        else:
            pdf_bytes = uploaded_file.read()
            if len(pdf_bytes) > MAX_FILE_SIZE_BYTES:
                st.error("This file is larger than 25 MB. Please upload a smaller PDF.")
            else:
                # Text extraction check
                try:
                    text = extract_text(pdf_bytes)
                except Exception as extract_err:
                    print(f"[ERROR] PDF extraction failed: {extract_err}", file=sys.stderr)
                    st.error("Could not read this PDF. The file may be damaged, password-protected, or in an unsupported format.")
                    text = None

                if text is None:
                    pass
                elif len(text.strip()) < MIN_TEXT_CHARS:
                    st.warning("This PDF has almost no readable text. It may be scanned or image-based.")
                else:
                    # File hash for caching AI usage
                    file_hash = hashlib.md5(pdf_bytes).hexdigest()
                    cached_data = st.session_state["file_cache"].get(file_hash)

                    # If not yet summarized, render Generate button
                    if cached_data is None:
                        btn_placeholder = st.empty()
                        is_generating = st.session_state.get("is_generating", False)
                        if btn_placeholder.button(
                            "Generate Summary",
                            type="primary",
                            disabled=is_generating,
                            key=f"gen_{file_hash}",
                        ):
                            # Disable / hide button immediately so it cannot be clicked twice
                            btn_placeholder.empty()
                            st.session_state["is_generating"] = True
                            try:
                                with st.spinner("Reading and summarizing... this can take up to a minute."):
                                    summary = summarize_text(text, api_key=api_key)
                                    if summary:
                                        try:
                                             pdf_output = build_pdf(summary)
                                             st.session_state["file_cache"][file_hash] = {
                                                 "summary": summary,
                                                 "pdf_bytes": pdf_output,
                                             }
                                        except Exception as pdf_err:
                                            handle_error(pdf_err, api_key)
                            finally:
                                st.session_state["is_generating"] = False
                                st.rerun()

                    # Display results if available in session_state
                    cached_data = st.session_state["file_cache"].get(file_hash)
                    if cached_data:
                        summary_data = cached_data["summary"]
                        pdf_bytes_output = cached_data["pdf_bytes"]

                        st.divider()

                        orig_name = uploaded_file.name
                        file_stem = orig_name.rsplit(".", 1)[0] if "." in orig_name else orig_name
                        pdf_filename = f"{file_stem}_summary.pdf"

                        # Prominent Download Button
                        st.download_button(
                            label="Download Summary PDF",
                            data=pdf_bytes_output,
                            file_name=pdf_filename,
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True,
                        )

                        title_text = summary_data.get("title", "Weekly Current Affairs Summary")
                        overview_text = summary_data.get("week_overview", "")

                        # Title & Overview soft card
                        st.markdown(
                            f"""
                            <div class="overview-soft-card">
                                <div class="overview-card-title">{html.escape(title_text)}</div>
                                {f'<p class="overview-card-desc">{html.escape(overview_text)}</p>' if overview_text else ''}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        # Topics Section
                        topics = summary_data.get("topics", [])
                        if topics:
                            st.markdown('<div class="results-section-heading">Important Topics</div>', unsafe_allow_html=True)
                            cards_html = ['<div class="topics-grid">']
                            for topic in topics:
                                heading = html.escape(topic.get("heading", "").strip())
                                category = topic.get("category", "").strip()
                                bg_tint, text_tint = get_category_tint(category)
                                cat_label = html.escape(category.upper() if category else "GENERAL")
                                pts = "".join(f"<li>{html.escape(pt.strip())}</li>" for pt in topic.get("key_points", []) if pt.strip())
                                cards_html.append(
                                    f'<div class="topic-clean-card">'
                                    f'<span class="topic-category-pill" style="background-color: {bg_tint}; color: {text_tint};">{cat_label}</span>'
                                    f'<div class="topic-card-title">{heading}</div>'
                                    f'<ul class="topic-card-points">{pts}</ul>'
                                    f'</div>'
                                )
                            cards_html.append('</div>')
                            st.markdown("".join(cards_html), unsafe_allow_html=True)

                        # Important Dates Section
                        important_dates = summary_data.get("important_dates", [])
                        if important_dates:
                            st.markdown('<div class="results-section-heading">Important Dates</div>', unsafe_allow_html=True)
                            table_rows = [
                                {"Date": item.get("date", ""), "Event": item.get("event", "")}
                                for item in important_dates
                            ]
                            st.table(table_rows)

                        # Raw JSON Expander
                        with st.expander("Raw JSON", expanded=False):
                            st.json(summary_data)

    # Privacy notice at bottom
    st.markdown(
        '<div class="privacy-note">'
        "Your PDF text is sent to Google's Gemini API to create the summary. Do not upload private or confidential documents."
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

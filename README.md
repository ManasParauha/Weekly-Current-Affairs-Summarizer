# Weekly Current Affairs Summarizer

A clean, single-page Streamlit web app that extracts text from weekly current affairs PDFs, generates structured, exam-ready summaries in simple English using Google Gemini, and allows downloading the result as a publication-ready PDF.

## Features

- **Accurate PDF Text Extraction**: Extracts text reliably using PyMuPDF.
- **AI-Powered Summary**: Organizes news into weekly overview, categorized topics with bullet points, and an important dates table.
- **Publication-Ready PDF Export**: Formats the summary into a multi-page, styled PDF using `fpdf2` with DejaVu Sans unicode fonts.
- **Smart Caching**: Avoids redundant API calls by caching summaries and generated PDFs by file MD5 hash.
- **Friendly Error Handling**: Gracefully handles rate limits, invalid keys, and malformed inputs.

## Local Setup

1. **Clone or navigate to the repository**:
   ```bash
   cd "Weekly Current Affairs Summarizer"
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the Gemini API Key**:
   Create a file at `.streamlit/secrets.toml` (you can copy `.streamlit/secrets.toml.example`):
   ```toml
   GEMINI_API_KEY = "your-actual-gemini-api-key"
   ```

4. **Run the Streamlit app**:
   ```bash
   streamlit run app.py
   ```

import pymupdf
from app import build_pdf


def run_test():
    sample_data = {
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
                    "The milestone project was developed in close collaboration with the Raman Research Institute (RRI), Bengaluru – setting an Asian benchmark.",
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
                "event": "Bilateral Summit in New Delhi; signing of comprehensive mobility pact and clean hydrogen technology transfer agreements.",
            },
            {
                "date": "October 18, 2026",
                "event": "International Day for Eradication of Poverty – UNDP report highlights multidimensional poverty reduction in South Asia.",
            },
            {
                "date": "October 19, 2026",
                "event": "Defence Acquisition Council approves procurement of next-generation fast patrol vessels & sensors worth ₹ 4,800 crore.",
            },
            {
                "date": "October 20, 2026",
                "event": "Global Renewable Energy Investors Meet (RE-INVEST 2026) convenes with delegations from over 45 countries.",
            },
            {
                "date": "October 21, 2026",
                "event": "National Police Commemoration Day observed across all state police headquarters honoring fallen security personnel.",
            },
        ],
    }

    print("Building PDF using build_pdf from app.py...")
    pdf_bytes = build_pdf(sample_data)
    output_pdf_path = "sample_output.pdf"
    with open(output_pdf_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Wrote {output_pdf_path} ({len(pdf_bytes)} bytes)")

    # Convert pages to images
    doc = pymupdf.open(output_pdf_path)
    print(f"Total pages generated: {len(doc)}")
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=150)
        img_name = f"sample_output_page_{i+1}.png"
        pix.save(img_name)
        print(f"Saved {img_name} ({pix.width}x{pix.height})")


if __name__ == "__main__":
    run_test()

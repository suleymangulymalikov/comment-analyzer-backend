"""
Converts the HTML report to PDF using pyhtml2pdf (headless Chrome).
Requires: pip install pyhtml2pdf
Chrome must be installed on the machine.
"""
import os


def generate_pdf(html_path, pdf_path=None):
    """
    Converts an existing HTML report to PDF.
    If pdf_path not provided, saves alongside the HTML file with .pdf extension.
    Returns the pdf_path.
    """
    try:
        from pyhtml2pdf import converter
    except ImportError:
        raise ImportError("pyhtml2pdf not installed. Run: pip install pyhtml2pdf")

    if not os.path.exists(html_path):
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    if not pdf_path:
        pdf_path = html_path.replace(".html", ".pdf")

    # pyhtml2pdf needs an absolute path with file:/// prefix
    abs_path = os.path.abspath(html_path)
    converter.convert(f"file:///{abs_path}", pdf_path)

    print(f"  ✓ PDF report saved to {pdf_path}")
    return pdf_path
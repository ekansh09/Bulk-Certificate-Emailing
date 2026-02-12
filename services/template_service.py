"""
Template loading, preview, and PDF generation service.

Handles .docx template rendering and conversion to PDF.
"""

import os
import sys
import time
import tempfile
import itertools
import mammoth
from docxtpl import DocxTemplate
from docx2pdf import convert


def get_preview_html(template_path):
    """Convert a .docx template to HTML for browser preview."""
    with open(template_path, 'rb') as f:
        result = mammoth.convert_to_html(f)
    return result.value


def get_template_variables(template_path):
    """Extract undeclared Jinja2 variables from a .docx template."""
    tpl = DocxTemplate(template_path)
    return list(tpl.get_undeclared_template_variables())


def generate_pdf(template_path, context, filename_pattern, cert_dir, logger=None):
    """
    Render a .docx template with the given context and convert to PDF.

    Returns the path to the generated PDF file.
    Retries conversion up to 3 times on failure.
    """
    # 1. Render template
    tpl = DocxTemplate(template_path)
    tpl.render(context)
    tmp_docx = tempfile.NamedTemporaryFile(suffix='.docx', delete=False).name
    tpl.save(tmp_docx)

    # 2. Compute output path
    base_name = filename_pattern.format(**context)
    if not base_name.lower().endswith('.pdf'):
        base_name += '.pdf'

    os.makedirs(cert_dir, exist_ok=True)
    final_path = os.path.join(cert_dir, base_name)

    # Avoid overwriting existing files
    name, ext = os.path.splitext(final_path)
    for i in itertools.count(1):
        if not os.path.exists(final_path):
            break
        final_path = f"{name}_{i}{ext}"

    # 3. Convert with retries (initialize COM on Windows for thread safety)
    com_initialized = False
    if sys.platform == 'win32':
        try:
            import pythoncom
            pythoncom.CoInitialize()
            com_initialized = True
        except ImportError:
            pass

    last_exc = None
    for attempt in range(1, 4):
        try:
            convert(tmp_docx, final_path)
            break
        except Exception as e:
            last_exc = e
            if logger:
                logger(f"[PDF] Conversion failed (attempt {attempt}): {e}")
            time.sleep(2)
    else:
        if com_initialized:
            pythoncom.CoUninitialize()
        os.remove(tmp_docx)
        raise RuntimeError(
            f"Could not convert DOCX to PDF after 3 attempts: {last_exc}"
        )

    if com_initialized:
        pythoncom.CoUninitialize()

    # 4. Cleanup temp file
    try:
        os.remove(tmp_docx)
    except OSError:
        pass

    return final_path

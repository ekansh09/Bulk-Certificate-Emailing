"""
Template loading, preview, and PDF generation service.

Handles .docx template rendering and conversion to PDF.
"""

import os
import re
import sys
import time
import tempfile
import itertools
import mammoth
from docxtpl import DocxTemplate
from docx2pdf import convert

# Characters illegal in Windows filenames
INVALID_FILENAME_CHARS = r'[<>:"/\|?*]'


def sanitize_filename(name):
    """Replace characters that are invalid in Windows/macOS filenames."""
    return re.sub(INVALID_FILENAME_CHARS, '_', name).strip('. ')


def get_preview_html(template_path):
    """Convert a .docx template to HTML for browser preview."""
    with open(template_path, 'rb') as f:
        result = mammoth.convert_to_html(f)
    return result.value


def _convert_with_word(docx_path, pdf_path):
    """Convert a .docx file to PDF using Word COM directly (Windows only).

    Suppresses all Word alerts and dialogs to avoid 'Command failed' errors
    caused by font substitution, compatibility prompts, or special characters.
    """
    import win32com.client
    import pywintypes  # noqa: F401 — imported for exception type

    WD_FORMAT_PDF = 17
    word = None
    doc = None
    try:
        word = win32com.client.DispatchEx('Word.Application')
        word.Visible = False
        word.DisplayAlerts = 0          # wdAlertsNone
        word.AutomationSecurity = 3     # msoAutomationSecurityForceDisable

        abs_docx = os.path.abspath(docx_path)
        abs_pdf = os.path.abspath(pdf_path)

        doc = word.Documents.Open(
            abs_docx,
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
            NoEncodingDialog=True,
        )
        doc.SaveAs2(abs_pdf, FileFormat=WD_FORMAT_PDF)
    finally:
        if doc is not None:
            try:
                doc.Close(SaveChanges=0)  # wdDoNotSaveChanges
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit(SaveChanges=0)
            except Exception:
                pass


def get_template_variables(template_path):
    """Extract undeclared Jinja2 variables from a .docx template."""
    tpl = DocxTemplate(template_path)
    return list(tpl.get_undeclared_template_variables())


def validate_rows(data_df, mapping, filename_pattern):
    """Check all rows for characters that are problematic in filenames.

    Returns a list of dicts: {row: int, field: str, value: str, chars: str}
    for every field whose value contains invalid filename characters.
    """
    filename_fmt = filename_pattern.replace('{{', '{').replace('}}', '}')
    # Figure out which placeholders appear in the filename pattern
    used_placeholders = re.findall(r'\{(\w+)\}', filename_fmt)

    issues = []
    for idx, row in data_df.iterrows():
        context = {ph: str(row[col]) for ph, col in mapping.items()}
        for ph in used_placeholders:
            val = context.get(ph, '')
            bad = set(re.findall(INVALID_FILENAME_CHARS, val))
            if bad:
                issues.append({
                    'row': int(idx) + 1,
                    'field': ph,
                    'value': val,
                    'chars': ' '.join(sorted(bad)),
                })
    return issues


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

    # 2. Compute output path (sanitize to remove invalid filename chars)
    base_name = filename_pattern.format(**context)
    base_name = sanitize_filename(base_name)
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
            if sys.platform == 'win32':
                _convert_with_word(tmp_docx, final_path)
            else:
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

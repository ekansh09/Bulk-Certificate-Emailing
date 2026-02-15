"""
Bulk Certificate Generator & Emailer — Web Application

Author: Ekansh Chauhan
Description: Flask-based web interface for generating personalized PDF
             certificates from .docx templates and emailing them in bulk.
"""

import os
import re
import sys
import json
import time
import shutil
import logging
import platform
import subprocess

from flask import (
    Flask, render_template, request, jsonify, Response, send_file,
)
import pandas as pd

from config import (
    BASE_DIR, UPLOAD_DIR, CERT_DIR, LOG_FILE, FAILED_FILE,
    load_config, save_config,
)
from services import data_service, template_service, email_service, task_service
from services import checkpoint_service

# ── Logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
log = logging.getLogger(__name__)

# ── Flask App ───────────────────────────────────────────────────────
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB


@app.errorhandler(Exception)
def handle_exception(e):
    """Return JSON instead of HTML for all uncaught errors."""
    log.exception("Unhandled exception: %s", e)
    return jsonify(error=str(e)), 500

# ── In-memory state (single-user application) ──────────────────────
state = {
    'data_df': None,
    'template_path': None,
    'active_checkpoint_id': None,
}


# ════════════════════════════════════════════════════════════════════
#  Pages
# ════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/reset', methods=['POST'])
def reset_state():
    """Clear all in-memory state so the user starts fresh."""
    state['data_df'] = None
    state['template_path'] = None
    state['active_checkpoint_id'] = None
    return jsonify(success=True)


# ════════════════════════════════════════════════════════════════════
#  Setup / Health-check endpoints
# ════════════════════════════════════════════════════════════════════

@app.route('/api/health-check')
def health_check():
    """Return a full system health report as JSON."""
    IS_WIN = platform.system() == 'Windows'
    checks = []

    # 1. Python version
    v = sys.version_info
    py_ok = v >= (3, 8)
    checks.append({
        'label': f'Python {v.major}.{v.minor}.{v.micro}',
        'ok': py_ok,
        'fix': 'Install Python 3.8 or newer' if not py_ok else None,
    })

    # 2. Virtual environment
    venv_dir = os.path.join(BASE_DIR, '.venv')
    if IS_WIN:
        venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe')
    else:
        venv_python = os.path.join(venv_dir, 'bin', 'python')
    venv_ok = os.path.isfile(venv_python)
    checks.append({
        'label': 'Virtual environment',
        'ok': venv_ok,
        'fix': 'Run: python setup.py' if not venv_ok else None,
    })

    # 3. Required packages
    required = ['flask', 'pandas', 'openpyxl', 'docxtpl',
                'docx2pdf', 'mammoth', 'retrying']
    pkg_missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            pkg_missing.append(pkg)
    checks.append({
        'label': 'Python packages',
        'ok': len(pkg_missing) == 0,
        'detail': f'Missing: {", ".join(pkg_missing)}' if pkg_missing else 'All installed',
        'fix': f'Run: pip install {" ".join(pkg_missing)}' if pkg_missing else None,
    })

    # 4. Write permissions
    perm_issues = []
    for label, d in [('Uploads', UPLOAD_DIR), ('Certificates', CERT_DIR)]:
        os.makedirs(d, exist_ok=True)
        test_f = os.path.join(d, '.write_test')
        try:
            with open(test_f, 'w') as f:
                f.write('ok')
            os.remove(test_f)
        except (PermissionError, OSError):
            perm_issues.append(label)
    checks.append({
        'label': 'Write permissions',
        'ok': len(perm_issues) == 0,
        'detail': f'Cannot write to: {", ".join(perm_issues)}' if perm_issues else 'OK',
        'fix': ('Run as Administrator' if IS_WIN else 'Check folder permissions') if perm_issues else None,
    })

    # 5. PDF backend
    pdf_ok = False
    pdf_detail = ''
    if IS_WIN:
        try:
            import win32com.client  # type: ignore
            pdf_ok = True
            pdf_detail = 'Microsoft Word (COM)'
        except Exception:
            pdf_detail = 'Microsoft Word not found'
    else:
        if shutil.which('libreoffice') or shutil.which('soffice'):
            pdf_ok = True
            pdf_detail = 'LibreOffice'
        elif os.path.exists('/Applications/Microsoft Word.app'):
            pdf_ok = True
            pdf_detail = 'Microsoft Word'
        else:
            pdf_detail = 'No converter found'
    checks.append({
        'label': 'PDF conversion backend',
        'ok': pdf_ok,
        'detail': pdf_detail,
        'fix': ('Install LibreOffice or Microsoft Word') if not pdf_ok else None,
    })

    # 6. Platform info
    info = {
        'platform': platform.system(),
        'release': platform.release(),
        'arch': platform.machine(),
        'python': f'{v.major}.{v.minor}.{v.micro}',
    }

    all_ok = all(c['ok'] for c in checks)
    return jsonify(checks=checks, info=info, all_ok=all_ok)


# ════════════════════════════════════════════════════════════════════
#  Data endpoints
# ════════════════════════════════════════════════════════════════════

@app.route('/api/upload-data', methods=['POST'])
def upload_data():
    """Upload and parse an Excel/CSV file."""
    if 'file' not in request.files:
        return jsonify(error="No file provided"), 400

    f = request.files['file']
    if not f.filename:
        return jsonify(error="Empty filename"), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ('.csv', '.xls', '.xlsx'):
        return jsonify(error=f"Unsupported file type: {ext}"), 400

    path = os.path.join(UPLOAD_DIR, f"data{ext}")
    f.save(path)

    try:
        df, fixes = data_service.load_data(path)
        state['data_df'] = df
        columns = list(df.columns)
        placeholders = [data_service.default_placeholder(c) for c in columns]
        preview = data_service.get_preview(df, page=0)
        log.info("Data loaded: %s (%d rows, %d fixes)", f.filename, len(df), len(fixes))

        # Sync to active checkpoint if one is loaded
        cp_id = state.get('active_checkpoint_id')
        if cp_id:
            checkpoint_service.sync_file_to_checkpoint(
                BASE_DIR, cp_id, path, f'data{ext}'
            )
            checkpoint_service.update_checkpoint_fields(
                BASE_DIR, cp_id, row_count=len(df)
            )

        return jsonify(
            columns=columns,
            placeholders=placeholders,
            preview=preview,
            row_count=len(df),
            fixes=fixes,
        )
    except Exception as e:
        log.error("Data load error: %s", e)
        return jsonify(error=str(e)), 400


@app.route('/api/data-preview')
def data_preview():
    """Return a paginated slice of the loaded data."""
    if state['data_df'] is None:
        return jsonify(error="No data loaded"), 400
    page = request.args.get('page', 0, type=int)
    return jsonify(data_service.get_preview(state['data_df'], page=page))


# ════════════════════════════════════════════════════════════════════
#  Template endpoints
# ════════════════════════════════════════════════════════════════════

@app.route('/api/upload-template', methods=['POST'])
def upload_template():
    """Upload a .docx template, return HTML preview and variables."""
    if 'file' not in request.files:
        return jsonify(error="No file provided"), 400

    f = request.files['file']
    if not f.filename or not f.filename.lower().endswith('.docx'):
        return jsonify(error="Please upload a .docx file"), 400

    path = os.path.join(UPLOAD_DIR, 'template.docx')
    f.save(path)
    state['template_path'] = path

    try:
        html = template_service.get_preview_html(path)
        variables = template_service.get_template_variables(path)
        log.info("Template loaded: %s (vars: %s)", f.filename, variables)

        # Sync to active checkpoint if one is loaded
        cp_id = state.get('active_checkpoint_id')
        if cp_id:
            checkpoint_service.sync_file_to_checkpoint(
                BASE_DIR, cp_id, path, 'template.docx'
            )

        return jsonify(preview_html=html, variables=variables)
    except Exception as e:
        log.error("Template load error: %s", e)
        return jsonify(error=str(e)), 400


# ════════════════════════════════════════════════════════════════════
#  Authentication endpoints
# ════════════════════════════════════════════════════════════════════

@app.route('/api/credentials')
def get_credentials():
    """Return stored credentials (local tool — not a public server)."""
    cfg = load_config()
    return jsonify(
        email=cfg.get('email', ''),
        password=cfg.get('app_password', ''),
    )


@app.route('/api/save-credentials', methods=['POST'])
def save_credentials():
    """Save email credentials to config file."""
    data = request.get_json()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    if not email or not password:
        return jsonify(error="Both email and app password are required"), 400
    save_config({'email': email, 'app_password': password})
    log.info("Credentials saved for %s", email)

    # Update active checkpoint with the new email
    cp_id = state.get('active_checkpoint_id')
    if cp_id:
        checkpoint_service.update_checkpoint_fields(
            BASE_DIR, cp_id, email_used=email
        )

    return jsonify(success=True)


@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    """Test SMTP connection with provided credentials."""
    data = request.get_json()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    if not email or not password:
        return jsonify(error="Both fields are required"), 400
    try:
        email_service.test_connection(email, password)
        log.info("SMTP test passed for %s", email)
        return jsonify(success=True, message="Connection successful")
    except Exception as e:
        log.warning("SMTP test failed for %s: %s", email, e)
        return jsonify(success=False, message=str(e)), 400


# ════════════════════════════════════════════════════════════════════
#  Processing endpoints
# ════════════════════════════════════════════════════════════════════

@app.route('/api/validate-rows', methods=['POST'])
def validate_rows():
    """Scan all rows for characters that would cause filename issues."""
    data = request.get_json()
    df = state.get('data_df')
    if df is None:
        return jsonify(error="No data loaded"), 400

    mapping = data.get('mapping', {})
    filename = data.get('filename_pattern', '')
    if not filename:
        return jsonify(error="Filename pattern is required"), 400

    issues = template_service.validate_rows(df, mapping, filename)
    return jsonify(issues=issues, total=len(df))


@app.route('/api/start', methods=['POST'])
def start_processing():
    """Validate inputs and launch the background processing task.

    Accepts a JSON ``mode`` field:
      - ``'generate'`` — only generate PDFs (no email)
      - ``'send'``     — only send emails (PDFs must exist)
      - ``'both'``     — generate then send (default)
    """
    if task_service.is_running():
        return jsonify(error="A task is already running"), 409

    data = request.get_json()
    df = state.get('data_df')
    tpl = state.get('template_path')

    mode = data.get('mode', 'both')
    if mode not in ('generate', 'send', 'both'):
        return jsonify(error="Invalid mode"), 400

    if df is None:
        return jsonify(error="No data loaded"), 400
    if tpl is None and mode in ('generate', 'both'):
        return jsonify(error="No template loaded"), 400

    mapping = data.get('mapping', {})
    recipient_col = data.get('recipient_col', '')
    email_subj = data.get('subject', '')
    email_body = data.get('body', '')           # plain text fallback
    email_body_html = data.get('body_html', '') # rich HTML body
    filename = data.get('filename_pattern', '')

    # ── Basic validation ────────────────────────────────────────
    if not recipient_col and mode in ('send', 'both'):
        return jsonify(error="Recipient email column is required"), 400
    if not email_subj and mode in ('send', 'both'):
        return jsonify(error="Email subject is required"), 400
    if not email_body and not email_body_html and mode in ('send', 'both'):
        return jsonify(error="Email body is required"), 400
    if not filename:
        return jsonify(error="Filename pattern is required"), 400

    # If body plain text is empty, strip HTML tags for a fallback
    if not email_body and email_body_html:
        email_body = re.sub(r'<[^>]+>', '', email_body_html).strip()

    # Convert {{placeholder}} → {placeholder} for .format()
    email_subj_fmt = email_subj.replace('{{', '{').replace('}}', '}')
    email_body_fmt = email_body.replace('{{', '{').replace('}}', '}')
    filename_fmt = filename.replace('{{', '{').replace('}}', '}')

    # ── Template placeholder validation (skip for send-only) ────
    errors = []
    if mode in ('generate', 'both'):
        tpl_vars_raw = template_service.get_template_variables(tpl)
        tpl_vars = {v.lower() for v in tpl_vars_raw}
        wrong_case = [v for v in tpl_vars_raw if v != v.lower()]
        missing = tpl_vars - set(mapping.keys())

        if wrong_case:
            errors.append(
                "Template placeholders not lowercase: " + ", ".join(wrong_case)
            )
        if missing:
            errors.append(
                "Unmapped template placeholders: " + ", ".join(sorted(missing))
            )

    # ── Subject / body / filename tag validation ────────────────
    def find_tags(text):
        return re.findall(r'\{(\w+)\}', text)

    if mode in ('send', 'both'):
        inv_subj = set(find_tags(email_subj_fmt)) - set(mapping.keys())
        inv_body = set(find_tags(email_body_fmt)) - set(mapping.keys())
        if inv_subj:
            errors.append("Unknown placeholders in subject: " + ", ".join(sorted(inv_subj)))
        if inv_body:
            errors.append("Unknown placeholders in body: " + ", ".join(sorted(inv_body)))

    inv_fname = set(find_tags(filename_fmt)) - set(mapping.keys())
    if inv_fname:
        errors.append("Unknown placeholders in filename: " + ", ".join(sorted(inv_fname)))

    if errors:
        return jsonify(error="\n".join(errors)), 400

    # ── Load credentials (only needed when sending) ─────────────
    auth_user = ''
    auth_pwd = ''
    if mode in ('send', 'both'):
        cfg = load_config()
        auth_user = cfg.get('email', '')
        auth_pwd = cfg.get('app_password', '')

    # ── Launch background task ──────────────────────────────────
    # Create / update checkpoint
    cp_id = data.get('checkpoint_id') or state.get('active_checkpoint_id')

    # Resolve data file path for checkpoint
    data_path = None
    for ext in ('.xlsx', '.xls', '.csv'):
        candidate = os.path.join(UPLOAD_DIR, f'data{ext}')
        if os.path.isfile(candidate):
            data_path = candidate
            break

    cp_id = checkpoint_service.create_checkpoint(
        BASE_DIR,
        mapping=mapping,
        recipient_col=recipient_col,
        subject=email_subj,
        body_plain=email_body,
        body_html=email_body_html,
        filename_pattern=filename,
        cert_dir=CERT_DIR,
        data_path=data_path,
        template_path=tpl,
        row_count=len(df),
        checkpoint_id=cp_id,
        email_used=auth_user,
    )
    state['active_checkpoint_id'] = cp_id

    task_service.start(
        data_df=df,
        template_path=tpl,
        mapping=mapping,
        recipient_col=recipient_col,
        email_subj=email_subj_fmt,
        email_body_plain=email_body_fmt,
        email_body_html=email_body_html,
        filename_pattern=filename_fmt,
        auth_user=auth_user,
        auth_pwd=auth_pwd,
        cert_dir=CERT_DIR,
        failed_path=FAILED_FILE,
        mode=mode,
        base_dir=BASE_DIR,
        checkpoint_id=cp_id,
    )

    log.info("Processing started (mode=%s): %d rows, checkpoint=%s", mode, len(df), cp_id)
    return jsonify(success=True, total=len(df), mode=mode, checkpoint_id=cp_id)


@app.route('/api/progress')
def progress_stream():
    """Server-Sent Events endpoint for real-time progress updates."""
    def generate():
        ts = task_service.task_state
        while True:
            logs = ts.drain_logs()
            payload = {
                'progress': ts.progress,
                'processed': ts.processed,
                'total': ts.total,
                'phase': ts.phase,
                'logs': logs,
                'complete': ts.complete,
                'sent': ts.sent,
                'failed_count': len(ts.failed),
                'running': ts.running,
                'mode': getattr(ts, 'mode', 'both'),
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if ts.complete:
                break
            time.sleep(0.5)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/api/download-failed')
def download_failed():
    """Download the CSV file of failed email rows."""
    if not os.path.exists(FAILED_FILE):
        return jsonify(error="No failed list available"), 404
    return send_file(FAILED_FILE, as_attachment=True, download_name='failed_list.csv')


@app.route('/api/stop', methods=['POST'])
def stop_processing():
    """Request the running task to stop gracefully."""
    if task_service.stop():
        return jsonify(success=True, message="Stop requested")
    return jsonify(error="No task is running"), 400


@app.route('/api/save-checkpoint', methods=['POST'])
def save_checkpoint_only():
    """Save the current configuration as a checkpoint without running."""
    data = request.get_json()
    df = state.get('data_df')
    tpl = state.get('template_path')

    if df is None:
        return jsonify(error="No data loaded"), 400

    mapping = data.get('mapping', {})
    recipient_col = data.get('recipient_col', '')
    email_subj = data.get('subject', '')
    email_body = data.get('body', '')
    email_body_html = data.get('body_html', '')
    filename = data.get('filename_pattern', '')

    if not filename:
        return jsonify(error="Filename pattern is required"), 400

    # If body plain text is empty, strip HTML tags for a fallback
    if not email_body and email_body_html:
        email_body = re.sub(r'<[^>]+>', '', email_body_html).strip()

    # Resolve data file path
    data_path = None
    for ext in ('.xlsx', '.xls', '.csv'):
        candidate = os.path.join(UPLOAD_DIR, f'data{ext}')
        if os.path.isfile(candidate):
            data_path = candidate
            break

    cfg = load_config()
    auth_user = cfg.get('email', '')

    cp_id = data.get('checkpoint_id') or state.get('active_checkpoint_id')
    cp_id = checkpoint_service.create_checkpoint(
        BASE_DIR,
        mapping=mapping,
        recipient_col=recipient_col,
        subject=email_subj,
        body_plain=email_body,
        body_html=email_body_html,
        filename_pattern=filename,
        cert_dir=CERT_DIR,
        data_path=data_path,
        template_path=tpl,
        row_count=len(df),
        checkpoint_id=cp_id,
        email_used=auth_user,
    )
    state['active_checkpoint_id'] = cp_id

    log.info("Checkpoint saved (no run): %s", cp_id)
    return jsonify(success=True, checkpoint_id=cp_id)


# ════════════════════════════════════════════════════════════════
#  Checkpoint endpoints
# ════════════════════════════════════════════════════════════════

@app.route('/api/checkpoints')
def list_checkpoints():
    """Return the last 3 checkpoints."""
    cps = checkpoint_service.list_checkpoints(BASE_DIR, limit=3)
    return jsonify(checkpoints=cps)


@app.route('/api/checkpoints/<cp_id>')
def get_checkpoint(cp_id):
    """Return full checkpoint details."""
    cp = checkpoint_service.load_checkpoint(BASE_DIR, cp_id)
    if not cp:
        return jsonify(error="Checkpoint not found"), 404
    return jsonify(cp)


@app.route('/api/checkpoints/<cp_id>/load', methods=['POST'])
def load_checkpoint(cp_id):
    """Load a checkpoint’s data file and template into the app state.

    Returns the checkpoint config so the frontend can restore UI fields.
    """
    cp = checkpoint_service.load_checkpoint(BASE_DIR, cp_id)
    if not cp:
        return jsonify(error="Checkpoint not found"), 404

    # Restore the data file from checkpoint
    cp_dir = os.path.join(BASE_DIR, 'checkpoints', cp_id)
    data_file = None
    for ext in ('.xlsx', '.xls', '.csv'):
        candidate = os.path.join(cp_dir, f'data{ext}')
        if os.path.isfile(candidate):
            data_file = candidate
            break

    columns = []
    row_count = 0
    if data_file:
        try:
            df, _ = data_service.load_data(data_file)
            state['data_df'] = df
            columns = list(df.columns)
            row_count = len(df)
        except Exception as e:
            log.error("Could not load checkpoint data: %s", e)
            return jsonify(error=f"Failed to load checkpoint data: {e}"), 400

    # Restore the template
    tpl_file = os.path.join(cp_dir, 'template.docx')
    if os.path.isfile(tpl_file):
        state['template_path'] = tpl_file

    state['active_checkpoint_id'] = cp_id

    # Check if saved credentials match the email used in this checkpoint
    credentials_match = False
    cp_email = cp.get('email_used', '')
    if cp_email:
        cfg = load_config()
        saved_email = cfg.get('email', '')
        saved_pwd = cfg.get('app_password', '')
        credentials_match = (saved_email == cp_email and bool(saved_pwd))
    else:
        credentials_match = True  # no email was saved, nothing to warn about

    # Get template preview HTML if available
    tpl_preview_html = ''
    tpl_vars = []
    if os.path.isfile(tpl_file):
        try:
            tpl_preview_html = template_service.get_preview_html(tpl_file)
            tpl_vars = template_service.get_template_variables(tpl_file)
        except Exception:
            pass

    # Get data preview if loaded
    data_preview = None
    placeholders = []
    if data_file and state.get('data_df') is not None:
        placeholders = [data_service.default_placeholder(c) for c in columns]
        data_preview = data_service.get_preview(state['data_df'], page=0)

    return jsonify(
        checkpoint=cp,
        columns=columns,
        placeholders=placeholders,
        row_count=row_count,
        data_loaded=data_file is not None,
        template_loaded=os.path.isfile(tpl_file),
        template_preview_html=tpl_preview_html,
        template_vars=tpl_vars,
        data_preview=data_preview,
        credentials_match=credentials_match,
        cp_email=cp_email,
    )


@app.route('/api/checkpoints/<cp_id>', methods=['PATCH'])
def update_checkpoint(cp_id):
    """Update editable fields in an existing checkpoint."""
    cp = checkpoint_service.load_checkpoint(BASE_DIR, cp_id)
    if not cp:
        return jsonify(error="Checkpoint not found"), 404

    data = request.get_json()
    ok = checkpoint_service.update_checkpoint_fields(
        BASE_DIR, cp_id,
        mapping=data.get('mapping', cp.get('mapping')),
        recipient_col=data.get('recipient_col', cp.get('recipient_col')),
        subject=data.get('subject', cp.get('subject')),
        body_plain=data.get('body_plain', cp.get('body_plain')),
        body_html=data.get('body_html', cp.get('body_html')),
        filename_pattern=data.get('filename_pattern', cp.get('filename_pattern')),
    )
    return jsonify(success=ok)


@app.route('/api/checkpoints/<cp_id>', methods=['DELETE'])
def delete_checkpoint(cp_id):
    """Delete a checkpoint."""
    checkpoint_service.delete_checkpoint(BASE_DIR, cp_id)
    if state.get('active_checkpoint_id') == cp_id:
        state['active_checkpoint_id'] = None
    return jsonify(success=True)


# ════════════════════════════════════════════════════════════════════
#  Entry point
# ════════════════════════════════════════════════════════════════════

def _open_browser():
    """Open the app in the default browser (called once after server starts)."""
    import webbrowser
    import threading

    def _wait_and_open():
        """Wait until the server is accepting connections, then open the browser."""
        import socket, time
        for _ in range(30):          # try for up to 15 seconds
            try:
                with socket.create_connection(('127.0.0.1', 5050), timeout=1):
                    break
            except OSError:
                time.sleep(0.5)
        webbrowser.open('http://127.0.0.1:5050')

    threading.Thread(target=_wait_and_open, daemon=True).start()


if __name__ == '__main__':
    log.info("=== Web Application Started ===")
    print("Starting Bulk Certificate Emailer at http://127.0.0.1:5050")

    # Only auto-open browser on the first run (debug mode spawns a reloader child)
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        _open_browser()

    app.run(debug=True, port=5050, threaded=True)

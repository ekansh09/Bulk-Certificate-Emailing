"""
Checkpoint management for persisting task configuration and PDF manifests.

Each checkpoint saves the full task config (mapping, email body, template, data)
and a PDF manifest that maps each row to its generated PDF.  This ensures
that "Send Only" mode after a server restart always attaches the correct
certificate — even when multiple rows share the same name.
"""

import os
import json
import shutil
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Maximum number of checkpoints to keep on disk
MAX_CHECKPOINTS = 10


def _checkpoints_dir(base_dir):
    d = os.path.join(base_dir, 'checkpoints')
    os.makedirs(d, exist_ok=True)
    return d


def _generate_id():
    return datetime.now().strftime('%Y%m%d_%H%M%S')


# ── Public API ──────────────────────────────────────────────────────

def create_checkpoint(base_dir, *, mapping, recipient_col, subject,
                      body_plain, body_html, filename_pattern,
                      cert_dir, data_path=None, template_path=None,
                      row_count=0, checkpoint_id=None, email_used=''):
    """Create a new checkpoint or update an existing one.

    If *checkpoint_id* is given the existing checkpoint is updated in-place;
    otherwise a fresh one is created.

    Returns the checkpoint id.
    """
    cdir = _checkpoints_dir(base_dir)

    if checkpoint_id and os.path.isdir(os.path.join(cdir, checkpoint_id)):
        cp_id = checkpoint_id
    else:
        cp_id = _generate_id()

    cp_dir = os.path.join(cdir, cp_id)
    os.makedirs(cp_dir, exist_ok=True)

    # Copy data & template into checkpoint folder (skip if source is already inside it)
    if data_path and os.path.isfile(data_path):
        ext = os.path.splitext(data_path)[1]
        dest = os.path.join(cp_dir, f'data{ext}')
        if os.path.abspath(data_path) != os.path.abspath(dest):
            shutil.copy2(data_path, dest)
    if template_path and os.path.isfile(template_path):
        dest = os.path.join(cp_dir, 'template.docx')
        if os.path.abspath(template_path) != os.path.abspath(dest):
            shutil.copy2(template_path, dest)

    meta = {
        'id': cp_id,
        'created_at': datetime.now().isoformat(),
        'mapping': mapping,
        'recipient_col': recipient_col,
        'subject': subject,
        'body_plain': body_plain,
        'body_html': body_html,
        'filename_pattern': filename_pattern,
        'cert_dir': cert_dir,
        'row_count': row_count,
        'pdf_manifest': [],
        'generated_count': 0,
        'sent_count': 0,
        'email_used': email_used,
        'status': 'in-progress',
    }

    # Keep existing pdf_manifest if updating
    meta_path = os.path.join(cp_dir, 'checkpoint.json')
    if os.path.isfile(meta_path):
        try:
            with open(meta_path) as f:
                old = json.load(f)
            meta['created_at'] = old.get('created_at', meta['created_at'])
            # Preserve pdf_manifest if we haven't generated new ones yet
            if old.get('pdf_manifest'):
                meta['pdf_manifest'] = old['pdf_manifest']
                meta['generated_count'] = old.get('generated_count', 0)
                meta['sent_count'] = old.get('sent_count', 0)
        except (json.JSONDecodeError, IOError):
            pass

    meta['updated_at'] = datetime.now().isoformat()

    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    _prune_old(cdir)
    logger.info("Checkpoint saved: %s", cp_id)
    return cp_id


def save_pdf_manifest(base_dir, checkpoint_id, pdf_manifest, generated_count=0):
    """Write the PDF manifest (list of {row_index, pdf_path, recipient}).

    Called after the generation phase completes."""
    cdir = _checkpoints_dir(base_dir)
    cp_dir = os.path.join(cdir, checkpoint_id)
    meta_path = os.path.join(cp_dir, 'checkpoint.json')

    if not os.path.isfile(meta_path):
        logger.warning("Checkpoint %s not found — cannot save manifest", checkpoint_id)
        return

    with open(meta_path) as f:
        meta = json.load(f)

    meta['pdf_manifest'] = pdf_manifest
    meta['generated_count'] = generated_count
    meta['updated_at'] = datetime.now().isoformat()

    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)


def update_sent_count(base_dir, checkpoint_id, sent_count):
    """Update the sent count after emails are dispatched."""
    cdir = _checkpoints_dir(base_dir)
    meta_path = os.path.join(cdir, checkpoint_id, 'checkpoint.json')
    if not os.path.isfile(meta_path):
        return
    with open(meta_path) as f:
        meta = json.load(f)
    meta['sent_count'] = sent_count
    meta['status'] = 'complete'
    meta['updated_at'] = datetime.now().isoformat()
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)


def mark_complete(base_dir, checkpoint_id):
    """Mark a checkpoint as complete."""
    cdir = _checkpoints_dir(base_dir)
    meta_path = os.path.join(cdir, checkpoint_id, 'checkpoint.json')
    if not os.path.isfile(meta_path):
        return
    with open(meta_path) as f:
        meta = json.load(f)
    meta['status'] = 'complete'
    meta['updated_at'] = datetime.now().isoformat()
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)


def list_checkpoints(base_dir, limit=3):
    """Return the *limit* most recent checkpoints as dicts (newest first)."""
    cdir = _checkpoints_dir(base_dir)
    results = []
    for name in os.listdir(cdir):
        meta_path = os.path.join(cdir, name, 'checkpoint.json')
        if os.path.isfile(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                # Build a friendly label
                ts = meta.get('created_at', '')
                try:
                    dt = datetime.fromisoformat(ts)
                    label = dt.strftime('%b %d, %Y  %I:%M %p')
                except Exception:
                    label = ts
                results.append({
                    'id': meta['id'],
                    'label': label,
                    'row_count': meta.get('row_count', 0),
                    'generated_count': meta.get('generated_count', 0),
                    'sent_count': meta.get('sent_count', 0),
                    'status': meta.get('status', 'unknown'),
                    'filename_pattern': meta.get('filename_pattern', ''),
                    'subject': meta.get('subject', ''),
                    'email_used': meta.get('email_used', ''),
                    'created_at': ts,
                })
            except (json.JSONDecodeError, IOError, KeyError):
                continue
    results.sort(key=lambda x: x['created_at'], reverse=True)
    return results[:limit]


def load_checkpoint(base_dir, checkpoint_id):
    """Load full checkpoint metadata including pdf_manifest."""
    cdir = _checkpoints_dir(base_dir)
    meta_path = os.path.join(cdir, checkpoint_id, 'checkpoint.json')
    if not os.path.isfile(meta_path):
        return None
    with open(meta_path) as f:
        return json.load(f)


def get_pdf_manifest(base_dir, checkpoint_id):
    """Return just the pdf_manifest list from a checkpoint, or []."""
    cp = load_checkpoint(base_dir, checkpoint_id)
    if cp:
        return cp.get('pdf_manifest', [])
    return []


def update_checkpoint_fields(base_dir, checkpoint_id, **fields):
    """Update specific fields in an existing checkpoint.

    Accepts keyword arguments for any top-level keys in the checkpoint
    JSON (mapping, subject, body_plain, body_html, filename_pattern,
    recipient_col, etc.).  Unknown keys are silently ignored.
    """
    cdir = _checkpoints_dir(base_dir)
    meta_path = os.path.join(cdir, checkpoint_id, 'checkpoint.json')
    if not os.path.isfile(meta_path):
        logger.warning("Checkpoint %s not found — cannot update", checkpoint_id)
        return False

    ALLOWED = {
        'mapping', 'recipient_col', 'subject', 'body_plain', 'body_html',
        'filename_pattern', 'email_used', 'row_count',
    }

    with open(meta_path) as f:
        meta = json.load(f)

    changed = False
    for key, value in fields.items():
        if key in ALLOWED:
            meta[key] = value
            changed = True

    if changed:
        meta['updated_at'] = datetime.now().isoformat()
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)
        logger.info("Checkpoint %s updated: %s", checkpoint_id, list(fields.keys()))

    return changed


def sync_file_to_checkpoint(base_dir, checkpoint_id, src_path, dest_name):
    """Copy a file into the checkpoint folder (e.g. after re-uploading data/template)."""
    cdir = _checkpoints_dir(base_dir)
    cp_dir = os.path.join(cdir, checkpoint_id)
    if not os.path.isdir(cp_dir):
        return
    dest = os.path.join(cp_dir, dest_name)
    if os.path.abspath(src_path) != os.path.abspath(dest):
        shutil.copy2(src_path, dest)
        logger.info("Synced %s → checkpoint %s/%s", src_path, checkpoint_id, dest_name)


def delete_checkpoint(base_dir, checkpoint_id):
    """Remove a checkpoint folder."""
    cdir = _checkpoints_dir(base_dir)
    cp_dir = os.path.join(cdir, checkpoint_id)
    if os.path.isdir(cp_dir):
        shutil.rmtree(cp_dir, ignore_errors=True)


# ── Internal ────────────────────────────────────────────────────────

def _prune_old(cdir):
    """Delete the oldest checkpoints if the total exceeds MAX_CHECKPOINTS."""
    all_cp = []
    for name in os.listdir(cdir):
        meta_path = os.path.join(cdir, name, 'checkpoint.json')
        if os.path.isfile(meta_path):
            all_cp.append((name, os.path.getmtime(meta_path)))

    all_cp.sort(key=lambda x: x[1], reverse=True)
    for name, _ in all_cp[MAX_CHECKPOINTS:]:
        shutil.rmtree(os.path.join(cdir, name), ignore_errors=True)

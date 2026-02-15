"""
Background task management for certificate generation and emailing.

Runs the generate-then-send pipeline in a background thread with
real-time progress reporting via a shared TaskState object.
"""

import threading
import queue
import time
import csv
import os
import logging

from services import email_service, template_service, checkpoint_service

logger = logging.getLogger(__name__)


class TaskState:
    """Thread-safe state container for background task progress."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.running = False
        self.progress = 0
        self.processed = 0
        self.total = 0
        self.phase = 'idle'
        self.sent = 0
        self.failed = []
        self.log_queue = queue.Queue()
        self.complete = False
        self.error = None
        self.mode = 'both'
        self.stop_requested = False

    def log(self, message):
        """Push a log message to the queue and write to file logger."""
        self.log_queue.put(message)
        logger.info(message)

    def drain_logs(self):
        """Retrieve all pending log messages (non-blocking)."""
        messages = []
        while True:
            try:
                messages.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        return messages


# Single global instance (single-user application)
task_state = TaskState()


def is_running():
    """Check if a task is currently in progress."""
    return task_state.running


def stop():
    """Request the running task to stop gracefully."""
    if task_state.running:
        task_state.stop_requested = True
        task_state.log("═══ Stop requested — finishing current item… ═══")
        return True
    return False


def start(data_df, template_path, mapping, recipient_col,
          email_subj, email_body_plain, email_body_html,
          filename_pattern, auth_user, auth_pwd, cert_dir, failed_path,
          mode='both', base_dir=None, checkpoint_id=None):
    """Validate state and launch the background processing thread.

    mode: 'generate' — only create PDFs
          'send'     — only send emails (PDFs must already exist)
          'both'     — generate then send (original behaviour)
    """
    if task_state.running:
        raise RuntimeError("A task is already running")

    task_state.reset()
    task_state.running = True
    task_state.total = len(data_df)
    task_state.mode = mode

    thread = threading.Thread(
        target=_run,
        args=(data_df, template_path, mapping, recipient_col,
              email_subj, email_body_plain, email_body_html,
              filename_pattern, auth_user, auth_pwd, cert_dir, failed_path,
              mode, base_dir, checkpoint_id),
        daemon=True,
    )
    thread.start()


# ── helpers ─────────────────────────────────────────────────────────

def _resolve_existing_pdf(context, filename_pattern, cert_dir, claimed_paths=None):
    """Return the path to an already-generated PDF for the given context,
    or None if it doesn't exist.

    When *claimed_paths* is provided (a set), any PDF that has already been
    assigned to a previous row is skipped so that duplicate names resolve
    to their correct numbered variant (e.g. name.pdf → name_1.pdf).
    The matched path is automatically added to *claimed_paths*.
    """
    if claimed_paths is None:
        claimed_paths = set()

    base_name = filename_pattern.format(**context)
    if not base_name.lower().endswith('.pdf'):
        base_name += '.pdf'
    path = os.path.join(cert_dir, base_name)

    # Check base name first, then numbered variants (_1, _2, …)
    if os.path.isfile(path) and path not in claimed_paths:
        claimed_paths.add(path)
        return path
    name, ext = os.path.splitext(path)
    for i in range(1, 100):
        variant = f"{name}_{i}{ext}"
        if os.path.isfile(variant) and variant not in claimed_paths:
            claimed_paths.add(variant)
            return variant
    return None


def _run(data_df, template_path, mapping, recipient_col,
         email_subj, email_body_plain, email_body_html,
         filename_pattern, auth_user, auth_pwd, cert_dir, failed_path,
         mode='both', base_dir=None, checkpoint_id=None):
    """Execute the pipeline according to the selected mode."""
    total = len(data_df)
    sent = 0
    failed = []
    pdf_results = []

    do_generate = mode in ('generate', 'both')
    do_send = mode in ('send', 'both')

    # ── Phase 1: Generate all PDFs ──────────────────────────────────
    if do_generate:
        task_state.phase = 'generating'
        task_state.log("═══ Phase 1: Generating certificates ═══")

        for idx, row in data_df.iterrows():
            if task_state.stop_requested:
                task_state.log("[STOP] Generation stopped by user")
                break

            context = {ph: str(row[col]) for ph, col in mapping.items()}
            try:
                pdf_path = template_service.generate_pdf(
                    template_path, context, filename_pattern, cert_dir,
                    logger=task_state.log,
                )
                pdf_results.append((row, context, pdf_path))
                label = context.get('name', f'row {idx}')
                task_state.log(f"[PDF] Generated: {label}")
            except Exception as e:
                recipient = str(row[recipient_col])
                failed.append((recipient, f"PDF error: {e}"))
                task_state.log(f"[FAIL] PDF for {recipient}: {e}")

            task_state.processed = len(pdf_results) + len(failed)
            if do_send:
                task_state.progress = int((task_state.processed / total) * 50)
            else:
                task_state.progress = int((task_state.processed / total) * 100)

        # Save PDF manifest to checkpoint
        if base_dir and checkpoint_id:
            manifest = []
            for i, (row, ctx, path) in enumerate(pdf_results):
                manifest.append({
                    'row_index': i,
                    'pdf_path': path,
                    'recipient': str(row[recipient_col]),
                })
            checkpoint_service.save_pdf_manifest(
                base_dir, checkpoint_id, manifest,
                generated_count=len(pdf_results),
            )
            task_state.log(f"[CHECKPOINT] PDF manifest saved ({len(manifest)} entries)")

    # ── Phase 1-alt: Locate existing PDFs (send-only mode) ──────────
    if mode == 'send':
        # Try to use checkpoint manifest first (reliable across restarts)
        manifest = []
        if base_dir and checkpoint_id:
            manifest = checkpoint_service.get_pdf_manifest(base_dir, checkpoint_id)

        if manifest:
            task_state.phase = 'locating'
            task_state.log("═══ Locating certificates from checkpoint ═══")

            for entry in manifest:
                if task_state.stop_requested:
                    task_state.log("[STOP] Locating stopped by user")
                    break

                pdf_path = entry['pdf_path']
                row_idx = entry['row_index']

                if row_idx >= len(data_df):
                    task_state.log(f"[SKIP] Row {row_idx} not in current data")
                    continue

                row = data_df.iloc[row_idx]
                context = {ph: str(row[col]) for ph, col in mapping.items()}

                if os.path.isfile(pdf_path):
                    pdf_results.append((row, context, pdf_path))
                    label = context.get('name', f'row {row_idx}')
                    task_state.log(f"[FOUND] {label}: {os.path.basename(pdf_path)}")
                else:
                    recipient = entry.get('recipient', str(row[recipient_col]))
                    failed.append((recipient, "Certificate PDF not found"))
                    task_state.log(f"[MISS] PDF missing: {pdf_path}")

                task_state.processed = len(pdf_results) + len(failed)
                task_state.progress = int((task_state.processed / total) * 10)
        else:
            # Fallback: resolve PDFs by filename pattern (no checkpoint)
            task_state.phase = 'locating'
            task_state.log("═══ Locating existing certificates ═══")

            claimed_paths = set()
            for idx, row in data_df.iterrows():
                if task_state.stop_requested:
                    task_state.log("[STOP] Locating stopped by user")
                    break

                context = {ph: str(row[col]) for ph, col in mapping.items()}
                pdf_path = _resolve_existing_pdf(context, filename_pattern, cert_dir, claimed_paths)
                if pdf_path:
                    pdf_results.append((row, context, pdf_path))
                    label = context.get('name', f'row {idx}')
                    task_state.log(f"[FOUND] {label}: {os.path.basename(pdf_path)}")
                else:
                    recipient = str(row[recipient_col])
                    failed.append((recipient, "Certificate PDF not found"))
                    task_state.log(f"[MISS] No PDF for {recipient}")

                task_state.processed = len(pdf_results) + len(failed)
                task_state.progress = int((task_state.processed / total) * 10)

    # ── Phase 2: Send emails ────────────────────────────────────────
    if do_send:
        task_state.phase = 'sending'
        task_state.log("═══ Phase 2: Sending emails ═══")

        progress_base = 50 if do_generate else 10

        server = None
        if auth_user and auth_pwd:
            try:
                server = email_service.create_connection(auth_user, auth_pwd)
                task_state.log("[SMTP] Connected to Gmail")
            except Exception as e:
                task_state.log(f"[ERROR] SMTP connection failed: {e}")
                task_state.error = str(e)
        else:
            task_state.log("[ERROR] Gmail credentials not provided — skipping email send")

        progress_range = 100 - progress_base

        for i, (row, context, pdf_path) in enumerate(pdf_results):
            if task_state.stop_requested:
                task_state.log("[STOP] Sending stopped by user")
                break

            recipient = str(row[recipient_col])
            try:
                subject = email_subj.format(**context)
                body_plain = email_body_plain.format(**context)

                # Replace {{placeholders}} in HTML body
                html = email_body_html
                for key, col in mapping.items():
                    html = html.replace("{{" + key + "}}", str(row[col]))

                msg = email_service.build_message(
                    auth_user, recipient, subject, body_plain, html, pdf_path,
                )

                if server:
                    email_service.send_message(server, msg)
                    sent += 1
                    task_state.log(f"[SENT] {recipient}")
                else:
                    failed.append((recipient, "No SMTP connection"))
                    task_state.log(f"[SKIP] {recipient} — no SMTP connection")

            except Exception as e:
                failed.append((recipient, f"Email error: {e}"))
                task_state.log(f"[FAIL] Email to {recipient}: {e}")

            time.sleep(1)  # Rate limiting
            email_pct = int(((i + 1) / max(len(pdf_results), 1)) * progress_range)
            task_state.progress = progress_base + email_pct

        if server:
            try:
                server.quit()
            except Exception:
                pass

    # ── Finalize ────────────────────────────────────────────────────
    stopped = task_state.stop_requested
    task_state.sent = sent
    task_state.failed = failed
    task_state.progress = 100
    task_state.processed = total
    task_state.phase = 'stopped' if stopped else 'complete'
    task_state.running = False
    task_state.complete = True

    generated_count = len(pdf_results)
    if stopped:
        task_state.log(
            f"═══ Stopped: {generated_count} generated, {sent} sent, "
            f"{len(failed)} failed ═══"
        )
    elif mode == 'generate':
        task_state.log(
            f"═══ Complete: {generated_count}/{total} certificates generated, "
            f"{len(failed)} failed ═══"
        )
    elif mode == 'send':
        task_state.log(
            f"═══ Complete: {sent}/{total} sent, {len(failed)} failed ═══"
        )
    else:
        task_state.log(
            f"═══ Complete: {generated_count} generated, {sent}/{total} sent, "
            f"{len(failed)} failed ═══"
        )

    # Update checkpoint with final counts
    if base_dir and checkpoint_id:
        if do_send:
            checkpoint_service.update_sent_count(base_dir, checkpoint_id, sent)
        else:
            checkpoint_service.mark_complete(base_dir, checkpoint_id)

    if failed:
        _export_failed(data_df, failed, recipient_col, failed_path)


def _export_failed(data_df, failed, recipient_col, failed_path):
    """Write a CSV containing all failed rows with an error column."""
    try:
        with open(failed_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            headers = list(data_df.columns) + ['error']
            writer.writerow(headers)
            for email_addr, error in failed:
                rows = data_df[data_df[recipient_col].astype(str) == email_addr]
                for _, row in rows.iterrows():
                    writer.writerow(list(row.values) + [error])
        task_state.log(f"[FILE] Failed list saved: {os.path.abspath(failed_path)}")
    except Exception as e:
        task_state.log(f"[ERROR] Could not save failed list: {e}")

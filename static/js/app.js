/* ═══════════════════════════════════════════════════════════════════
   Bulk Certificate Emailer — Frontend Logic
   ═══════════════════════════════════════════════════════════════════ */

// ── State ──────────────────────────────────────────────────────────
const state = {
    currentStep: 'home',
    columns: [],
    mapping: {},
    dataLoaded: false,
    rowCount: 0,
    templateLoaded: false,
    templateVars: [],
    credentialsSaved: false,
    currentPage: 0,
    totalPages: 1,
    eventSource: null,
    htmlSourceMode: false,
    activeCheckpointId: null,
    lastFocusedField: null,
};

// ── Initialisation ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initUploadZones();
    loadCredentials();
    setDefaults();
    initInsertableFields();
    initCheckpointAutoSave();
    loadCheckpoints();
});

function setDefaults() {
    document.getElementById('email-subject').value = 'CERTIFICATE';
    document.getElementById('filename-pattern').value = 'certificate_{{name}}.pdf';

    const editor = document.getElementById('email-body');
    editor.innerHTML =
        'Thank you for your support to make it a successful conference.<br><br>Best Regards,<br>Conf Org.';
}

// ── Step Navigation ────────────────────────────────────────────────
function goToStep(n) {
    if (n === 'home' && state.currentStep !== 'home') {
        resetApp();
    }

    state.currentStep = n;

    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    const panel = document.getElementById('panel-' + n);
    if (panel) panel.classList.add('active');

    document.querySelectorAll('.step-btn').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`.step-btn[data-step="${n}"]`);
    if (btn) btn.classList.add('active');

    if (n === 'home') loadCheckpoints();
    if (n === 4) refreshEmailConfig();
    if (n === 5) refreshChecklist();
    if (n === 0) runHealthCheck();

    updateStepStatuses();
}

function resetApp() {
    // Clear active checkpoint
    state.activeCheckpointId = null;

    // Reset data state
    state.dataLoaded = false;
    state.rowCount = 0;
    state.columns = [];
    state.mapping = {};
    state.currentPage = 0;
    state.totalPages = 1;

    // Reset template state
    state.templateLoaded = false;
    state.templateVars = [];

    // Reset misc
    state.htmlSourceMode = false;
    state.lastFocusedField = null;

    // ── Reset UI elements ──────────────────────────────────────
    // Data panel
    const dataInfo = document.getElementById('data-info');
    if (dataInfo) dataInfo.textContent = '';
    const mappingBody = document.getElementById('mapping-body');
    if (mappingBody) mappingBody.innerHTML = '';
    hide('mapping-card');
    hide('preview-card');
    hide('fixes-card');

    // Template panel
    const tplInfo = document.getElementById('template-info');
    if (tplInfo) tplInfo.textContent = '';
    const tplPreview = document.getElementById('template-preview');
    if (tplPreview) tplPreview.innerHTML = '';
    const varsEl = document.getElementById('template-vars');
    if (varsEl) varsEl.innerHTML = '';
    hide('tpl-preview-card');
    hide('vars-card');

    // Email config defaults
    setDefaults();
    const recipientSel = document.getElementById('recipient-col');
    if (recipientSel) recipientSel.innerHTML = '<option value="">-- Select column --</option>';

    // Step 5 cards
    hide('progress-section');
    hide('log-card');
    hide('results-card');
    clearLog();

    // File inputs
    const dataInput = document.getElementById('data-input');
    if (dataInput) dataInput.value = '';
    const tplInput = document.getElementById('template-input');
    if (tplInput) tplInput.value = '';

    // Close any SSE connection
    if (state.eventSource) {
        state.eventSource.close();
        state.eventSource = null;
    }

    // Tell the server to clear its state too
    fetch('/api/reset', { method: 'POST' }).catch(() => {});

    // Reload credentials (they persist across sessions)
    loadCredentials();
    updateStepStatuses();
}

function updateStepStatuses() {
    const set = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    };

    set('status-home', '');
    set('status-0', '');
    set('status-1', state.dataLoaded ? `${state.rowCount} rows` : '');
    set('status-2', state.templateLoaded ? 'Ready' : '');
    set('status-3', state.credentialsSaved ? 'Saved' : '');
    set('status-4', '');
    set('status-5', '');

    // Show/hide green checkmarks on sidebar
    toggleCheck('check-1', state.dataLoaded);
    toggleCheck('check-2', state.templateLoaded);
    toggleCheck('check-3', state.credentialsSaved);
}

function toggleCheck(id, show) {
    const el = document.getElementById(id);
    if (!el) return;
    if (show) el.classList.remove('hidden');
    else el.classList.add('hidden');
}

// ── Health Check ───────────────────────────────────────────────────
async function runHealthCheck() {
    const list = document.getElementById('health-checks');
    const result = document.getElementById('health-result');
    const loading = document.getElementById('health-loading');
    const info = document.getElementById('health-info');
    const btn = document.getElementById('run-check-btn');

    list.innerHTML = '';
    result.className = 'status-msg';
    result.textContent = '';
    loading.classList.remove('hidden');
    btn.disabled = true;
    info.textContent = '';

    try {
        const res = await fetch('/api/health-check');
        const data = await res.json();

        loading.classList.add('hidden');
        btn.disabled = false;

        if (data.info) {
            info.textContent = `Platform: ${data.info.platform} ${data.info.release} (${data.info.arch}) · Python ${data.info.python}`;
        }

        (data.checks || []).forEach(c => {
            const li = document.createElement('li');
            li.className = c.ok ? 'ok' : (c.warn ? 'warn' : 'fail');
            const icon = c.ok ? '✅' : (c.warn ? '⚠️' : '❌');
            let label = c.label;
            if (c.detail) label += ` — ${c.detail}`;
            li.innerHTML = `<span class="check-icon">${icon}</span> ${escHtml(label)}`;
            list.appendChild(li);
        });

        if (data.all_ok) {
            showStatus(result, '✓ System is ready — you can proceed!', 'success');
        } else {
            showStatus(result, '⚠ Some checks failed. Run setup.py to fix (see below).', 'error');
        }
    } catch (e) {
        loading.classList.add('hidden');
        btn.disabled = false;
        showStatus(result, 'Could not reach server: ' + e.message, 'error');
    }
}

// ── Upload Zones ───────────────────────────────────────────────────
function initUploadZones() {
    setupZone('data-zone', 'data-input', handleDataUpload);
    setupZone('template-zone', 'template-input', handleTemplateUpload);
}

function setupZone(zoneId, inputId, handler) {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(inputId);

    zone.addEventListener('click', () => input.click());

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length) handler(e.dataTransfer.files[0]);
    });

    input.addEventListener('change', () => {
        if (input.files.length) handler(input.files[0]);
    });
}

// ── Data Upload & Mapping ──────────────────────────────────────────
async function handleDataUpload(file) {
    const info = document.getElementById('data-info');
    info.textContent = 'Uploading…';

    const form = new FormData();
    form.append('file', file);

    try {
        const res = await fetch('/api/upload-data', { method: 'POST', body: form });
        const data = await res.json();

        if (!res.ok) {
            toast(data.error || 'Upload failed', 'error');
            info.textContent = '';
            return;
        }

        state.columns = data.columns;
        state.dataLoaded = true;
        state.rowCount = data.row_count;
        state.currentPage = 0;
        state.totalPages = data.preview.total_pages;

        info.textContent = `✓ ${file.name} — ${data.row_count} rows, ${data.columns.length} columns`;

        // Show auto-correction fixes if any
        if (data.fixes && data.fixes.length > 0) {
            const fixesList = document.getElementById('fixes-list');
            fixesList.innerHTML = '';
            data.fixes.forEach(f => {
                const li = document.createElement('li');
                li.innerHTML = `<span>⚠️</span> ${escHtml(f)}`;
                fixesList.appendChild(li);
            });
            show('fixes-card');
            toast(`${data.fixes.length} auto-correction(s) applied`, 'info');
        } else {
            hide('fixes-card');
        }

        buildMappingTable(data.columns, data.placeholders);
        renderPreview(data.preview);
        updatePlaceholders();
        updateStepStatuses();

        show('mapping-card');
        show('preview-card');
        toast('Data loaded successfully', 'success');
    } catch (e) {
        toast('Network error: ' + e.message, 'error');
        info.textContent = '';
    }
}

function buildMappingTable(columns, placeholders) {
    const body = document.getElementById('mapping-body');
    body.innerHTML = '';
    state.mapping = {};

    columns.forEach((col, i) => {
        const ph = placeholders[i];
        state.mapping[ph] = col;

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${escHtml(col)}</strong></td>
            <td><input type="text" value="${escHtml(ph)}" data-col="${escHtml(col)}"
                       spellcheck="false" autocomplete="off"></td>
        `;
        const input = tr.querySelector('input');
        input.addEventListener('input', () => {
            rebuildMapping();
            updatePlaceholders();
        });
        body.appendChild(tr);
    });
}

function rebuildMapping() {
    state.mapping = {};
    document.querySelectorAll('#mapping-body input').forEach(inp => {
        const ph = inp.value.trim().toLowerCase();
        const col = inp.dataset.col;
        if (ph) state.mapping[ph] = col;
    });
    // Auto-save to checkpoint when mapping changes
    _debouncedCheckpointSave();
}

function renderPreview(preview) {
    const head = document.getElementById('preview-head');
    head.innerHTML = '<tr>' +
        preview.columns.map(c => `<th>${escHtml(c)}</th>`).join('') +
        '</tr>';

    const body = document.getElementById('preview-body');
    body.innerHTML = '';
    preview.rows.forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = row.map(v => `<td>${escHtml(v)}</td>`).join('');
        body.appendChild(tr);
    });

    state.currentPage = preview.page;
    state.totalPages = preview.total_pages;
    document.getElementById('page-info').textContent =
        `Page ${preview.page + 1} of ${preview.total_pages}`;
    document.getElementById('prev-btn').disabled = preview.page === 0;
    document.getElementById('next-btn').disabled = preview.page >= preview.total_pages - 1;
}

async function changePage(delta) {
    const page = state.currentPage + delta;
    try {
        const res = await fetch(`/api/data-preview?page=${page}`);
        const data = await res.json();
        if (res.ok) renderPreview(data);
    } catch (e) {
        toast('Error loading page', 'error');
    }
}

// ── Template Upload ────────────────────────────────────────────────
async function handleTemplateUpload(file) {
    const info = document.getElementById('template-info');
    info.textContent = 'Uploading…';

    const form = new FormData();
    form.append('file', file);

    try {
        const res = await fetch('/api/upload-template', { method: 'POST', body: form });
        const data = await res.json();

        if (!res.ok) {
            toast(data.error || 'Upload failed', 'error');
            info.textContent = '';
            return;
        }

        state.templateLoaded = true;
        state.templateVars = data.variables || [];

        info.textContent = `✓ ${file.name} loaded`;

        const varsEl = document.getElementById('template-vars');
        varsEl.innerHTML = '';
        if (state.templateVars.length) {
            state.templateVars.forEach(v => {
                const span = document.createElement('span');
                span.className = 'tag';
                span.textContent = `{{${v}}}`;
                varsEl.appendChild(span);
            });
            show('vars-card');
        }

        document.getElementById('template-preview').innerHTML = data.preview_html;
        show('tpl-preview-card');

        updateStepStatuses();
        toast('Template loaded successfully', 'success');
    } catch (e) {
        toast('Network error: ' + e.message, 'error');
        info.textContent = '';
    }
}

// ── Authentication ─────────────────────────────────────────────────
async function loadCredentials() {
    try {
        const res = await fetch('/api/credentials');
        const data = await res.json();
        if (data.email) {
            document.getElementById('auth-email').value = data.email;
            state.credentialsSaved = true;
        }
        if (data.password) {
            document.getElementById('auth-password').value = data.password;
        }
        updateStepStatuses();
    } catch (e) {
        // No saved credentials — that's fine
    }
}

async function saveCredentials() {
    const email = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value.trim();
    const status = document.getElementById('auth-status');

    if (!email || !password) {
        showStatus(status, 'Both email and app password are required.', 'error');
        return;
    }

    try {
        const res = await fetch('/api/save-credentials', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await res.json();

        if (res.ok) {
            state.credentialsSaved = true;
            showStatus(status, 'Credentials saved.', 'success');
            updateStepStatuses();
        } else {
            showStatus(status, data.error || 'Save failed.', 'error');
        }
    } catch (e) {
        showStatus(status, 'Network error: ' + e.message, 'error');
    }
}

async function testConnection() {
    const email = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value.trim();
    const status = document.getElementById('auth-status');

    if (!email || !password) {
        showStatus(status, 'Enter both fields first.', 'error');
        return;
    }

    showStatus(status, 'Testing connection…', 'info');

    try {
        const res = await fetch('/api/test-connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await res.json();

        if (res.ok) {
            showStatus(status, '✓ ' + data.message, 'success');
        } else {
            showStatus(status, '✗ ' + (data.message || 'Connection failed'), 'error');
        }
    } catch (e) {
        showStatus(status, 'Network error: ' + e.message, 'error');
    }
}

function showStatus(el, text, type) {
    el.textContent = text;
    el.className = 'status-msg ' + type;
    el.style.display = 'block';
}

// ── Rich Text Editor Commands ──────────────────────────────────────
function editorCmd(cmd, value) {
    document.execCommand(cmd, false, value || null);
    document.getElementById('email-body').focus();
}

function editorFontSize(size) {
    if (!size) return;
    document.execCommand('fontSize', false, size);
    document.getElementById('email-body').focus();
}

function editorInsertLink() {
    const url = prompt('Enter URL:', 'https://');
    if (url) document.execCommand('createLink', false, url);
    document.getElementById('email-body').focus();
}

function editorInsertImage() {
    const url = prompt('Enter image URL:', 'https://');
    if (url) document.execCommand('insertImage', false, url);
    document.getElementById('email-body').focus();
}

function editorInsertHR() {
    document.execCommand('insertHorizontalRule', false, null);
    document.getElementById('email-body').focus();
}

function toggleHtmlSource() {
    const editor = document.getElementById('email-body');
    const source = document.getElementById('email-body-source');
    const toolbar = document.getElementById('editor-toolbar');
    const btn = document.getElementById('html-source-btn');

    state.htmlSourceMode = !state.htmlSourceMode;

    if (state.htmlSourceMode) {
        source.value = editor.innerHTML;
        editor.classList.add('hidden');
        source.classList.remove('hidden');
        btn.style.background = 'var(--accent)';
        btn.style.color = '#fff';
        toolbar.querySelectorAll('button:not(#html-source-btn), select, input[type=color]').forEach(
            el => el.disabled = true
        );
    } else {
        editor.innerHTML = source.value;
        source.classList.add('hidden');
        editor.classList.remove('hidden');
        btn.style.background = '';
        btn.style.color = '';
        toolbar.querySelectorAll('button, select, input[type=color]').forEach(
            el => el.disabled = false
        );
    }
}

function getEditorHtml() {
    if (state.htmlSourceMode) {
        return document.getElementById('email-body-source').value;
    }
    return document.getElementById('email-body').innerHTML;
}

function getEditorText() {
    const tmp = document.createElement('div');
    tmp.innerHTML = getEditorHtml();
    return tmp.textContent || tmp.innerText || '';
}

// ── Email Configuration ────────────────────────────────────────────
function refreshEmailConfig() {
    const sel = document.getElementById('recipient-col');
    const current = sel.value;
    sel.innerHTML = '<option value="">-- Select column --</option>';

    state.columns.forEach(col => {
        const opt = document.createElement('option');
        opt.value = col;
        opt.textContent = col;
        sel.appendChild(opt);
    });

    if (current) {
        sel.value = current;
    } else {
        for (const col of state.columns) {
            if (col.toLowerCase().includes('email')) {
                sel.value = col;
                break;
            }
        }
    }

    updatePlaceholders();
}

function updatePlaceholders() {
    const container = document.getElementById('placeholders-list');
    const card = document.getElementById('placeholders-card');
    container.innerHTML = '';

    const placeholders = Object.keys(state.mapping);
    if (placeholders.length === 0) {
        card.classList.add('hidden');
        return;
    }

    card.classList.remove('hidden');
    placeholders.forEach(ph => {
        const tag = document.createElement('span');
        tag.className = 'tag';
        tag.textContent = `{{${ph}}}`;
        tag.title = 'Click to insert into the last focused field';
        tag.onclick = () => {
            insertIntoEditor(`{{${ph}}}`);
            const targetLabel = state.lastFocusedField === 'email-subject' ? 'subject'
                : state.lastFocusedField === 'filename-pattern' ? 'filename'
                : 'body';
            toast(`Inserted {{${ph}}} into ${targetLabel}`, 'info');
        };
        container.appendChild(tag);
    });
}

function initInsertableFields() {
    // Track which field was last focused so placeholder tags insert there
    const fields = ['email-subject', 'filename-pattern'];
    fields.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('focus', () => { state.lastFocusedField = id; });
        }
    });
    const editor = document.getElementById('email-body');
    if (editor) {
        editor.addEventListener('focus', () => { state.lastFocusedField = 'email-body'; });
    }
    const source = document.getElementById('email-body-source');
    if (source) {
        source.addEventListener('focus', () => { state.lastFocusedField = 'email-body-source'; });
    }
}

function insertIntoEditor(text) {
    const target = state.lastFocusedField;

    // If the last focused field is a plain <input>, insert at its cursor position
    if (target === 'email-subject' || target === 'filename-pattern') {
        const el = document.getElementById(target);
        const start = el.selectionStart ?? el.value.length;
        const end = el.selectionEnd ?? start;
        el.value = el.value.substring(0, start) + text + el.value.substring(end);
        el.selectionStart = el.selectionEnd = start + text.length;
        el.focus();
        return;
    }

    // HTML source mode
    if (state.htmlSourceMode) {
        const ta = document.getElementById('email-body-source');
        const start = ta.selectionStart;
        const end = ta.selectionEnd;
        ta.value = ta.value.substring(0, start) + text + ta.value.substring(end);
        ta.selectionStart = ta.selectionEnd = start + text.length;
        ta.focus();
        return;
    }

    // Default: rich text editor
    const editor = document.getElementById('email-body');
    editor.focus();
    document.execCommand('insertText', false, text);
}

// ── Checklist ──────────────────────────────────────────────────────
function refreshChecklist() {
    const list = document.getElementById('checklist');
    list.innerHTML = '';

    const editorContent = getEditorText().trim();

    const checks = [
        { ok: state.dataLoaded, text: `Data loaded (${state.rowCount} rows)` },
        { ok: Object.keys(state.mapping).length > 0, text: 'Column mapping configured' },
        { ok: state.templateLoaded, text: 'Template loaded' },
        { ok: state.credentialsSaved, text: 'Gmail credentials saved' },
        { ok: !!document.getElementById('recipient-col').value, text: 'Recipient column selected' },
        { ok: !!document.getElementById('email-subject').value.trim(), text: 'Email subject set' },
        { ok: !!editorContent, text: 'Email body set' },
        { ok: !!document.getElementById('filename-pattern').value.trim(), text: 'Filename pattern set' },
    ];

    checks.forEach(c => {
        const li = document.createElement('li');
        li.className = c.ok ? 'ok' : 'fail';
        li.innerHTML = `<span class="check-icon">${c.ok ? '✅' : '❌'}</span> ${escHtml(c.text)}`;
        list.appendChild(li);
    });

    // Show "Save Session" button when all checks pass
    const allPassed = checks.every(c => c.ok);
    const saveBtn = document.getElementById('save-checkpoint-btn');
    if (saveBtn) {
        if (allPassed) saveBtn.classList.remove('hidden');
        else saveBtn.classList.add('hidden');
    }

    // Auto-run validation when step 5 is opened
    runValidation();
}

async function runValidation() {
    const container = document.getElementById('validation-results');
    if (!state.dataLoaded || !document.getElementById('filename-pattern').value.trim()) {
        container.classList.add('hidden');
        return;
    }

    rebuildMapping();

    try {
        const res = await fetch('/api/validate-rows', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mapping: state.mapping,
                filename_pattern: document.getElementById('filename-pattern').value.trim(),
            }),
        });
        const data = await res.json();

        if (!res.ok) {
            container.classList.add('hidden');
            return;
        }

        if (data.issues.length === 0) {
            container.classList.remove('hidden');
            container.innerHTML = '<p class="status-msg success" style="display:block;">✅ All rows have valid filename characters.</p>';
        } else {
            container.classList.remove('hidden');
            let html = `<p class="status-msg warning" style="display:block;">⚠️ ${data.issues.length} row(s) contain characters that will be auto-replaced with "_" in filenames:</p>`;
            html += '<div class="table-wrap" style="max-height:200px;overflow:auto;"><table class="tbl"><thead><tr><th>Row</th><th>Field</th><th>Value</th><th>Bad Chars</th></tr></thead><tbody>';
            data.issues.forEach(i => {
                html += `<tr><td>${i.row}</td><td>${escHtml(i.field)}</td><td>${escHtml(i.value)}</td><td><code>${escHtml(i.chars)}</code></td></tr>`;
            });
            html += '</tbody></table></div>';
            container.innerHTML = html;
            toast(`${data.issues.length} row(s) have special characters — they will be auto-sanitized`, 'info');
        }
    } catch (e) {
        container.classList.add('hidden');
    }
}

// ── Processing ─────────────────────────────────────────────────────
async function startProcessing(mode = 'both') {
    rebuildMapping();

    const bodyHtml = getEditorHtml();
    const bodyText = getEditorText();

    const fullHtml = bodyHtml.trim().toLowerCase().startsWith('<html')
        ? bodyHtml
        : '<html><body style="font-family:sans-serif;font-size:14px;color:#333;">' +
          bodyHtml +
          '</body></html>';

    const payload = {
        mode: mode,
        mapping: state.mapping,
        recipient_col: document.getElementById('recipient-col').value,
        subject: document.getElementById('email-subject').value.trim(),
        body: bodyText,
        body_html: fullHtml,
        filename_pattern: document.getElementById('filename-pattern').value.trim(),
        checkpoint_id: state.activeCheckpointId || null,
    };

    setModeButtonsDisabled(true);

    try {
        const res = await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (!res.ok) {
            toast(data.error || 'Start failed', 'error');
            setModeButtonsDisabled(false);
            return;
        }

        state.currentMode = mode;
        if (data.checkpoint_id) state.activeCheckpointId = data.checkpoint_id;
        show('progress-section');
        show('log-card');
        hide('results-card');
        clearLog();

        const stopBtn = document.getElementById('stop-btn');
        if (stopBtn) { stopBtn.disabled = false; stopBtn.textContent = '⏹ Stop'; }

        const modeLabels = { generate: 'Generating', send: 'Sending', both: 'Processing' };
        toast(`${modeLabels[mode]} ${data.total} rows…`, 'info');
        connectProgress();

    } catch (e) {
        toast('Network error: ' + e.message, 'error');
        setModeButtonsDisabled(false);
    }
}

function setModeButtonsDisabled(disabled) {
    ['generate-btn', 'send-btn', 'both-btn'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.disabled = disabled;
    });
}

function resetStartBtn(btn) {
    // legacy compat — now resets all mode buttons
    setModeButtonsDisabled(false);
}

function connectProgress() {
    if (state.eventSource) state.eventSource.close();

    const es = new EventSource('/api/progress');
    state.eventSource = es;

    es.onmessage = (event) => {
        const d = JSON.parse(event.data);

        document.getElementById('progress-bar').style.width = d.progress + '%';
        document.getElementById('progress-pct').textContent = d.progress + '%';
        document.getElementById('progress-count').textContent = `${d.processed} / ${d.total}`;

        const phaseMap = {
            generating: '📄 Generating certificates…',
            locating: '🔍 Locating existing certificates…',
            sending: '📧 Sending emails…',
            complete: '✅ Complete',
            stopped: '⏹ Stopped',
            idle: 'Preparing…',
        };
        document.getElementById('phase-label').textContent = phaseMap[d.phase] || d.phase;

        const logArea = document.getElementById('log-area');
        d.logs.forEach(msg => {
            const line = document.createElement('span');
            line.className = 'log-line ' + getLogClass(msg);
            line.textContent = msg;
            logArea.appendChild(line);
        });
        if (d.logs.length) logArea.scrollTop = logArea.scrollHeight;

        if (d.complete) {
            es.close();
            state.eventSource = null;
            showResults(d);
            setModeButtonsDisabled(false);
            const stopBtn = document.getElementById('stop-btn');
            if (stopBtn) stopBtn.disabled = true;
        }
    };

    es.onerror = () => {
        es.close();
        state.eventSource = null;
        setModeButtonsDisabled(false);
        toast('Connection to server lost. Check that the server is running.', 'error');
    };
}

function getLogClass(msg) {
    if (msg.startsWith('[SENT]'))  return 'sent';
    if (msg.startsWith('[FAIL]') || msg.startsWith('[ERROR]')) return 'fail';
    if (msg.startsWith('[STOP]')) return 'fail';
    if (msg.startsWith('═══'))    return 'phase';
    return 'info';
}

function showResults(data) {
    show('results-card');
    const summary = document.getElementById('results-summary');
    const mode = state.currentMode || 'both';
    const stopped = data.phase === 'stopped';
    const stoppedNote = stopped ? '<p style="color:var(--error)">⏹ Processing was stopped by user</p>' : '';

    if (mode === 'generate') {
        const generated = data.total - data.failed_count;
        summary.innerHTML = `
            ${stoppedNote}
            <p>Generated: <span class="result-sent">${generated}</span> / ${data.total} certificates</p>
            <p>Failed: <span class="result-failed">${data.failed_count}</span></p>
        `;
    } else if (mode === 'send') {
        summary.innerHTML = `
            ${stoppedNote}
            <p>Sent: <span class="result-sent">${data.sent}</span> / ${data.total}</p>
            <p>Failed: <span class="result-failed">${data.failed_count}</span></p>
        `;
    } else {
        summary.innerHTML = `
            ${stoppedNote}
            <p>Sent: <span class="result-sent">${data.sent}</span> / ${data.total}</p>
            <p>Failed: <span class="result-failed">${data.failed_count}</span></p>
        `;
    }

    const dlBtn = document.getElementById('download-failed-btn');
    if (data.failed_count > 0) {
        dlBtn.classList.remove('hidden');
    } else {
        dlBtn.classList.add('hidden');
    }

    // Show "Now Send Emails" button after a generate-only run
    const sendAfterBtn = document.getElementById('send-after-generate-btn');
    if (mode === 'generate' && data.failed_count < data.total) {
        sendAfterBtn.classList.remove('hidden');
    } else {
        sendAfterBtn.classList.add('hidden');
    }

    const modeLabels = { generate: 'generated', send: 'sent', both: 'processed' };
    toast(
        stopped
            ? `Stopped. ${mode === 'generate'
                ? (data.total - data.failed_count) + '/' + data.total + ' generated so far'
                : data.sent + '/' + data.total + ' sent so far'}.`
            : `Done! ${mode === 'generate'
                ? (data.total - data.failed_count) + '/' + data.total + ' generated'
                : data.sent + '/' + data.total + ' sent'}, ${data.failed_count} failed.`,
        (stopped || data.failed_count > 0) ? 'error' : 'success'
    );
}

function downloadFailed() {
    window.open('/api/download-failed', '_blank');
}

function clearLog() {
    document.getElementById('log-area').innerHTML = '';
}

// ── Checkpoint Auto-Save ───────────────────────────────────────────
let _cpSaveTimer = null;

function _debouncedCheckpointSave(delay = 800) {
    if (_cpSaveTimer) clearTimeout(_cpSaveTimer);
    _cpSaveTimer = setTimeout(() => autoSaveCheckpoint(), delay);
}

async function autoSaveCheckpoint() {
    const cpId = state.activeCheckpointId;
    if (!cpId) return;

    rebuildMapping();
    const bodyHtml = getEditorHtml();
    const bodyPlain = getEditorText();

    const payload = {
        mapping: state.mapping,
        recipient_col: document.getElementById('recipient-col').value,
        subject: document.getElementById('email-subject').value.trim(),
        body_plain: bodyPlain,
        body_html: bodyHtml,
        filename_pattern: document.getElementById('filename-pattern').value.trim(),
    };

    try {
        await fetch(`/api/checkpoints/${cpId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
    } catch (e) {
        // silent — auto-save is best-effort
    }
}

function initCheckpointAutoSave() {
    // Text inputs: debounced save on typing
    ['email-subject', 'filename-pattern'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', () => _debouncedCheckpointSave());
    });

    // Recipient column: save on change
    const recipientSel = document.getElementById('recipient-col');
    if (recipientSel) recipientSel.addEventListener('change', () => _debouncedCheckpointSave(0));

    // Rich text editor: debounced save on input
    const editor = document.getElementById('email-body');
    if (editor) editor.addEventListener('input', () => _debouncedCheckpointSave());

    // HTML source textarea
    const source = document.getElementById('email-body-source');
    if (source) source.addEventListener('input', () => _debouncedCheckpointSave());
}

async function stopProcessing() {
    const stopBtn = document.getElementById('stop-btn');
    if (stopBtn) {
        stopBtn.disabled = true;
        stopBtn.textContent = 'Stopping…';
    }
    try {
        const res = await fetch('/api/stop', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            toast('Stop requested — finishing current item…', 'info');
        } else {
            toast(data.error || 'Could not stop', 'error');
            if (stopBtn) { stopBtn.disabled = false; stopBtn.textContent = '⏹ Stop'; }
        }
    } catch (e) {
        toast('Network error: ' + e.message, 'error');
        if (stopBtn) { stopBtn.disabled = false; stopBtn.textContent = '⏹ Stop'; }
    }
}

async function saveCheckpointOnly() {
    rebuildMapping();

    const bodyHtml = getEditorHtml();
    const bodyText = getEditorText();

    const payload = {
        mapping: state.mapping,
        recipient_col: document.getElementById('recipient-col').value,
        subject: document.getElementById('email-subject').value.trim(),
        body: bodyText,
        body_html: bodyHtml,
        filename_pattern: document.getElementById('filename-pattern').value.trim(),
        checkpoint_id: state.activeCheckpointId || null,
    };

    const btn = document.getElementById('save-checkpoint-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

    try {
        const res = await fetch('/api/save-checkpoint', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (res.ok) {
            state.activeCheckpointId = data.checkpoint_id;
            toast('Session saved! You can close the app and resume later from Home.', 'success');
            loadCheckpoints();
        } else {
            toast(data.error || 'Save failed', 'error');
        }
    } catch (e) {
        toast('Network error: ' + e.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-3px;margin-right:4px;"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Save Session for Later`;
        }
    }
}

// ── Theme Toggle ───────────────────────────────────────────────────
function toggleTheme() {
    const html = document.documentElement;
    const icon = document.getElementById('theme-icon');
    const btn = document.getElementById('theme-btn');

    if (html.getAttribute('data-theme') === 'dark') {
        html.removeAttribute('data-theme');
        icon.textContent = '🌙';
        btn.childNodes[btn.childNodes.length - 1].textContent = ' Dark Mode';
    } else {
        html.setAttribute('data-theme', 'dark');
        icon.textContent = '☀️';
        btn.childNodes[btn.childNodes.length - 1].textContent = ' Light Mode';
    }
}

// Initialize theme button text on page load
document.addEventListener('DOMContentLoaded', () => {
    const html = document.documentElement;
    const icon = document.getElementById('theme-icon');
    const btn = document.getElementById('theme-btn');
    if (html.getAttribute('data-theme') === 'dark') {
        icon.textContent = '☀️';
        btn.childNodes[btn.childNodes.length - 1].textContent = ' Light Mode';
    }
});

// ── Toast Notifications ────────────────────────────────────────────
function toast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 3200);
}

// ── Helpers ────────────────────────────────────────────────────────
function show(id) { document.getElementById(id).classList.remove('hidden'); }
function hide(id) { document.getElementById(id).classList.add('hidden'); }

function escHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

// ── Mobile Navigation ──────────────────────────────────────────────
function toggleMobileNav() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    sidebar.classList.toggle('open');
    overlay.classList.toggle('open');
}

// Close mobile nav when a step is selected
document.addEventListener('click', (e) => {
    const btn = e.target.closest('.step-btn');
    if (btn && window.innerWidth <= 600) {
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        sidebar.classList.remove('open');
        overlay.classList.remove('open');
    }
});

// ── Checkpoints / Recent Sessions ──────────────────────────────────
async function loadCheckpoints() {
    const container = document.getElementById('checkpoints-list');
    if (!container) return;

    try {
        const res = await fetch('/api/checkpoints');
        const data = await res.json();

        const cps = data.checkpoints || [];
        if (cps.length === 0) {
            container.innerHTML = '<p class="hint" style="text-align:center;">No previous sessions found.</p>';
            return;
        }

        let html = '';
        cps.forEach(cp => {
            const isActive = cp.id === state.activeCheckpointId;
            const statusIcon = cp.status === 'complete' ? '✅' : '🔄';
            const genLabel = cp.generated_count > 0 ? `${cp.generated_count} generated` : '';
            const sentLabel = cp.sent_count > 0 ? `${cp.sent_count} sent` : '';
            const details = [genLabel, sentLabel].filter(Boolean).join(', ') || 'No activity yet';
            const emailLabel = cp.email_used ? `📧 ${cp.email_used}` : '';

            html += `
                <div class="checkpoint-item ${isActive ? 'active' : ''}" data-id="${escHtml(cp.id)}">
                    <div class="checkpoint-info">
                        <div class="checkpoint-label">
                            <span class="checkpoint-status">${statusIcon}</span>
                            <strong>${escHtml(cp.label)}</strong>
                            ${isActive ? '<span class="tag" style="margin-left:6px;font-size:11px;">Active</span>' : ''}
                        </div>
                        <div class="checkpoint-meta">
                            ${cp.row_count} rows · ${details}
                            ${cp.filename_pattern ? ' · <code>' + escHtml(cp.filename_pattern) + '</code>' : ''}
                            ${emailLabel ? '<br>' + escHtml(emailLabel) : ''}
                        </div>
                    </div>
                    <div class="checkpoint-actions">
                        <button class="btn btn-sm ${isActive ? 'btn-secondary' : 'btn-primary'}"
                                onclick="restoreCheckpoint('${escHtml(cp.id)}')"
                                ${isActive ? 'disabled' : ''}>
                            ${isActive ? 'Loaded' : 'Load'}
                        </button>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<p class="hint" style="text-align:center;">Could not load sessions.</p>';
    }
}

async function restoreCheckpoint(cpId) {
    try {
        toast('Loading session…', 'info');
        const res = await fetch(`/api/checkpoints/${cpId}/load`, { method: 'POST' });
        const data = await res.json();

        if (!res.ok) {
            toast(data.error || 'Failed to load session', 'error');
            return;
        }

        const cp = data.checkpoint;
        state.activeCheckpointId = cp.id;

        // ── Restore data state ─────────────────────────────────
        if (data.data_loaded) {
            state.dataLoaded = true;
            state.rowCount = data.row_count;
            state.columns = data.columns;

            const dataInfo = document.getElementById('data-info');
            if (dataInfo) dataInfo.textContent = `✓ Restored from session — ${data.row_count} rows, ${data.columns.length} columns`;

            // Rebuild mapping from checkpoint
            if (cp.mapping) {
                state.mapping = cp.mapping;
                const body = document.getElementById('mapping-body');
                if (body) {
                    body.innerHTML = '';
                    for (const [ph, col] of Object.entries(cp.mapping)) {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><strong>${escHtml(col)}</strong></td>
                            <td><input type="text" value="${escHtml(ph)}" data-col="${escHtml(col)}"
                                       spellcheck="false" autocomplete="off"></td>
                        `;
                        const input = tr.querySelector('input');
                        input.addEventListener('input', () => {
                            rebuildMapping();
                            updatePlaceholders();
                        });
                        body.appendChild(tr);
                    }
                }
                show('mapping-card');
            }

            // Render data preview if returned
            if (data.data_preview) {
                state.currentPage = data.data_preview.page;
                state.totalPages = data.data_preview.total_pages;
                renderPreview(data.data_preview);
                show('preview-card');
            }
        }

        // ── Restore template state ─────────────────────────────
        if (data.template_loaded) {
            state.templateLoaded = true;
            state.templateVars = data.template_vars || [];

            const tplInfo = document.getElementById('template-info');
            if (tplInfo) tplInfo.textContent = '✓ Template restored from session';

            // Show template preview
            if (data.template_preview_html) {
                const tplPreview = document.getElementById('template-preview');
                if (tplPreview) {
                    tplPreview.innerHTML = data.template_preview_html;
                    show('tpl-preview-card');
                }
            }

            // Show template variables
            if (state.templateVars.length) {
                const varsEl = document.getElementById('template-vars');
                if (varsEl) {
                    varsEl.innerHTML = '';
                    state.templateVars.forEach(v => {
                        const span = document.createElement('span');
                        span.className = 'tag';
                        span.textContent = `{{${v}}}`;
                        varsEl.appendChild(span);
                    });
                    show('vars-card');
                }
            }
        }

        // ── Restore email config fields ────────────────────────
        if (cp.subject) {
            document.getElementById('email-subject').value = cp.subject;
        }
        if (cp.filename_pattern) {
            document.getElementById('filename-pattern').value = cp.filename_pattern;
        }
        if (cp.body_html) {
            const editor = document.getElementById('email-body');
            if (editor) editor.innerHTML = cp.body_html;
        }
        if (cp.recipient_col) {
            const sel = document.getElementById('recipient-col');
            sel.innerHTML = '<option value="">-- Select column --</option>';
            state.columns.forEach(col => {
                const opt = document.createElement('option');
                opt.value = col;
                opt.textContent = col;
                sel.appendChild(opt);
            });
            sel.value = cp.recipient_col;
        }

        // ── Credential check ───────────────────────────────────
        if (data.cp_email && !data.credentials_match) {
            state.credentialsSaved = false;
            toast(`⚠️ Session used ${data.cp_email} but no matching saved password found. Update credentials in Step 3.`, 'error');
        } else if (data.cp_email && data.credentials_match) {
            state.credentialsSaved = true;
        }

        updateStepStatuses();
        updatePlaceholders();
        loadCheckpoints();

        const hasPdfManifest = cp.pdf_manifest && cp.pdf_manifest.length > 0;
        toast(
            `Session restored: ${data.row_count} rows` +
            (hasPdfManifest ? ` — ${cp.pdf_manifest.length} PDFs mapped` : ''),
            'success'
        );

        // Navigate to Step 5 so user can directly run
        goToStep(5);
    } catch (e) {
        toast('Network error: ' + e.message, 'error');
    }
}
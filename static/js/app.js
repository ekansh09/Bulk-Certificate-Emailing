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
};

// ── Initialisation ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initUploadZones();
    loadCredentials();
    setDefaults();
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
    state.currentStep = n;

    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    const panel = document.getElementById('panel-' + n);
    if (panel) panel.classList.add('active');

    document.querySelectorAll('.step-btn').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`.step-btn[data-step="${n}"]`);
    if (btn) btn.classList.add('active');

    if (n === 4) refreshEmailConfig();
    if (n === 5) refreshChecklist();
    if (n === 0) runHealthCheck();

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
        tag.title = 'Click to insert into editor';
        tag.onclick = () => {
            insertIntoEditor(`{{${ph}}}`);
            toast('Inserted: {{' + ph + '}}', 'info');
        };
        container.appendChild(tag);
    });
}

function insertIntoEditor(text) {
    const editor = document.getElementById('email-body');
    if (state.htmlSourceMode) {
        const ta = document.getElementById('email-body-source');
        const start = ta.selectionStart;
        const end = ta.selectionEnd;
        ta.value = ta.value.substring(0, start) + text + ta.value.substring(end);
        ta.selectionStart = ta.selectionEnd = start + text.length;
        ta.focus();
    } else {
        editor.focus();
        document.execCommand('insertText', false, text);
    }
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
}

// ── Processing ─────────────────────────────────────────────────────
async function startProcessing() {
    rebuildMapping();

    const bodyHtml = getEditorHtml();
    const bodyText = getEditorText();

    const fullHtml = bodyHtml.trim().toLowerCase().startsWith('<html')
        ? bodyHtml
        : '<html><body style="font-family:sans-serif;font-size:14px;color:#333;">' +
          bodyHtml +
          '</body></html>';

    const payload = {
        mapping: state.mapping,
        recipient_col: document.getElementById('recipient-col').value,
        subject: document.getElementById('email-subject').value.trim(),
        body: bodyText,
        body_html: fullHtml,
        filename_pattern: document.getElementById('filename-pattern').value.trim(),
    };

    const startBtn = document.getElementById('start-btn');
    startBtn.disabled = true;
    startBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg> Starting…';

    try {
        const res = await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (!res.ok) {
            toast(data.error || 'Start failed', 'error');
            resetStartBtn(startBtn);
            return;
        }

        show('progress-section');
        show('log-card');
        hide('results-card');
        clearLog();

        toast(`Processing ${data.total} rows…`, 'info');
        connectProgress();

    } catch (e) {
        toast('Network error: ' + e.message, 'error');
        resetStartBtn(startBtn);
    }
}

function resetStartBtn(btn) {
    btn.disabled = false;
    btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> Start Processing';
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
            sending: '📧 Sending emails…',
            complete: '✅ Complete',
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
            resetStartBtn(document.getElementById('start-btn'));
        }
    };

    es.onerror = () => {
        es.close();
        state.eventSource = null;
        resetStartBtn(document.getElementById('start-btn'));
        toast('Connection to server lost. Check that the server is running.', 'error');
    };
}

function getLogClass(msg) {
    if (msg.startsWith('[SENT]'))  return 'sent';
    if (msg.startsWith('[FAIL]') || msg.startsWith('[ERROR]')) return 'fail';
    if (msg.startsWith('═══'))    return 'phase';
    return 'info';
}

function showResults(data) {
    show('results-card');
    const summary = document.getElementById('results-summary');
    summary.innerHTML = `
        <p>Sent: <span class="result-sent">${data.sent}</span> / ${data.total}</p>
        <p>Failed: <span class="result-failed">${data.failed_count}</span></p>
    `;

    const dlBtn = document.getElementById('download-failed-btn');
    if (data.failed_count > 0) {
        dlBtn.classList.remove('hidden');
    } else {
        dlBtn.classList.add('hidden');
    }

    toast(
        `Done! ${data.sent}/${data.total} sent, ${data.failed_count} failed.`,
        data.failed_count > 0 ? 'error' : 'success'
    );
}

function downloadFailed() {
    window.open('/api/download-failed', '_blank');
}

function clearLog() {
    document.getElementById('log-area').innerHTML = '';
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
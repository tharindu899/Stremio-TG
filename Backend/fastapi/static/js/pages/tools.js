/* Page behavior: tools */
/* ─────────────── State ─────────────── */
let scanTimer = null;
let dbcTimer = null;
let deadSource = "dbcheck";   // where the current dead list came from
let purgeIds = [];            // explicit ids to purge when source = flagged

/* ─────────────── Channels ─────────────── */
async function loadChannels() {
    const list = document.getElementById('channel-list');
    try {
        const res = await fetch('/api/admin/tools/channels');
        const data = await res.json();
        const channels = (data && data.data) || [];
        if (!channels.length) {
            list.innerHTML = `<div class="hint">No AUTH channels configured. Add them in <a href="/admin/settings" style="color:var(--primary)">Settings</a>.</div>`;
            return;
        }
        list.innerHTML = channels.map(c => `
            <label class="channel-chip" data-id="${escapeHtmlAttr(c.id)}">
                <input type="checkbox" value="${escapeHtmlAttr(c.id)}" onchange="onChipChange(this)">
                <span class="channel-check" aria-hidden="true"><i class="fa-solid fa-check"></i></span>
                <span class="channel-copy">
                    <strong>${escapeHtml(c.name)}</strong>
                    <small>${escapeHtml(c.id)}</small>
                </span>
            </label>
        `).join('');
    } catch (e) {
        list.innerHTML = `<div class="hint" style="color:#ef4444">Failed to load channels.</div>`;
    }
}

function onChipChange(input) {
    input.closest('.channel-chip, .chip')?.classList.toggle('selected', input.checked);
}
function selectAllChannels(state) {
    document.querySelectorAll('#channel-list input[type=checkbox]').forEach(cb => {
        cb.checked = state;
        onChipChange(cb);
    });
}
function getSelectedChannels() {
    return [...document.querySelectorAll('#channel-list input[type=checkbox]:checked')].map(cb => cb.value);
}

/* ─────────────── Single Channel Scanner ─────────────── */
function getScanScope() {
    return document.querySelector('input[name="scan_scope"]:checked')?.value || 'all';
}
function scopeLabel(scope) {
    return ({ media: 'Media', subtitles: 'Subtitles', all: 'Everything' })[scope] || 'Everything';
}
function setScanScope(scope) {
    const input = document.querySelector(`input[name="scan_scope"][value="${scope}"]`);
    if (input) input.checked = true;
}
function setScanScopeLocked(locked) {
    document.querySelectorAll('input[name="scan_scope"]').forEach(input => { input.disabled = locked; });
}

async function startScan(mode) {
    const channels = getSelectedChannels();
    const scope = getScanScope();
    if (mode === 'scan' && !channels.length) {
        showToast('Select at least one channel to scan.', 'error', 'No channels');
        return;
    }
    try {
        const res = await fetch('/api/admin/tools/scan/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode, channels, scope })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message || `${scopeLabel(scope)} scan started.`, 'success', 'Channel Scanner');
            startScanPolling();
        } else {
            showToast(data.detail || 'Could not start scan.', 'error', 'Scanner');
        }
    } catch (e) {
        showToast('Network error.', 'error', 'Scanner');
    }
}

async function confirmRescan() {
    const channels = getSelectedChannels();
    const scope = getScanScope();
    if (!channels.length) {
        showToast('Select the channels you want to rescan.', 'error', 'No channels');
        return;
    }
    const clearText = {
        media: 'movie and series entries only',
        subtitles: 'subtitle index rows only',
        all: 'movie, series and subtitle index rows'
    }[scope];
    const safeText = scope === 'subtitles'
        ? '\n\nTelegram subtitle files and movie/series entries stay safe.'
        : '\n\nTelegram source files stay safe.';
    const confirmed = await confirmAction({
        title: 'Start rescan',
        subtitle: 'The scanner will rebuild selected index records from the first message.',
        message: `Rescan ${clearText} for ${channels.length} selected channel(s)?`,
        note: scope === 'subtitles' ? 'Telegram subtitle files and movie/series entries stay safe.' : 'Telegram source files stay safe.',
        confirmText: 'Start rescan',
        tone: 'primary'
    });
    if (!confirmed) return;
    startScan('rescan');
}

async function cancelScan() {
    try {
        const res = await fetch('/api/admin/tools/scan/cancel', { method: 'POST' });
        const data = await res.json();
        showToast(data.message || 'Stop requested.', data.ok ? 'info' : 'error', 'Channel Scanner');
    } catch (e) {
        showToast('Network error.', 'error', 'Scanner');
    }
}

function startScanPolling() {
    if (scanTimer) clearInterval(scanTimer);
    pollScan();
    scanTimer = setInterval(pollScan, 1500);
}

async function pollScan() {
    try {
        const res = await fetch('/api/admin/tools/scan/status');
        const data = await res.json();
        renderScan(data.data || {});
    } catch (e) { /* ignore transient errors */ }
}

function renderScan(s) {
    const pill = document.getElementById('scan-status-pill');
    const status = s.status || 'idle';
    const scope = s.content_scope || getScanScope();
    const scopeName = scopeLabel(scope);
    pill.className = 'status-pill status-' + status;
    pill.textContent = status.charAt(0).toUpperCase() + status.slice(1);

    const c = s.counters || {};
    setText('sc-processed', c.processed || 0);
    setText('sc-indexed', c.indexed || 0);
    setText('sc-subs-found', c.subtitles_found || 0);
    setText('sc-subs-indexed', c.subtitles_indexed || 0);
    setText('sc-subs-matched', c.subtitles_matched || 0);
    setText('sc-subs-unmatched', c.subtitles_unmatched || 0);
    setText('sc-subs-replaced', c.subtitles_replaced || 0);
    setText('sc-errors', c.errors || 0);
    setText('sc-non-video-skipped', c.skipped_nonvid || 0);
    setText('scan-elapsed', s.elapsed || '0s');

    const card = document.getElementById('scan-progress-card');
    const titleEl = document.getElementById('scan-title');
    const currentEl = document.getElementById('scan-current');
    const bar = document.getElementById('scan-bar');
    const track = bar?.parentElement;
    const startBtn = document.getElementById('scan-start-btn');
    const cancelBtn = document.getElementById('scan-cancel-btn');
    const rescanBtn = document.getElementById('rescan-btn');
    const startLabel = document.getElementById('scan-start-label');
    const errEl = document.getElementById('scan-error');
    const name = s.current_channel_name || s.current_channel || 'selected channel';

    if (s.is_running) {
        setScanScope(scope);
        setScanScopeLocked(true);
        card?.classList.add('is-running');
        titleEl.textContent = `${scopeName} scan · ${name}`;
        currentEl.textContent = scanProgressLabel(s);
        setScanProgressBar(bar, track, s, true);
        startBtn.disabled = true; rescanBtn.disabled = true; cancelBtn.disabled = false;
        errEl.style.display = 'none';
    } else {
        setScanScopeLocked(false);
        card?.classList.remove('is-running');
        startBtn.disabled = false; rescanBtn.disabled = false; cancelBtn.disabled = true;

        if (s.resumable) {
            setScanScope(scope);
            startLabel.textContent = `Resume ${scopeName} Scan`;
            titleEl.textContent = `${scopeName} scan paused`;
            currentEl.textContent = scanResumeLabel(s);
            setScanProgressBar(bar, track, s, false, 60);
        } else {
            startLabel.textContent = `Start ${scopeLabel(getScanScope())} Scan`;
            const summary = String(s.summary || '').trim();
            titleEl.textContent = status === 'completed' ? `${scopeName} scan complete` :
                status === 'error' ? `${scopeName} scan failed` :
                status === 'cancelled' ? `${scopeName} scan stopped` : 'Scanner ready';
            currentEl.textContent = status === 'completed' ? (summary || `${scopeName} scan complete.`) :
                status === 'error' ? (summary || 'Scan failed.') :
                status === 'cancelled' ? (summary || 'Scan stopped. Resume continues from the saved cursor.') :
                'Choose a channel and start a scan.';
            setScanProgressBar(bar, track, s, false, status === 'completed' ? 100 : 0);
        }

        if (s.error) { errEl.style.display = ''; errEl.textContent = s.error; }
        else errEl.style.display = 'none';

        if (scanTimer && ['completed', 'cancelled', 'error', 'paused', 'idle'].includes(status)) {
            clearInterval(scanTimer); scanTimer = null;
        }
    }
}

function hasExactScanTail(s) {
    // `target_message_id` is an internal bot-only probe ceiling when Telegram
    // blocks GetHistory. Never show it as the channel's final message ID.
    return s.tail_is_exact === true;
}

function scanTargetId(s) {
    if (!hasExactScanTail(s)) return 0;
    return Math.max(0, Number(s.latest_message_id) || 0);
}

function scanProgressLabel(s) {
    const current = Math.max(0, Number(s.current_id) || 0);
    const target = scanTargetId(s);
    if (s.phase === 'finalizing') return 'Finalizing subtitles and scan counters';
    if (current && target) return `Indexing through message #${current.toLocaleString()} → #${target.toLocaleString()}`;
    if (current) return `Indexing through message #${current.toLocaleString()}`;
    return 'Preparing the channel scan…';
}

function scanResumeLabel(s) {
    const current = Math.max(0, Number(s.current_id) || 0);
    const target = scanTargetId(s);
    if (current && target) return `Resume from message #${current.toLocaleString()} → #${target.toLocaleString()}`;
    if (current) return `Resume from message #${current.toLocaleString()}`;
    return `${(s.pending || []).length} channel(s) remaining.`;
}

function setScanProgressBar(bar, track, s, isRunning, fallbackPercent = 0) {
    if (!bar) return;
    const current = Math.max(0, Number(s.current_id) || 0);
    const target = scanTargetId(s);
    const started = Math.max(0, Number(s.start_message_id) || 0);
    let percent = fallbackPercent;

    if (s.phase === 'finalizing') {
        // All message commits finished, but final subtitle reconciliation is
        // still running. Reserve the last 1% for the actual completed state.
        percent = 99;
    } else if (target > 0 && current > 0) {
        const range = Math.max(1, target - started);
        percent = Math.round(((current - started) / range) * 100);
    }

    percent = Math.max(0, Math.min(100, percent));
    const hasKnownProgress = target > 0 && current > 0;
    bar.classList.toggle('indeterminate', Boolean(isRunning && !hasKnownProgress && s.phase !== 'finalizing'));
    bar.style.width = hasKnownProgress || !isRunning || s.phase === 'finalizing' ? `${percent}%` : '';
    if (track) track.setAttribute('aria-valuenow', String(percent));
}

document.addEventListener('change', (event) => {
    if (event.target?.name === 'scan_scope') {
        const status = document.getElementById('scan-status-pill')?.textContent?.toLowerCase();
        if (!['running', 'paused', 'cancelled'].includes(status)) {
            document.getElementById('scan-start-label').textContent = `Start ${scopeLabel(getScanScope())} Scan`;
        }
    }
});

/* ─────────────── DB Check control ─────────────── */
async function startDbCheck() {
    try {
        const res = await fetch('/api/admin/tools/dbcheck/start', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            showToast('DB check started.', 'success', 'DB Check');
            startDbcPolling();
        } else {
            showToast(data.detail || 'Could not start.', 'error', 'Error');
        }
    } catch (e) { showToast('Network error.', 'error', 'Error'); }
}

async function cancelDbCheck() {
    try {
        const res = await fetch('/api/admin/tools/dbcheck/cancel', { method: 'POST' });
        const data = await res.json();
        showToast(data.message || 'Stop requested.', data.ok ? 'info' : 'error', 'DB Check');
    } catch (e) { showToast('Network error.', 'error', 'Error'); }
}

function startDbcPolling() {
    if (dbcTimer) clearInterval(dbcTimer);
    pollDbc();
    dbcTimer = setInterval(pollDbc, 1500);
}

async function pollDbc() {
    try {
        const res = await fetch('/api/admin/tools/dbcheck/status');
        const data = await res.json();
        renderDbc(data.data || {});
    } catch (e) { /* ignore */ }
}

function renderDbc(s) {
    const pill = document.getElementById('dbc-status-pill');
    const status = s.status || 'idle';
    pill.className = 'status-pill status-' + status;
    pill.textContent = status.charAt(0).toUpperCase() + status.slice(1);

    setText('dbc-checked', s.checked || 0);
    setText('dbc-alive', s.alive || 0);
    setText('dbc-dead', s.dead || 0);
    setText('dbc-errors', s.errors || 0);
    setText('dbc-purged', s.purged || 0);
    setText('dbc-speed', s.speed || 0);
    setText('dbc-elapsed', s.elapsed || '0s');

    const bar = document.getElementById('dbc-bar');
    const startBtn = document.getElementById('dbc-start-btn');
    const cancelBtn = document.getElementById('dbc-cancel-btn');

    if (s.is_running) {
        document.getElementById('dbc-current').textContent = `Checking… ${s.checked || 0} verified`;
        bar.classList.add('indeterminate');
        startBtn.disabled = true; cancelBtn.disabled = false;
    } else {
        bar.classList.remove('indeterminate');
        bar.style.width = (status === 'completed' || status === 'cancelled') ? '100%' : '0%';
        startBtn.disabled = false; cancelBtn.disabled = true;
        document.getElementById('dbc-current').textContent =
            status === 'completed' ? `Done — ${s.dead || 0} dead found.` :
            status === 'cancelled' ? 'Stopped.' :
            status === 'error' ? 'Check failed.' : 'No check running';

        if (dbcTimer && ['completed','cancelled','error','idle'].includes(status)) {
            clearInterval(dbcTimer); dbcTimer = null;
        }
    }

    // refresh dead list from this run's findings
    if ((s.dead_entries || []).length || status === 'completed') {
        deadSource = 'dbcheck';
        purgeIds = [];
        renderDeadList(s.dead_entries || []);
    }
}

/* ─────────────── Dead links ─────────────── */
function renderDeadList(entries) {
    const list = document.getElementById('dead-list');
    const purgeBtn = document.getElementById('purge-btn');
    const purgeLabel = document.getElementById('purge-label');

    if (!entries.length) {
        list.innerHTML = `<div class="hint">No dead links to show.</div>`;
        purgeBtn.disabled = true;
        purgeLabel.textContent = 'Purge dead links';
        return;
    }
    list.innerHTML = entries.map(e => `
        <div class="dead-row">
            <span class="min-w-0 truncate">
                <i class="fa-solid fa-link-slash" style="color:#ef4444"></i>
                ${escapeHtml(e.title || 'Unknown')}
                ${e.quality ? `<span class="c-id">· ${escapeHtml(e.quality)}</span>` : ''}
            </span>
        </div>
    `).join('');
    purgeBtn.disabled = false;
    purgeLabel.textContent = `Purge ${entries.length} dead link${entries.length === 1 ? '' : 's'}`;
}

async function loadFlaggedDeadLinks() {
    try {
        const res = await fetch('/api/admin/dead-links');
        const data = await res.json();
        const links = (data && data.data) || [];
        deadSource = 'flagged';
        purgeIds = links.map(l => l.quality_id).filter(Boolean);
        renderDeadList(links.map(l => ({ title: l.title, quality: l.quality })));
        showToast(`${links.length} flagged dead link(s) loaded.`, 'info', 'Dead Links');
    } catch (e) { showToast('Failed to load flagged links.', 'error', 'Error'); }
}

async function purgeDeadLinks() {
    const confirmed = await confirmAction({ title: 'Purge dead links', subtitle: 'This cannot be undone.', message: 'Permanently remove these dead links from the database?', confirmText: 'Purge links', tone: 'danger' });
    if (!confirmed) return;
    const btn = document.getElementById('purge-btn');
    btn.disabled = true;
    const body = (deadSource === 'flagged')
        ? { source: 'flagged' }
        : { source: 'dbcheck' };
    try {
        const res = await fetch('/api/admin/tools/dead-links/purge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (res.ok && data.ok) {
            showToast(data.message || 'Purged.', 'success', 'Dead Links');
            renderDeadList([]);
            pollDbc();
        } else {
            showToast(data.message || data.detail || 'Nothing to purge.', 'error', 'Dead Links');
            btn.disabled = false;
        }
    } catch (e) {
        showToast('Network error.', 'error', 'Error');
        btn.disabled = false;
    }
}

/* ─────────────── Utils ─────────────── */
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function escapeHtml(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}
function escapeHtmlAttr(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;');
}

/* ─────────────── Init ─────────────── */
loadChannels();
pollScan().then(() => {
    const pill = document.getElementById('scan-status-pill');
    if (pill.classList.contains('status-running')) startScanPolling();
});
pollDbc().then(() => {
    const pill = document.getElementById('dbc-status-pill');
    if (pill.classList.contains('status-running')) startDbcPolling();
});

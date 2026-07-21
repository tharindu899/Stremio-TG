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
    const scopeText = {
        media: 'movies, series and split videos',
        subtitles: 'subtitles',
        all: 'media and subtitles'
    }[scope];
    const confirmed = await confirmAction({
        title: 'Start safe rescan',
        subtitle: 'The scanner will read from the first message without purging your indexed library.',
        message: `Safely check older ${scopeText} for ${channels.length} selected channel(s)?`,
        note: 'Existing indexed records stay in place. Missing posts are added and captions are refreshed for tag-based catalogs.',
        confirmText: 'Start safe rescan',
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


/* ─────────────── Duplicate Check & Cleanup ─────────────── */
let dupTimer = null;

function selectedDuplicateIds() {
    return [...document.querySelectorAll('.dup-entry-check:checked')].map(input => input.value);
}

function syncDuplicateButtons() {
    const selected = selectedDuplicateIds().length;
    const count = Number(document.getElementById('dup-count')?.textContent || 0);
    const running = document.getElementById('dup-status-pill')?.classList.contains('status-running');
    const selectedBtn = document.getElementById('dup-selected-btn');
    const allBtn = document.getElementById('dup-all-btn');
    if (selectedBtn) selectedBtn.disabled = running || selected === 0;
    if (allBtn) allBtn.disabled = running || count === 0;
}

function renderDuplicateGroups(groups) {
    const list = document.getElementById('duplicate-list');
    if (!list) return;
    if (!groups?.length) {
        list.innerHTML = `<div class="dead-empty"><i class="fa-solid fa-circle-check"></i><span>No duplicate streams found.</span></div>`;
        syncDuplicateButtons();
        return;
    }
    list.innerHTML = groups.map(group => {
        const entries = group.entries || [];
        return `<article class="duplicate-group">
            <header><div><strong>${escapeHtml(group.title || 'Unknown title')}</strong><span>${escapeHtml(group.quality || 'Auto')} · ${entries.length} copies</span></div><span class="duplicate-type">${escapeHtml(group.media_type || 'media')}</span></header>
            <div class="duplicate-entries">${entries.map((entry, index) => {
                const keep = index === entries.length - 1;
                return `<label class="duplicate-entry ${keep ? 'is-keep' : ''}">
                    <input class="dup-entry-check" type="checkbox" value="${escapeHtmlAttr(entry.id)}" ${keep ? '' : 'checked'} onchange="syncDuplicateButtons()">
                    <span class="channel-check"><i class="fa-solid fa-check"></i></span>
                    <span class="duplicate-entry-copy"><strong>${escapeHtml(entry.name || 'Unnamed stream')}</strong><small>${escapeHtml(entry.size || 'Unknown size')}${entry.parts ? ` · ${entry.parts} parts` : ''}</small></span>
                    <span class="duplicate-keep-label">${keep ? 'Keep newest' : 'Remove'}</span>
                </label>`;
            }).join('')}</div>
        </article>`;
    }).join('');
    syncDuplicateButtons();
}

async function startDuplicateCheck() {
    try {
        const response = await fetch('/api/admin/tools/duplicates/start', { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || data.message || 'Could not start duplicate scan.');
        showToast(data.message || 'Duplicate scan started.', 'success', 'Duplicates');
        startDuplicatePolling();
        await pollDuplicates();
    } catch (error) {
        showToast(error.message || 'Could not start duplicate scan.', 'error', 'Duplicates');
    }
}

async function cancelDuplicateCheck() {
    try {
        const response = await fetch('/api/admin/tools/duplicates/cancel', { method: 'POST' });
        const data = await response.json();
        showToast(data.message || data.detail || 'Stop requested.', response.ok ? 'info' : 'error', 'Duplicates');
    } catch (_) {
        showToast('Network error.', 'error', 'Duplicates');
    }
}

function startDuplicatePolling() {
    if (dupTimer) clearInterval(dupTimer);
    dupTimer = setInterval(pollDuplicates, 1200);
}

async function pollDuplicates() {
    try {
        const response = await fetch('/api/admin/tools/duplicates/status');
        const payload = await response.json();
        const state = payload.data || {};
        const status = state.status || 'idle';
        const pill = document.getElementById('dup-status-pill');
        if (pill) {
            pill.textContent = status.charAt(0).toUpperCase() + status.slice(1);
            pill.className = `status-pill ${status === 'running' ? 'status-running' : status === 'error' ? 'status-error' : 'status-idle'}`;
        }
        setText('dup-scanned', state.scanned || 0);
        setText('dup-groups', state.group_count || 0);
        setText('dup-count', state.duplicate_count || 0);
        setText('dup-purged', state.purged || 0);
        setText('dup-elapsed', state.elapsed || '0s');
        setText('dup-current', status === 'running' ? 'Scanning movies and episodes…' : status === 'completed' ? 'Duplicate check complete' : status === 'error' ? (state.error || 'Duplicate check failed') : 'No duplicate scan running');
        const bar = document.getElementById('dup-bar');
        if (bar) bar.style.width = status === 'running' ? '72%' : ['completed', 'cancelled'].includes(status) ? '100%' : '0%';
        const startBtn = document.getElementById('dup-start-btn');
        const cancelBtn = document.getElementById('dup-cancel-btn');
        if (startBtn) startBtn.disabled = status === 'running' || state.purge_running;
        if (cancelBtn) cancelBtn.disabled = status !== 'running';

        const cleanup = document.getElementById('dup-cleanup');
        const purgeActive = state.purge_status && state.purge_status !== 'idle';
        cleanup?.classList.toggle('hidden', !purgeActive);
        if (purgeActive) {
            setText('dup-cleanup-copy', state.purge_status === 'running' ? 'Removing duplicate Telegram files…' : state.purge_status === 'completed' ? 'Cleanup complete' : 'Cleanup failed');
            setText('dup-cleanup-meta', `${state.purge_done || 0} / ${state.purge_total || 0} · ETA ${state.purge_eta || '—'}`);
            const cleanupBar = document.getElementById('dup-cleanup-bar');
            if (cleanupBar) cleanupBar.style.width = `${state.purge_progress || 0}%`;
        }

        if (status !== 'running' && state.purge_status !== 'running') {
            renderDuplicateGroups(state.groups || []);
            if (dupTimer) { clearInterval(dupTimer); dupTimer = null; }
        } else {
            syncDuplicateButtons();
        }
    } catch (_) {
        // Keep the last useful state visible during a transient poll failure.
    }
}

async function purgeDuplicatePayload(payload, title, message) {
    const confirmed = await confirmAction({ title, subtitle: 'Telegram source posts will also be deleted.', message, confirmText: 'Remove duplicates', tone: 'danger' });
    if (!confirmed) return;
    try {
        const response = await fetch('/api/admin/tools/duplicates/purge', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || data.message || 'Cleanup could not start.');
        showToast(data.message || 'Duplicate cleanup started.', 'info', 'Duplicates');
        startDuplicatePolling();
        await pollDuplicates();
    } catch (error) {
        showToast(error.message || 'Duplicate cleanup failed.', 'error', 'Duplicates');
    }
}

function purgeSelectedDuplicates() {
    const ids = selectedDuplicateIds();
    if (!ids.length) return;
    return purgeDuplicatePayload({ stream_ids: ids }, 'Remove selected duplicates', `Remove ${ids.length} selected duplicate stream${ids.length === 1 ? '' : 's'}?`);
}

function purgeAllDuplicates() {
    return purgeDuplicatePayload({ delete_all: true }, 'Keep newest copies', 'For every duplicate group, keep the newest indexed copy and remove all older copies?');
}

/* ─────────────── Bot Admin Manager ─────────────── */
let botAdminData = null;
let botAdminTimer = null;

function setBotAdminPill(text, state = 'idle') {
    const pill = document.getElementById('ba-status-pill');
    if (!pill) return;
    pill.textContent = text;
    pill.className = `status-pill ${state === 'running' ? 'status-running' : state === 'error' ? 'status-error' : 'status-idle'}`;
}

function selectAllBotAdminBots(checked) {
    document.querySelectorAll('.ba-bot-check').forEach(input => { input.checked = checked; onChipChange(input); });
}
function selectAllBotAdminChannels(checked) {
    document.querySelectorAll('.ba-channel-check:not(:disabled)').forEach(input => { input.checked = checked; input.closest('.bot-admin-channel')?.classList.toggle('selected', checked); });
}

function renderBotAdminScan(data) {
    botAdminData = data;
    const bots = data.bots || [];
    const channels = data.channels || [];
    document.getElementById('ba-picker')?.classList.remove('hidden');
    const botBox = document.getElementById('ba-bots');
    botBox.innerHTML = bots.map(bot => `<label class="channel-chip selected"><input class="ba-bot-check" type="checkbox" value="${bot.user_id}" checked onchange="onChipChange(this)"><span class="channel-check"><i class="fa-solid fa-check"></i></span><span class="channel-copy"><strong>${escapeHtml(bot.name || bot.username || 'Bot')}</strong><small>${bot.username ? '@' + escapeHtml(bot.username) : bot.user_id}${bot.is_main ? ' · Main' : ''}</small></span></label>`).join('');

    const channelBox = document.getElementById('ba-channels');
    channelBox.innerHTML = channels.length ? channels.map(channel => {
        const statuses = bots.map(bot => `${escapeHtml(bot.name || bot.username || 'Bot')}: ${escapeHtml(channel.bots?.[String(bot.user_id)] || 'missing')}`).join(' · ');
        const disabled = !channel.manageable;
        return `<label class="bot-admin-channel ${channel.manageable ? 'selected' : 'is-blocked'}">
            <input class="ba-channel-check" type="checkbox" value="${escapeHtmlAttr(channel.id)}" ${disabled ? 'disabled' : 'checked'} onchange="this.closest('.bot-admin-channel').classList.toggle('selected', this.checked)">
            <span class="channel-check"><i class="fa-solid fa-check"></i></span>
            <span class="bot-admin-channel-copy"><strong>${escapeHtml(channel.name || channel.id)}</strong><small>${escapeHtml((channel.roles || []).join(', ') || 'channel')} · ${statuses}</small>${channel.reason ? `<em>${escapeHtml(channel.reason)}</em>` : ''}</span>
            <span class="admin-access-state ${channel.manageable ? 'is-ready' : 'is-blocked'}">${channel.manageable ? 'Ready' : 'Blocked'}</span>
        </label>`;
    }).join('') : `<div class="dead-empty"><i class="fa-solid fa-circle-exclamation"></i><span>No configured service channels were found.</span></div>`;
    document.getElementById('ba-apply-btn').disabled = !channels.some(channel => channel.manageable);
    renderBotAdminReport(channels.map(channel => ({ name: channel.name, items: [{ status: channel.manageable ? 'ready' : 'skipped', bot: 'Session', message: channel.manageable ? 'Can add admins.' : (channel.reason || 'Cannot manage this channel.') }] })));
}

async function scanBotAdmins() {
    const button = document.getElementById('ba-scan-btn');
    if (button) button.disabled = true;
    setBotAdminPill('Scanning', 'running');
    try {
        const response = await fetch('/api/admin/tools/bot-admin/scan');
        const data = await response.json();
        if (!response.ok || data.status !== 'success') throw new Error(data.message || data.detail || 'Bot admin scan failed.');
        renderBotAdminScan(data.data || {});
        setBotAdminPill('Ready');
        showToast('Channel administrator access scanned.', 'success', 'Bot Admin');
    } catch (error) {
        setBotAdminPill('Unavailable', 'error');
        document.getElementById('ba-report').innerHTML = `<div class="dead-empty" style="color:var(--danger)"><i class="fa-solid fa-triangle-exclamation"></i><span>${escapeHtml(error.message || 'Bot Admin Manager is unavailable.')}</span></div>`;
        showToast(error.message || 'Bot Admin Manager is unavailable.', 'error', 'Bot Admin');
    } finally {
        if (button) button.disabled = false;
    }
}

async function applyBotAdmins() {
    const channelIds = [...document.querySelectorAll('.ba-channel-check:checked')].map(input => input.value);
    const botIds = [...document.querySelectorAll('.ba-bot-check:checked')].map(input => input.value);
    if (!channelIds.length) return showToast('Select at least one manageable channel.', 'error', 'Bot Admin');
    if (!botIds.length) return showToast('Select at least one bot.', 'error', 'Bot Admin');
    const confirmed = await confirmAction({ title: 'Add bot administrators', subtitle: 'Telegram permissions will be changed.', message: `Add ${botIds.length} bot${botIds.length === 1 ? '' : 's'} as admins in ${channelIds.length} channel${channelIds.length === 1 ? '' : 's'}?`, confirmText: 'Apply permissions', tone: 'primary' });
    if (!confirmed) return;
    try {
        const response = await fetch('/api/admin/tools/bot-admin/apply', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_ids: channelIds, bot_ids: botIds, demote_orphans: document.getElementById('ba-demote-orphans')?.checked })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || data.message || 'Could not apply bot administrators.');
        setBotAdminPill('Applying', 'running');
        document.getElementById('ba-progress')?.classList.remove('hidden');
        document.getElementById('ba-apply-btn').disabled = true;
        startBotAdminPolling();
    } catch (error) {
        showToast(error.message || 'Could not apply bot administrators.', 'error', 'Bot Admin');
    }
}

function startBotAdminPolling() {
    if (botAdminTimer) clearInterval(botAdminTimer);
    botAdminTimer = setInterval(pollBotAdminApply, 1000);
    pollBotAdminApply();
}

async function pollBotAdminApply() {
    try {
        const response = await fetch('/api/admin/tools/bot-admin/apply/status');
        const payload = await response.json();
        const state = payload.data || {};
        const total = Number(state.total || 0);
        const done = Number(state.done || 0);
        const progress = total ? Math.round(done / total * 100) : 0;
        setText('ba-progress-meta', `${done} / ${total}`);
        const bar = document.getElementById('ba-progress-bar');
        if (bar) bar.style.width = `${progress}%`;
        renderBotAdminReport(state.results || []);
        if (!state.running && state.state !== 'idle') {
            if (botAdminTimer) { clearInterval(botAdminTimer); botAdminTimer = null; }
            setBotAdminPill(state.state === 'completed' ? 'Complete' : 'Error', state.state === 'completed' ? 'idle' : 'error');
            setText('ba-progress-copy', state.state === 'completed' ? 'Permission update complete' : (state.error || 'Permission update failed'));
            document.getElementById('ba-apply-btn').disabled = false;
            showToast(state.state === 'completed' ? 'Bot administrator permissions updated.' : (state.error || 'Bot Admin update failed.'), state.state === 'completed' ? 'success' : 'error', 'Bot Admin');
        }
    } catch (_) {}
}

function renderBotAdminReport(results) {
    const report = document.getElementById('ba-report');
    if (!report) return;
    if (!results?.length) {
        report.innerHTML = `<div class="dead-empty"><i class="fa-solid fa-user-shield"></i><span>No report yet.</span></div>`;
        return;
    }
    report.innerHTML = results.map(channel => `<article class="bot-admin-result"><header><strong>${escapeHtml(channel.name || channel.id || 'Channel')}</strong></header><div>${(channel.items || []).map(item => `<p class="ba-result-${escapeHtmlAttr(item.status || 'ready')}"><i class="fa-solid ${['added','already','ready'].includes(item.status) ? 'fa-circle-check' : item.status === 'error' ? 'fa-circle-xmark' : 'fa-circle-info'}"></i><span><strong>${escapeHtml(item.bot || 'Bot')}</strong> · ${escapeHtml(item.message || item.status || '')}</span></p>`).join('')}</div></article>`).join('');
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
pollDuplicates().then(() => {
    const pill = document.getElementById('dup-status-pill');
    if (pill?.classList.contains('status-running')) startDuplicatePolling();
});
pollBotAdminApply().then(() => {
    const pill = document.getElementById('ba-status-pill');
    if (pill?.classList.contains('status-running')) startBotAdminPolling();
});

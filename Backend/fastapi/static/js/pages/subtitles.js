/* Page behavior: subtitles */
let currentPage = 1;
let currentRows = [];
let currentLink = null;
let languageLabels = {};

function openLinkModal() {
    const shell = document.getElementById('link-dialog');
    if (!shell) return;
    shell.classList.remove('hidden');
    shell.classList.add('is-open');
    shell.setAttribute('aria-hidden', 'false');
    document.body.classList.add('overflow-hidden');
}

function closeLinkDialog() {
    const shell = document.getElementById('link-dialog');
    if (!shell) return;
    shell.classList.add('hidden');
    shell.classList.remove('is-open');
    shell.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('overflow-hidden');
}
window.closeLinkDialog = closeLinkDialog;
const PAGE_SIZE = 50;

function esc(value) {
    return String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}
function setLoading(loading) { document.getElementById('loading').classList.toggle('hidden', !loading); }
function requestOptions(method = 'GET', body = null) {
    const options = { method, credentials: 'same-origin', headers: { 'Accept':'application/json' } };
    if (body !== null) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
    return options;
}
function syncSubtitleChoice(selectId, triggerId, fallback = 'Select') {
    const select = document.getElementById(selectId);
    const trigger = document.getElementById(triggerId);
    if (!select || !trigger) return;
    const option = select.options[select.selectedIndex];
    trigger.querySelector('span').textContent = option ? option.textContent : fallback;
}
async function openSubtitleChoice(selectId, title) {
    const select = document.getElementById(selectId);
    if (!select || typeof showChoiceDialog !== 'function') return;
    const chosen = await showChoiceDialog({
        title,
        subtitle: 'Pick one option below.',
        value: select.value,
        options: Array.from(select.options).map(option => ({ value: option.value, label: option.textContent }))
    });
    if (chosen === null) return;
    select.value = chosen;
    syncSubtitleChoice(selectId, `${selectId}-trigger`);
    select.dispatchEvent(new Event('change', { bubbles: true }));
}
function subtitleLanguageOptions(selected = 'und') {
    const values = Object.entries(languageLabels).sort((a,b) => a[1].localeCompare(b[1]));
    if (!languageLabels.und) values.unshift(['und','Unknown']);
    return values.map(([code, name]) => `<option value="${esc(code)}" ${code === selected ? 'selected' : ''}>${esc(name)} (${esc(code)})</option>`).join('');
}

async function loadStats() {
    const response = await fetch('/api/subtitles/stats', requestOptions());
    if (!response.ok) throw new Error('Unable to load subtitle statistics.');
    const stats = await response.json();
    languageLabels = stats.language_labels || {};
    document.getElementById('total-stat').textContent = stats.total ?? 0;
    document.getElementById('matched-stat').textContent = stats.matched ?? 0;
    document.getElementById('unmatched-stat').textContent = stats.unmatched ?? 0;
    const select = document.getElementById('language-filter');
    const selected = select.value;
    select.innerHTML = '<option value="">All languages</option>' + subtitleLanguageOptions('___none___');
    select.value = selected;
    document.getElementById('link-language').innerHTML = subtitleLanguageOptions('und');
    syncSubtitleChoice('language-filter', 'language-filter-trigger', 'All languages');
    syncSubtitleChoice('link-language', 'link-language-trigger', 'Unknown (und)');
}

function mediaText(row) {
    const media = row.media || {};
    if (!media.imdb_id) return `<span class="text-muted">Not linked</span>`;
    const episode = media.season != null && media.episode != null ? ` · S${String(media.season).padStart(2,'0')}E${String(media.episode).padStart(2,'0')}` : '';
    return `<span class="linked-title">${esc(media.title || 'Linked media')}${episode}</span><span>${esc(media.imdb_id || '')}</span>`;
}

function subtitleCard(row, index) {
    const matched = row.status === 'matched';
    const caption = row.caption ? `<p class="subtitle-record-caption">${esc(row.caption)}</p>` : '';
    const filename = esc(row.filename || 'Untitled subtitle');
    const status = matched ? 'READY' : 'REVIEW';
    return `<article class="subtitle-record ${matched ? 'ready' : 'review'}">
      <div class="subtitle-record-head">
        <span class="subtitle-type-icon"><i class="fa-solid fa-closed-captioning"></i></span>
        <div class="subtitle-record-title"><strong title="${filename}">${filename}</strong><small>${esc(row.caption || row.detected?.title || 'Telegram subtitle document')}</small></div>
        <span class="subtitle-state status-pill ${matched ? 'status-live' : 'status-warning'}">${status}</span>
      </div>
      ${caption}
      <div class="subtitle-details">
        <div class="subtitle-detail"><label>Language</label><p>${esc(row.language_name || 'Unknown')} <span>${esc(row.language_code || 'und')}</span></p></div>
        <div class="subtitle-detail"><label>Linked media</label><p>${mediaText(row)}</p></div>
      </div>
      <div class="subtitle-actions">
        <button onclick="openLinkDialog(${index})" class="subtitle-link"><i class="fa-solid fa-link"></i>${matched ? 'Edit link' : 'Link media'}</button>
        ${matched ? `<button onclick="unlinkSubtitle(${index})" class="subtitle-unlink"><i class="fa-solid fa-link-slash"></i>Unlink</button>` : ''}
        <button onclick="removeSubtitle(${index})" class="subtitle-remove"><i class="fa-solid fa-trash"></i>Remove</button>
      </div>
    </article>`;
}

async function loadSubtitles(page = currentPage) {
    currentPage = page;
    syncSubtitleChoice('status-filter', 'status-filter-trigger', 'All status');
    syncSubtitleChoice('language-filter', 'language-filter-trigger', 'All languages');
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    const search = document.getElementById('search-input').value.trim();
    const status = document.getElementById('status-filter').value;
    const language = document.getElementById('language-filter').value;
    if (search) params.set('search', search);
    if (status !== 'all') params.set('status', status);
    if (language) params.set('language', language);
    try {
        const response = await fetch(`/api/subtitles?${params}`, requestOptions());
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'Unable to load subtitles.');
        currentRows = data.subtitles || [];
        const list = document.getElementById('subtitle-list');
        list.innerHTML = currentRows.map(subtitleCard).join('');
        document.getElementById('empty').classList.toggle('hidden', currentRows.length !== 0);
        renderPagination(data.current_page || 1, data.total_pages || 0);
    } catch (error) {
        showToast(error.message, 'error', 'Subtitle Manager');
    } finally { setLoading(false); }
}

function renderPagination(page, totalPages) {
    const wrapper = document.getElementById('pagination');
    const inner = document.getElementById('pagination-inner');
    if (totalPages <= 1) { wrapper.classList.add('hidden'); inner.innerHTML = ''; return; }
    wrapper.classList.remove('hidden');
    const buttons = [];
    const button = (label, target, active = false) => `<button onclick="loadSubtitles(${target})" class="${active ? 'btn-primary' : 'btn-ghost'}">${label}</button>`;
    if (page > 1) buttons.push(button('<i class="fa-solid fa-chevron-left"></i>', page - 1));
    for (let n = Math.max(1, page - 2); n <= Math.min(totalPages, page + 2); n++) buttons.push(button(n, n, n === page));
    if (page < totalPages) buttons.push(button('<i class="fa-solid fa-chevron-right"></i>', page + 1));
    inner.innerHTML = buttons.join('');
}

function manualLinkTitle(row) {
    const media = row.media || {};
    const detected = row.detected || {};
    const title = media.title || detected.title || '';
    const season = media.season ?? detected.season;
    const episode = media.episode ?? detected.episode;
    const episodeLabel = season != null && episode != null
        ? ` · S${String(season).padStart(2, '0')}E${String(episode).padStart(2, '0')}`
        : '';
    return title ? `Link to ${title}${episodeLabel}` : 'Link subtitle';
}

function openLinkDialog(index) {
    currentLink = currentRows[index];
    document.getElementById('link-dialog-title').textContent = manualLinkTitle(currentLink);
    document.getElementById('link-dialog-file').textContent = currentLink.filename || '';
    document.getElementById('link-imdb').value = currentLink.media?.imdb_id || currentLink.detected?.imdb_id || '';
    document.getElementById('link-season').value = currentLink.media?.season ?? currentLink.detected?.season ?? '';
    document.getElementById('link-episode').value = currentLink.media?.episode ?? currentLink.detected?.episode ?? '';
    document.getElementById('link-language').innerHTML = subtitleLanguageOptions(currentLink.language_code || 'und');
    syncSubtitleChoice('link-language', 'link-language-trigger', 'Unknown (und)');
    openLinkModal();
}

async function saveManualLink() {
    if (!currentLink) return;
    const imdb_id = document.getElementById('link-imdb').value.trim();
    if (!imdb_id) { showToast('Enter the IMDb ID of media already indexed in the library.', 'error', 'IMDb ID needed'); return; }
    const seasonText = document.getElementById('link-season').value;
    const episodeText = document.getElementById('link-episode').value;
    const payload = {
        imdb_id,
        language_code: document.getElementById('link-language').value,
        season: seasonText === '' ? null : Number(seasonText),
        episode: episodeText === '' ? null : Number(episodeText),
    };
    try {
        const response = await fetch(`/api/subtitles/${encodeURIComponent(currentLink._id)}?db_index=${encodeURIComponent(currentLink.db_index)}`, requestOptions('PUT', payload));
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'Unable to update subtitle.');
        closeLinkDialog();
        showToast(data.message || 'Subtitle linked.', 'success', 'Saved');
        await Promise.all([loadStats(), loadSubtitles(currentPage)]);
    } catch (error) { showToast(error.message, 'error', 'Link failed'); }
}

async function unlinkSubtitle(index) {
    const row = currentRows[index];
    const ok = typeof showConfirmDialog === 'function'
        ? await showConfirmDialog({
            title: 'Unlink subtitle',
            subtitle: 'The subtitle record stays indexed, but it will no longer point to the linked media.',
            message: `Unlink ${row.filename}?`,
            confirmText: 'Unlink',
            tone: 'primary'
          })
        : false;
    if (!ok) return;
    try {
        const response = await fetch(`/api/subtitles/${encodeURIComponent(row._id)}?db_index=${encodeURIComponent(row.db_index)}`, requestOptions('PUT', {unlink:true}));
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'Unable to unlink subtitle.');
        showToast('Subtitle unlinked.', 'success', 'Updated');
        await Promise.all([loadStats(), loadSubtitles(currentPage)]);
    } catch (error) { showToast(error.message, 'error', 'Unlink failed'); }
}

async function removeSubtitle(index) {
    const row = currentRows[index];
    const ok = typeof showConfirmDialog === 'function'
        ? await showConfirmDialog({
            title: 'Remove subtitle record',
            subtitle: 'This clears only the subtitle index entry from TG Stremio.',
            message: `Remove the index record for ${row.filename}?`,
            note: 'The Telegram file will not be deleted.',
            confirmText: 'Remove record',
            tone: 'danger'
          })
        : false;
    if (!ok) return;
    try {
        const response = await fetch(`/api/subtitles/${encodeURIComponent(row._id)}?db_index=${encodeURIComponent(row.db_index)}`, requestOptions('DELETE'));
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'Unable to remove subtitle.');
        showToast(data.message || 'Subtitle removed.', 'success', 'Removed');
        await Promise.all([loadStats(), loadSubtitles(currentPage)]);
    } catch (error) { showToast(error.message, 'error', 'Remove failed'); }
}

async function relinkSubtitles() {
    try {
        const response = await fetch('/api/subtitles/relink', requestOptions('POST', {limit:500}));
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'Unable to re-link subtitles.');
        showToast(data.message, 'success', 'Matching complete');
        await Promise.all([loadStats(), loadSubtitles(1)]);
    } catch (error) { showToast(error.message, 'error', 'Re-link failed'); }
}

document.addEventListener('DOMContentLoaded', async () => {
    syncSubtitleChoice('status-filter', 'status-filter-trigger', 'All status');
    syncSubtitleChoice('language-filter', 'language-filter-trigger', 'All languages');
    document.getElementById('status-filter').addEventListener('change', () => syncSubtitleChoice('status-filter', 'status-filter-trigger', 'All status'));
    document.getElementById('language-filter').addEventListener('change', () => syncSubtitleChoice('language-filter', 'language-filter-trigger', 'All languages'));
    document.getElementById('link-language').addEventListener('change', () => syncSubtitleChoice('link-language', 'link-language-trigger', 'Unknown (und)'));
    try { await loadStats(); await loadSubtitles(1); }
    catch (error) { showToast(error.message, 'error', 'Subtitle Manager'); }
    document.getElementById('search-input').addEventListener('keydown', event => { if (event.key === 'Enter') loadSubtitles(1); });
    const linkDialog = document.getElementById('link-dialog');
    linkDialog?.addEventListener('click', (event) => {
        if (event.target === linkDialog) closeLinkDialog();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && linkDialog?.classList.contains('is-open')) closeLinkDialog();
    });
});

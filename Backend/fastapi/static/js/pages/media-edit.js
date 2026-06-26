/* Page behavior: media-edit */
const tmdbId = window.TG_STREMIO_PAGE.tmdbId;
    const dbIndex = window.TG_STREMIO_PAGE.dbIndex;
    const mediaType = window.TG_STREMIO_PAGE.mediaType;

    let selectedRescanMatch = null;
    let latestRescanResults = [];

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function setRescanState(message = '', visible = false) {
        const el = document.getElementById('rescan-state');
        if (!el) return;
        el.textContent = message;
        el.classList.toggle('hidden', !visible);
    }

    function clearRescanSelection() {
        selectedRescanMatch = null;
        document.querySelectorAll('.match-card').forEach(card => card.classList.remove('active'));
        const preview = document.getElementById('rescan-preview');
        if (preview) preview.classList.add('hidden');
    }

    function selectRescanMatch(index) {
        const item = latestRescanResults[index];
        if (!item) return;

        selectedRescanMatch = item;
        document.querySelectorAll('.match-card').forEach(card => card.classList.remove('active'));
        const activeCard = document.getElementById(`match-card-${index}`);
        if (activeCard) activeCard.classList.add('active');

        document.getElementById('rescan-preview-title').textContent = item.title || 'Unknown title';
        document.getElementById('rescan-preview-subtitle').textContent = `${item.subtitle || 'Match'}${item.year ? ` • ${item.year}` : ''}`;
        document.getElementById('rescan-preview-ids').textContent = `IMDb: ${item.imdb_id || 'N/A'} • TMDb: ${item.tmdb_id || 'N/A'}`;
        document.getElementById('rescan-preview-poster').src = item.poster || '/static/placeholder.svg';
        document.getElementById('rescan-preview').classList.remove('hidden');
    }

    async function searchRescanCandidates() {
        const query = document.getElementById('rescan-query').value.trim();
        const resultsEl = document.getElementById('rescan-results');

        if (!query) {
            showErrorMessage('Please enter a title to search.');
            return;
        }

        clearRescanSelection();
        latestRescanResults = [];
        resultsEl.innerHTML = '';
        setRescanState('Searching matches...', true);

        try {
            const params = new URLSearchParams({
                media_type: mediaType,
                query
            });

            const yearValue = document.getElementById('release_year')?.value;
            if (yearValue) {
                params.set('year', yearValue);
            }

            const response = await fetch(`/api/media/rescan/search?${params.toString()}`);
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                setRescanState('', false);
                showErrorMessage(data.detail || 'Failed to search matches.');
                return;
            }

            const results = data.results || [];
            latestRescanResults = results;

            if (!results.length) {
                setRescanState('No matches found.', true);
                return;
            }

            setRescanState(`Found ${results.length} match${results.length > 1 ? 'es' : ''}. Select one below.`, true);

            resultsEl.innerHTML = results.map((item, index) => `
                <button
                    type="button"
                    id="match-card-${index}"
                    class="match-card text-left w-full"
                    data-index="${index}"
                >
                    <div class="flex items-start gap-4">
                        <img
                            src="${item.poster || '/static/placeholder.svg'}"
                            alt="${escapeHtml(item.title || 'Poster')}"
                            class="match-thumb"
                            onerror="this.src='/static/placeholder.svg'"
                        >
                        <div class="min-w-0 flex-1">
                            <div class="flex flex-wrap items-center gap-2">
                                <h4 class="text-white font-bold text-base sm:text-lg">${escapeHtml(item.title || 'Unknown title')}</h4>
                                <span class="pill">${escapeHtml(item.year || '—')}</span>
                            </div>
                            <p class="muted text-sm mt-2">${escapeHtml(item.subtitle || '')}</p>
                            <p class="muted text-xs mt-2 break-all">
                                IMDb: ${escapeHtml(item.imdb_id || 'N/A')} · TMDb: ${escapeHtml(item.tmdb_id || 'N/A')}
                            </p>
                        </div>
                    </div>
                </button>
            `).join('');

            document.querySelectorAll('#rescan-results .match-card').forEach((card) => {
                card.addEventListener('click', () => {
                    const index = Number(card.dataset.index);
                    selectRescanMatch(index);
                });
            });
        } catch (error) {
            console.error('Rescan search failed:', error);
            setRescanState('', false);
            showErrorMessage('Failed to search matches. Please try again.');
        }
    }

    async function applyRescanSelection() {
        if (!selectedRescanMatch) {
            showErrorMessage('Please select a match first.');
            return;
        }
        const selectedId = selectedRescanMatch.tmdb_id || selectedRescanMatch.imdb_id;
        if (!selectedId) {
            showErrorMessage('Selected match does not contain a valid IMDb/TMDb id.');
            return;
        }

        const confirmed = await confirmAction({ title: 'Replace metadata', subtitle: 'Telegram files remain safe.', message: `Replace current metadata with “${selectedRescanMatch.title}”?`, confirmText: 'Replace metadata', tone: 'primary' });
        if (!confirmed) return;

        try {
            const response = await fetch(`/api/media/rescan/apply?tmdb_id=${tmdbId}&db_index=${dbIndex}&media_type=${mediaType}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ selected_id: String(selectedId) })
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                showErrorMessage(data.detail || 'Failed to apply selected metadata.');
                return;
            }

            showSuccessMessage(data.message || 'Metadata rescanned successfully.');

            const newTmdbId = data.redirect_tmdb_id || tmdbId;
            const newDbIndex = data.db_index || dbIndex;

            setTimeout(() => {
                window.location.href = `/media/edit?tmdb_id=${newTmdbId}&db_index=${newDbIndex}&media_type=${mediaType}`;
            }, 700);
        } catch (error) {
            console.error('Apply rescan failed:', error);
            showErrorMessage('Failed to apply selected metadata. Please try again.');
        }
    }

    function toggleSeason(seasonIndex) {
        const content = document.getElementById(`season-content-${seasonIndex}`);
        const arrow = document.getElementById(`season-arrow-${seasonIndex}`);
        if (!content || !arrow) return;

        const collapsed = content.classList.contains('season-collapsed');
        if (collapsed) {
            content.classList.remove('season-collapsed');
            arrow.style.transform = 'rotate(0deg)';
            requestAnimationFrame(() => {
                content.style.maxHeight = content.scrollHeight + 'px';
                content.style.opacity = '1';
            });
        } else {
            content.style.maxHeight = content.scrollHeight + 'px';
            requestAnimationFrame(() => {
                content.classList.add('season-collapsed');
                content.style.maxHeight = '0px';
                content.style.opacity = '0';
                arrow.style.transform = 'rotate(-90deg)';
            });
        }
    }

    async function updateMedia(event) {
        event.preventDefault();

        const formData = new FormData(event.target);
        const updateData = {};

        for (let [key, value] of formData.entries()) {
            if (key === 'genres') {
                updateData[key] = value.split(',').map(g => g.trim()).filter(Boolean);
            } else if (key === 'rating' || key === 'release_year' || key === 'runtime') {
                updateData[key] = value ? parseFloat(value) : null;
            } else {
                updateData[key] = value || null;
            }
        }

        try {
            const response = await fetch(`/api/media/update?tmdb_id=${tmdbId}&db_index=${dbIndex}&media_type=${mediaType}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updateData)
            });

            if (response.ok) {
                showSuccessMessage('Media updated successfully');
                setTimeout(() => location.reload(), 900);
            } else {
                const error = await response.json().catch(() => ({}));
                showErrorMessage(`Error updating media: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error updating media:', error);
            showErrorMessage('Error updating media. Please try again.');
        }
    }

    async function deleteQuality(id) {
        const confirmed = await confirmAction({ title: 'Delete quality', subtitle: 'This quality will no longer appear in Stremio.', message: `Delete ${id}?`, confirmText: 'Delete quality', tone: 'danger' });
        if (!confirmed) return;

        try {
            const response = await fetch(`/api/media/delete-quality?tmdb_id=${tmdbId}&db_index=${dbIndex}&id=${encodeURIComponent(id)}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                showSuccessMessage(`${id} deleted successfully`);
                setTimeout(() => location.reload(), 900);
            } else {
                const error = await response.json().catch(() => ({}));
                showErrorMessage(`Error deleting: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error deleting:', error);
            showErrorMessage('Error deleting. Please try again.');
        }
    }

    async function deleteTVQuality(season, episode, id) {
        const confirmed = await confirmAction({ title: 'Delete episode quality', subtitle: 'This quality will no longer appear in Stremio.', message: `Delete ${id} from Season ${season}, Episode ${episode}?`, confirmText: 'Delete quality', tone: 'danger' });
        if (!confirmed) return;

        try {
            const response = await fetch(`/api/media/delete-tv-quality?tmdb_id=${tmdbId}&db_index=${dbIndex}&season=${season}&episode=${episode}&id=${encodeURIComponent(id)}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                showSuccessMessage(`${id} deleted successfully`);
                setTimeout(() => location.reload(), 900);
            } else {
                const error = await response.json().catch(() => ({}));
                showErrorMessage(`Error deleting: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error deleting:', error);
            showErrorMessage('Error deleting. Please try again.');
        }
    }

    async function deleteTVEpisode(season, episode) {
        const confirmed = await confirmAction({ title: 'Delete episode', subtitle: 'All qualities in this episode will be removed.', message: `Delete Season ${season}, Episode ${episode}?`, confirmText: 'Delete episode', tone: 'danger' });
        if (!confirmed) return;

        try {
            const response = await fetch(`/api/media/delete-tv-episode?tmdb_id=${tmdbId}&db_index=${dbIndex}&season=${season}&episode=${episode}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                showSuccessMessage(`Episode ${episode} deleted successfully`);
                setTimeout(() => location.reload(), 900);
            } else {
                const error = await response.json().catch(() => ({}));
                showErrorMessage(`Error deleting episode: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error deleting episode:', error);
            showErrorMessage('Error deleting episode. Please try again.');
        }
    }

    async function deleteTVSeason(season) {
        const confirmed = await confirmAction({ title: 'Delete season', subtitle: 'This cannot be undone.', message: `Delete the entire Season ${season}?`, confirmText: 'Delete season', tone: 'danger' });
        if (!confirmed) return;

        try {
            const response = await fetch(`/api/media/delete-tv-season?tmdb_id=${tmdbId}&db_index=${dbIndex}&season=${season}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                showSuccessMessage(`Season ${season} deleted successfully`);
                setTimeout(() => location.reload(), 900);
            } else {
                const error = await response.json().catch(() => ({}));
                showErrorMessage(`Error deleting season: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error deleting season:', error);
            showErrorMessage('Error deleting season. Please try again.');
        }
    }

    function showSuccessMessage(message) {
        showToast(message, 'success', 'Success');
    }

    function showErrorMessage(message) {
        showToast(message, 'error', 'Error');
    }

    function copyStreamLink(qualityId, fileName) {
        const base = window.location.origin;
        const token = getCopylinkToken();

        if (!token) {
            showErrorMessage('No API token found. Please create an API token on the Dashboard page first.');
            return;
        }

        const encodedName = encodeURIComponent(fileName || 'stream');
        const url = `${base}/dl/${token}/${qualityId}/${encodedName}`;

        navigator.clipboard.writeText(url).then(() => {
            showSuccessMessage('Stream link copied to clipboard!');
        }).catch(() => {
            prompt('Copy this stream link:', url);
        });
    }

    function getCopylinkToken() {
        const serverToken = window.TG_STREMIO_PAGE.apiToken;
        return serverToken || sessionStorage.getItem('api_token') || localStorage.getItem('api_token') || null;
    }


    const CURRENT_TMDB_ID = window.TG_STREMIO_PAGE.tmdbId;
    const CURRENT_DB_INDEX = window.TG_STREMIO_PAGE.dbIndex;
    const CURRENT_MEDIA_TYPE = window.TG_STREMIO_PAGE.mediaType;

    function setCatalogStatus(message, type = 'info') {
        const status = document.getElementById('custom-catalog-status');
        if (!status) return;
        status.textContent = message;
        status.classList.remove('text-emerald-300', 'text-rose-300', 'text-amber-300');
        if (type === 'success') status.classList.add('text-emerald-300');
        if (type === 'error') status.classList.add('text-rose-300');
        if (type === 'warn') status.classList.add('text-amber-300');
    }

    async function loadMediaCatalogDropdown(selectedCatalogId = '') {
        const select = document.getElementById('custom-catalog-select');
        if (!select) return;

        select.disabled = true;
        select.innerHTML = '<option value="">Loading catalogs...</option>';
        setCatalogStatus('Loading custom catalogs...');

        try {
            const params = new URLSearchParams({
                tmdb_id: String(CURRENT_TMDB_ID),
                db_index: String(CURRENT_DB_INDEX),
                media_type: CURRENT_MEDIA_TYPE
            });
            const res = await fetch(`/api/custom-catalogs?${params.toString()}`);
            const data = await res.json().catch(() => ({}));

            if (!res.ok) {
                throw new Error(data.detail || 'Failed to load catalogs');
            }

            const catalogs = data.catalogs || [];
            if (!catalogs.length) {
                select.innerHTML = '<option value="">No custom catalog found</option>';
                setCatalogStatus('Create a catalog first from Manage Catalogs.', 'warn');
                return;
            }

            select.innerHTML = catalogs.map(catalog => {
                const visibility = catalog.visible ? 'Visible' : 'Hidden';
                const added = catalog.contains_current ? ' · Added' : '';
                return `<option value="${escapeHtml(catalog._id)}" data-visible="${catalog.visible ? '1' : '0'}" data-added="${catalog.contains_current ? '1' : '0'}">${escapeHtml(catalog.name)} (${visibility}${added})</option>`;
            }).join('');

            if (selectedCatalogId && catalogs.some(c => c._id === selectedCatalogId)) {
                select.value = selectedCatalogId;
            }

            select.disabled = false;
            updateCatalogDropdownStatus();
        } catch (error) {
            select.innerHTML = '<option value="">Failed to load catalogs</option>';
            setCatalogStatus(error.message || 'Failed to load custom catalogs.', 'error');
            showToast(error.message || 'Failed to load custom catalogs', 'error', 'Error');
        }
    }

    function updateCatalogDropdownStatus() {
        const select = document.getElementById('custom-catalog-select');
        if (!select || !select.value) return;

        const option = select.options[select.selectedIndex];
        const isVisible = option?.dataset.visible === '1';
        const isAdded = option?.dataset.added === '1';

        if (isAdded) {
            setCatalogStatus(`This title is already added to ${option.textContent.replace(' · Added', '')}.`, 'success');
        } else if (!isVisible) {
            setCatalogStatus('This catalog is hidden from Stremio main catalog screen, but you can still manage it here.', 'warn');
        } else {
            setCatalogStatus('This visible catalog will appear in Stremio main catalog screen.', 'info');
        }
    }

    async function addCurrentMediaToCatalog() {
        const select = document.getElementById('custom-catalog-select');
        const catalogId = select?.value;
        if (!catalogId) {
            showToast('Please select a catalog first.', 'error', 'Error');
            return;
        }

        try {
            const res = await fetch(`/api/custom-catalogs/${catalogId}/items`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    tmdb_id: CURRENT_TMDB_ID,
                    db_index: CURRENT_DB_INDEX,
                    media_type: CURRENT_MEDIA_TYPE
                })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Failed to add title to catalog');

            showToast(data.message || 'Added to catalog.', 'success', 'Success');
            await loadMediaCatalogDropdown(catalogId);
        } catch (error) {
            showToast(error.message || 'Failed to add title to catalog', 'error', 'Error');
            setCatalogStatus(error.message || 'Failed to add title to catalog.', 'error');
        }
    }

    async function removeCurrentMediaFromCatalog() {
        const select = document.getElementById('custom-catalog-select');
        const catalogId = select?.value;
        if (!catalogId) {
            showToast('Please select a catalog first.', 'error', 'Error');
            return;
        }

        try {
            const params = new URLSearchParams({
                tmdb_id: String(CURRENT_TMDB_ID),
                db_index: String(CURRENT_DB_INDEX),
                media_type: CURRENT_MEDIA_TYPE
            });
            const res = await fetch(`/api/custom-catalogs/${catalogId}/items?${params.toString()}`, {method: 'DELETE'});
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Failed to remove title from catalog');

            showToast(data.message || 'Removed from catalog.', data.removed === false ? 'info' : 'success', 'Done');
            await loadMediaCatalogDropdown(catalogId);
        } catch (error) {
            showToast(error.message || 'Failed to remove title from catalog', 'error', 'Error');
            setCatalogStatus(error.message || 'Failed to remove title from catalog.', 'error');
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const select = document.getElementById('custom-catalog-select');
        if (select) select.addEventListener('change', updateCatalogDropdownStatus);
        loadMediaCatalogDropdown();
        document.querySelectorAll('.season-content').forEach((content, index) => {
            if (index > 0) {
                content.classList.add('season-collapsed');
                content.style.maxHeight = '0px';
                content.style.opacity = '0';
                const arrow = document.getElementById(`season-arrow-${index}`);
                if (arrow) arrow.style.transform = 'rotate(-90deg)';
            } else {
                content.style.maxHeight = content.scrollHeight + 'px';
                content.style.opacity = '1';
            }
        });
    });

    let _stQualityId = null;
    let _stMediaType = null;
    let _stLabel = null;

    async function runSpeedTest(qualityId, mediaTypeArg, label) {
        _stQualityId = qualityId;
        _stMediaType = mediaTypeArg;
        _stLabel = label;
        _openModal(label);
        await _exec();
    }

    async function rerunSpeedTest() {
        if (!_stQualityId) return;
        _resetUI(_stLabel);
        await _exec();
    }

    function _openModal(label) {
        document.getElementById('speed-test-modal').classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        _resetUI(label);
    }

    function _resetUI(label) {
        document.getElementById('st-label').textContent = label ? `File: ${label}` : '';
        document.getElementById('st-spinner').classList.remove('hidden');
        document.getElementById('st-results').classList.add('hidden');
        document.getElementById('st-error').classList.add('hidden');
        document.getElementById('st-rerun-btn').classList.add('hidden');
        document.getElementById('st-tbody').innerHTML = '';
        document.getElementById('st-summary').textContent = '';
    }

    function closeSpeedTest() {
        document.getElementById('speed-test-modal').classList.add('hidden');
        document.body.style.overflow = '';
        if (window._stEventSource) {
            window._stEventSource.close();
            window._stEventSource = null;
        }
    }

    function _pingClass(ms) {
        if (ms === null) return 'speed-muted';
        if (ms < 100) return 'speed-good';
        if (ms < 300) return 'speed-warn';
        return 'speed-bad';
    }

    function _speedClass(mbps) {
        if (mbps === null) return 'speed-muted';
        if (mbps >= 20) return 'speed-good';
        if (mbps >= 5) return 'speed-warn';
        return 'speed-bad';
    }

    function _miniBar(value, max, state) {
        if (!value || !max) return '';
        const pct = Math.min(100, (value / max) * 100).toFixed(1);
        return `<span class="speed-meter"><span class="speed-meter-fill ${state}" style="width:${pct}%"></span></span>`;
    }

    async function _exec() {
        const params = new URLSearchParams({
            quality_id: _stQualityId,
            tmdb_id: tmdbId,
            db_index: dbIndex,
            media_type: _stMediaType || mediaType
        });

        if (window._stEventSource) {
            window._stEventSource.close();
            window._stEventSource = null;
        }

        let maxSpeed = 1;
        let completedCount = 0;
        let totalCount = 0;
        const allResults = [];
        const pendingRows = {};

        const es = new EventSource(`/api/system/speedtest/stream?${params}`);
        window._stEventSource = es;

        function updateSummary() {
            const best = allResults.filter(r => r.speed_mbps).sort((a, b) => b.speed_mbps - a.speed_mbps)[0];
            const summaryEl = document.getElementById('st-summary');
            if (!summaryEl) return;

            if (best) {
                summaryEl.textContent = `🏆 Fastest: DC ${best.dc_id} — ${best.speed_mbps.toFixed(2)} MB/s | ${completedCount}/${totalCount} client(s) done`;
            } else {
                summaryEl.textContent = `${completedCount}/${totalCount} client(s) done`;
            }
        }

        es.onmessage = (e) => {
            let msg;
            try { msg = JSON.parse(e.data); } catch { return; }

            if (msg.type === 'error') {
                es.close();
                document.getElementById('st-spinner').classList.add('hidden');
                document.getElementById('st-error').textContent = `Speed test stream error: ${msg.message}`;
                document.getElementById('st-error').classList.remove('hidden');
                document.getElementById('st-rerun-btn').classList.remove('hidden');
                showToast(msg.message || 'Speed test failed.', 'error', 'Speed Test Error');
                return;
            }

            if (msg.type === 'start') {
                totalCount = msg.total;
                document.getElementById('st-spinner').classList.add('hidden');
                document.getElementById('st-results').classList.remove('hidden');

                const labelEl = document.getElementById('st-label');
                if (msg.split_parts > 1) {
                    labelEl.textContent += ` | Split stream: sampled part ${msg.sample_part}/${msg.split_parts}`;
                }
                if (msg.target_dc && msg.target_dc !== "?") {
                    labelEl.innerHTML += ` &nbsp;|&nbsp; Target DC: <span class="target-dc">${msg.target_dc}</span>`;
                }

                const tbody = document.getElementById('st-tbody');
                tbody.innerHTML = '';
                for (let i = 0; i < totalCount; i++) {
                    const tr = document.createElement('tr');
                    tr.className = 'speed-pending';
                    tr.innerHTML = `
                        <td class="speed-client">⟳ Bot ${i + 1}</td>
                        <td><span class="speed-muted">Testing…</span></td>
                        <td><span class="speed-muted">Testing…</span></td>
                        <td class="speed-muted">—</td>
                        <td class="speed-muted">—</td>
                        <td><span class="speed-state speed-state-pending">Pending</span></td>`;
                    tbody.appendChild(tr);
                    pendingRows[i] = tr;
                }
                updateSummary();
            }

            if (msg.type === 'progress') {
                const r = msg.data;
                const tr = pendingRows[r.client_index];
                if (tr) {
                    maxSpeed = Math.max(maxSpeed, r.speed_mbps || 0, 1);
                    const isErr = !!r.error && !r.speed_mbps;
                    const medal = '';
                    const dc = `Bot ${r.client_index + 1} <span class="speed-dc">(DC ${r.dc_id})</span>`;
                    const ping = r.ping_ms !== null ? `<span class="${_pingClass(r.ping_ms)}">${r.ping_ms} ms</span>` : '<span class="speed-muted">—</span>';
                    const speed = r.speed_mbps !== null
                        ? `<span class="${_speedClass(r.speed_mbps)}">${r.speed_mbps.toFixed(2)} MB/s</span>
                           ${_miniBar(r.speed_mbps, maxSpeed, r.speed_mbps >= 20 ? 'is-fast' : r.speed_mbps >= 5 ? 'is-medium' : 'is-slow')}`
                        : '<span class="speed-muted">—</span>';
                    const taken = r.time_taken_sec !== null ? `${r.time_taken_sec.toFixed(2)}s` : '—';
                    const bytes = r.bytes_downloaded ? `${(r.bytes_downloaded / 1048576).toFixed(2)} MB` : '—';
                    const badge = isErr
                        ? `<span class="speed-state speed-state-error">Error</span>`
                        : `<span class="speed-state speed-state-ok">✓ OK</span>`;

                    const newTr = document.createElement('tr');
                    newTr.className = `speed-result-row ${isErr ? 'is-error' : ''}`;
                    newTr.innerHTML = `
                        <td class="speed-client">${medal}${dc}</td>
                        <td>${ping}</td>
                        <td>${speed}${isErr ? `<div class="speed-row-error">${r.error}</div>` : ''}</td>
                        <td class="speed-muted">${taken}</td>
                        <td class="speed-muted">${bytes}</td>
                        <td>${badge}</td>`;

                    if (pendingRows[r.client_index]) {
                        pendingRows[r.client_index].replaceWith(newTr);
                        delete pendingRows[r.client_index];
                    } else {
                        document.getElementById('st-tbody').appendChild(newTr);
                    }

                    allResults.push(r);
                    completedCount += 1;
                    updateSummary();
                }
            }

            if (msg.type === 'done') {
                es.close();
                window._stEventSource = null;

                allResults.sort((a, b) => (b.speed_mbps || 0) - (a.speed_mbps || 0));
                const tbody = document.getElementById('st-tbody');
                tbody.innerHTML = '';

                for (let i = 0; i < allResults.length; i++) {
                    const r = allResults[i];
                    const isErr = !!r.error && !r.speed_mbps;
                    const medal = i === 0 && !isErr ? '🥇 ' : '';
                    const dc = `Bot ${r.client_index + 1} <span class="speed-dc">(DC ${r.dc_id})</span>`;
                    const ping = r.ping_ms !== null ? `<span class="${_pingClass(r.ping_ms)}">${r.ping_ms} ms</span>` : '<span class="speed-muted">—</span>';
                    const speed = r.speed_mbps !== null
                        ? `<span class="${_speedClass(r.speed_mbps)}">${r.speed_mbps.toFixed(2)} MB/s</span>
                           ${_miniBar(r.speed_mbps, maxSpeed, r.speed_mbps >= 20 ? 'is-fast' : r.speed_mbps >= 5 ? 'is-medium' : 'is-slow')}`
                        : '<span class="speed-muted">—</span>';
                    const taken = r.time_taken_sec !== null ? `${r.time_taken_sec.toFixed(2)}s` : '—';
                    const bytes = r.bytes_downloaded ? `${(r.bytes_downloaded / 1048576).toFixed(2)} MB` : '—';
                    const badge = isErr
                        ? `<span class="speed-state speed-state-error">Error</span>`
                        : `<span class="speed-state speed-state-ok">✓ OK</span>`;

                    const tr = document.createElement('tr');
                    tr.className = `speed-result-row ${isErr ? 'is-error' : ''}`;
                    tr.innerHTML = `
                        <td class="speed-client">${medal}${dc}</td>
                        <td>${ping}</td>
                        <td>${speed}${isErr ? `<div class="speed-row-error">${r.error}</div>` : ''}</td>
                        <td class="speed-muted">${taken}</td>
                        <td class="speed-muted">${bytes}</td>
                        <td>${badge}</td>`;
                    tbody.appendChild(tr);
                }

                document.getElementById('st-rerun-btn').classList.remove('hidden');
                updateSummary();
                showToast('Speed test completed.', 'success', 'Speed Test');
            }
        };

        es.onerror = () => {
            es.close();
            window._stEventSource = null;
            if (completedCount === 0) {
                document.getElementById('st-spinner').classList.add('hidden');
                document.getElementById('st-error').textContent = 'Live tracking connection failed or interrupted.';
                document.getElementById('st-error').classList.remove('hidden');
                showToast('Live tracking connection failed or interrupted.', 'error', 'Speed Test Error');
            }
            document.getElementById('st-rerun-btn').classList.remove('hidden');
        };
    }

    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') closeSpeedTest();
    });

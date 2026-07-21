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

    let availableMoveChannels = [];
    let pendingMoveChannel = null;
    let selectedFullMoveChannel = null;
    let fullMoveBusy = false;
    let fullMovePollTimer = null;
    let fullMovePollFailures = 0;
    let fullMoveLastJob = null;
    const fullMoveStorageKey = `tg-stremio-full-move:${dbIndex}:${mediaType}:${tmdbId}`;

    function rememberFullMoveJob(jobId, targetName = '') {
        try {
            localStorage.setItem(fullMoveStorageKey, JSON.stringify({
                job_id: String(jobId || ''),
                target_name: String(targetName || ''),
                saved_at: Date.now(),
            }));
        } catch (_) {}
    }

    function forgetFullMoveJob() {
        try { localStorage.removeItem(fullMoveStorageKey); } catch (_) {}
    }

    function readRememberedFullMoveJob() {
        try {
            const raw = localStorage.getItem(fullMoveStorageKey);
            if (!raw) return null;
            const value = JSON.parse(raw);
            return value && value.job_id ? value : null;
        } catch (_) {
            return null;
        }
    }

    function setFullMoveRunningButton(label = 'Moving full title…') {
        fullMoveBusy = true;
        const submit = document.getElementById('full-move-submit');
        if (submit) {
            submit.disabled = true;
            submit.innerHTML = `<span class="loader-ring move-button-loader"></span> ${escapeHtml(label)}`;
        }
    }

    function setFullMoveState(message = '', type = 'info') {
        const state = document.getElementById('full-move-state');
        if (!state) return;
        state.textContent = message;
        state.classList.toggle('hidden', !message);
        state.classList.toggle('move-state-error', type === 'error');
        state.classList.toggle('move-state-success', type === 'success');
    }

    function setAvailableChannelState(message = '', type = 'info') {
        const state = document.getElementById('available-channel-state');
        if (!state) return;
        state.textContent = message;
        state.classList.toggle('hidden', !message);
        state.classList.toggle('move-state-error', type === 'error');
    }

    function renderAvailableChannels() {
        const list = document.getElementById('available-channel-list');
        const apply = document.getElementById('available-channel-apply');
        if (!list) return;
        if (!availableMoveChannels.length) {
            list.innerHTML = `<div class="content-empty"><i class="fa-solid fa-tower-broadcast"></i><strong>No available channels</strong><span>Add an AUTH channel in Settings and make the bot an admin.</span></div>`;
            if (apply) apply.disabled = true;
            return;
        }
        list.innerHTML = availableMoveChannels.map((channel, index) => {
            const active = pendingMoveChannel && String(pendingMoveChannel.id) === String(channel.id);
            return `<button type="button" class="available-channel-card${active ? ' active' : ''}" data-channel-index="${index}">
                <span class="available-channel-icon"><i class="fa-solid fa-bullhorn"></i></span>
                <span class="available-channel-copy"><strong>${escapeHtml(channel.name || 'Unnamed channel')}</strong><small>Available destination</small></span>
                <span class="available-channel-check"><i class="fa-solid fa-check"></i></span>
            </button>`;
        }).join('');
        list.querySelectorAll('[data-channel-index]').forEach(button => {
            button.addEventListener('click', () => selectAvailableChannel(Number(button.dataset.channelIndex)));
        });
        if (apply) apply.disabled = !pendingMoveChannel;
    }

    async function loadAvailableChannels(force = false) {
        if (availableMoveChannels.length && !force) {
            renderAvailableChannels();
            return;
        }
        const list = document.getElementById('available-channel-list');
        if (list) list.innerHTML = `<div class="content-empty"><i class="fa-solid fa-spinner fa-spin"></i><strong>Loading channels</strong><span>Checking configured AUTH channels.</span></div>`;
        setAvailableChannelState('');
        try {
            const response = await fetch(`/api/media/move-title/channels?tmdb_id=${encodeURIComponent(tmdbId)}&db_index=${encodeURIComponent(dbIndex)}&media_type=${encodeURIComponent(mediaType)}`);
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || 'Could not load available channels.');
            availableMoveChannels = (data.data || []).map((channel, index) => {
                const id = String(channel.id || '');
                const resolvedName = String(channel.name || '').trim();
                const name = resolvedName && resolvedName !== id && !/^-?\d+$/.test(resolvedName)
                    ? resolvedName
                    : `AUTH Channel ${index + 1}`;
                return {id, name};
            }).filter(channel => channel.id);
            if (selectedFullMoveChannel && !availableMoveChannels.some(channel => String(channel.id) === String(selectedFullMoveChannel.id))) {
                selectedFullMoveChannel = null;
                pendingMoveChannel = null;
                const selectedName = document.getElementById('full-move-channel-name');
                if (selectedName) selectedName.textContent = 'No channel selected';
                const submit = document.getElementById('full-move-submit');
                if (submit) submit.disabled = true;
            }
            renderAvailableChannels();
            if (!availableMoveChannels.length) {
                setAvailableChannelState('No other configured AUTH channel is available for this title.', 'error');
            }
        } catch (error) {
            availableMoveChannels = [];
            if (list) list.innerHTML = `<div class="content-empty content-empty-error"><i class="fa-solid fa-triangle-exclamation"></i><strong>Could not load channels</strong><span>${escapeHtml(error.message || 'Unknown error')}</span></div>`;
            setAvailableChannelState(error.message || 'Could not load available channels.', 'error');
        }
    }

    async function openAvailableChannels() {
        if (fullMoveBusy) return;
        pendingMoveChannel = selectedFullMoveChannel ? {...selectedFullMoveChannel} : null;
        document.getElementById('available-channels-modal')?.classList.remove('hidden');
        await loadAvailableChannels();
    }

    function closeAvailableChannels() {
        if (fullMoveBusy) return;
        document.getElementById('available-channels-modal')?.classList.add('hidden');
        pendingMoveChannel = null;
    }

    function selectAvailableChannel(index) {
        const channel = availableMoveChannels[index];
        if (!channel) return;
        pendingMoveChannel = channel;
        renderAvailableChannels();
    }

    function applyAvailableChannel() {
        if (!pendingMoveChannel) return;
        selectedFullMoveChannel = {...pendingMoveChannel};
        const name = document.getElementById('full-move-channel-name');
        if (name) name.textContent = selectedFullMoveChannel.name;
        const submit = document.getElementById('full-move-submit');
        if (submit) submit.disabled = fullMoveBusy;
        setFullMoveState(`Destination selected: ${selectedFullMoveChannel.name}`);
        document.getElementById('available-channels-modal')?.classList.add('hidden');
        pendingMoveChannel = null;
    }

    function updateFullMoveProgress(job) {
        fullMoveLastJob = {...(fullMoveLastJob || {}), ...(job || {})};
        const current = fullMoveLastJob;
        const box = document.getElementById('full-move-progress');
        const label = document.getElementById('full-move-progress-label');
        const percent = document.getElementById('full-move-progress-percent');
        const bar = document.getElementById('full-move-progress-bar');
        const files = document.getElementById('full-move-progress-files');
        const messages = document.getElementById('full-move-progress-messages');
        const value = Math.max(0, Math.min(100, Number(current.progress || 0)));
        const copied = Number(current.copied_messages || 0);
        const skipped = Number(current.skipped_messages || 0);
        const totalMessages = Number(current.total_messages || 0);
        const processed = Math.min(totalMessages || copied + skipped, copied + skipped);
        const movedStreams = Number(current.files_moved || 0);
        const totalStreams = Number(current.files_total || 0);
        box?.classList.remove('hidden');
        if (label) label.textContent = current.message || 'Moving full title…';
        if (percent) percent.textContent = `${value}%`;
        if (bar) bar.style.width = `${value}%`;
        if (files) {
            files.textContent = current.stage === 'saving' || current.stage === 'cleanup' || current.stage === 'completed'
                ? `${movedStreams} / ${totalStreams} streams indexed`
                : `${processed} / ${totalMessages} files processed`;
        }
        if (messages) {
            messages.textContent = `${copied} copied${skipped ? ` · ${skipped} waiting for retry` : ''}`;
        }
    }

    function resetFullMoveButton() {
        fullMoveBusy = false;
        const submit = document.getElementById('full-move-submit');
        if (submit) {
            submit.disabled = !selectedFullMoveChannel;
            submit.innerHTML = `<i class="fa-solid fa-right-left"></i> Move full ${['tv', 'series'].includes(mediaType) ? 'series' : 'movie'} and remove old`;
        }
    }

    async function pollFullTitleMove(jobId) {
        clearTimeout(fullMovePollTimer);
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 12000);
        try {
            const response = await fetch(`/api/media/move-title/status?job_id=${encodeURIComponent(jobId)}&_=${Date.now()}`, {
                cache: 'no-store',
                credentials: 'same-origin',
                signal: controller.signal,
            });
            const job = await response.json().catch(() => ({}));
            if (!response.ok) {
                const error = new Error(job.detail || 'Could not read move progress.');
                error.retryable = response.status >= 500 || response.status === 408 || response.status === 429;
                error.status = response.status;
                throw error;
            }

            fullMovePollFailures = 0;
            rememberFullMoveJob(jobId, job.target_channel || selectedFullMoveChannel?.name || '');
            updateFullMoveProgress(job);

            if (job.status === 'completed') {
                forgetFullMoveJob();
                const warning = job.old_files_removed === false;
                setFullMoveState(job.message || 'Full title moved.', warning ? 'error' : 'success');
                showToast(job.message || 'Full title moved.', warning ? 'info' : 'success', warning ? 'Moved with warning' : 'Move complete');
                setTimeout(() => location.reload(), 1300);
                return;
            }
            if (job.status === 'failed') {
                forgetFullMoveJob();
                const error = new Error(job.error || job.message || 'The full-title move failed.');
                error.retryable = false;
                throw error;
            }

            setFullMoveState('Move is running safely in the background. You may keep this page open or return later.');
            fullMovePollTimer = setTimeout(() => pollFullTitleMove(jobId), 3000);
        } catch (error) {
            const retryable = error?.retryable === true || error?.name === 'AbortError' || error instanceof TypeError;
            if (retryable) {
                fullMovePollFailures += 1;
                const retryDelay = Math.min(15000, 3000 + (fullMovePollFailures - 1) * 2000);
                const offline = typeof navigator !== 'undefined' && navigator.onLine === false;
                const reconnectMessage = offline
                    ? 'Internet connection is offline. The server move may still be running; reconnecting automatically…'
                    : 'Progress connection was interrupted. The server move is still protected; reconnecting automatically…';
                setFullMoveState(reconnectMessage);
                if (fullMoveLastJob) {
                    updateFullMoveProgress({...fullMoveLastJob, message: reconnectMessage});
                }
                fullMovePollTimer = setTimeout(() => pollFullTitleMove(jobId), retryDelay);
                return;
            }

            forgetFullMoveJob();
            const message = error.message || 'The full-title move failed.';
            setFullMoveState(message, 'error');
            showErrorMessage(message);
            resetFullMoveButton();
        } finally {
            clearTimeout(timeout);
        }
    }

    function resumeRememberedFullMove() {
        const remembered = readRememberedFullMoveJob();
        if (!remembered) return;
        setFullMoveRunningButton('Reconnecting to move…');
        setFullMoveState('Restoring the active move progress…');
        updateFullMoveProgress({progress: 0, message: 'Restoring the active move progress…'});
        pollFullTitleMove(remembered.job_id);
    }

    async function startFullTitleMove() {
        if (fullMoveBusy) return;
        if (!selectedFullMoveChannel) {
            setFullMoveState('Choose an available destination channel first.', 'error');
            await openAvailableChannels();
            return;
        }
        const confirmed = await confirmAction({
            title: `Move full ${['tv', 'series'].includes(mediaType) ? 'series' : 'movie'}`,
            subtitle: 'Every indexed stream will be moved together.',
            message: `Move the complete title to “${selectedFullMoveChannel.name}” and remove old Telegram posts after the index is updated?`,
            confirmText: `Move full ${['tv', 'series'].includes(mediaType) ? 'series' : 'movie'}`,
            tone: 'primary'
        });
        if (!confirmed) return;

        setFullMoveRunningButton('Starting full move…');
        const submit = document.getElementById('full-move-submit');
        setFullMoveState('Starting the safe full-title move…');
        updateFullMoveProgress({progress: 0, message: 'Starting full-title move…'});
        try {
            const response = await fetch(`/api/media/move-title/start?tmdb_id=${tmdbId}&db_index=${dbIndex}&media_type=${mediaType}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({target_channel: selectedFullMoveChannel.id}),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || 'Could not start the full-title move.');
            rememberFullMoveJob(data.job_id, selectedFullMoveChannel.name);
            if (submit) submit.innerHTML = '<span class="loader-ring move-button-loader"></span> Moving full title…';
            await pollFullTitleMove(data.job_id);
        } catch (error) {
            setFullMoveState(error.message || 'Could not start the full-title move.', 'error');
            showErrorMessage(error.message || 'Could not start the full-title move.');
            resetFullMoveButton();
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


    /* ─────────────── Media Edit tab workspace ─────────────── */
    function switchMediaEditTab(tabName, updateHash = true) {
        const valid = ['details', 'content', 'subtitles', 'catalog', 'rescan', 'move'];
        const target = valid.includes(tabName) ? tabName : 'details';
        document.querySelectorAll('[data-edit-tab]').forEach(button => {
            const active = button.dataset.editTab === target;
            button.classList.toggle('active', active);
            button.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        document.querySelectorAll('[data-edit-panel]').forEach(panel => {
            panel.classList.toggle('active', panel.dataset.editPanel === target);
        });
        if (target === 'subtitles') loadMediaSubtitles();
        if (updateHash && window.history?.replaceState) {
            window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${target}`);
        }
        document.getElementById('media-edit-tabs')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    let mediaSubtitlesLoaded = false;
    let mediaSubtitlesLoading = false;

    function subtitleEpisodeLabel(subtitle) {
        const media = subtitle.media || {};
        if (CURRENT_MEDIA_TYPE !== 'tv') return 'Movie';
        const season = Number(media.season);
        const episode = Number(media.episode);
        if (!Number.isFinite(season) || !Number.isFinite(episode)) return 'Series';
        return `S${String(season).padStart(2, '0')}E${String(episode).padStart(2, '0')}`;
    }

    function renderMediaSubtitles(subtitles) {
        const list = document.getElementById('media-subtitle-list');
        const count = document.getElementById('media-subtitle-count');
        if (!list || !count) return;
        count.innerHTML = `<i class="fa-solid fa-closed-captioning"></i> ${subtitles.length} matched subtitle${subtitles.length === 1 ? '' : 's'}`;
        if (!subtitles.length) {
            list.innerHTML = `<div class="content-empty"><i class="fa-solid fa-closed-captioning"></i><strong>No matched subtitles</strong><span>Scan subtitle channels or use Relink pending after the video is indexed.</span></div>`;
            return;
        }
        list.innerHTML = subtitles.map(subtitle => {
            const language = subtitle.language_name || String(subtitle.language_code || 'und').toUpperCase();
            const source = subtitle.chat_id && subtitle.msg_id ? `${subtitle.chat_id} / ${subtitle.msg_id}` : 'Telegram source';
            const subtitleId = escapeHtml(subtitle._id || '');
            const subtitleDbIndex = Number(subtitle.subtitle_db_index || subtitle.db_index || 1);
            return `<article class="media-subtitle-row">
                <span class="subtitle-language-mark">${escapeHtml(String(subtitle.language_code || 'und').toUpperCase())}</span>
                <div class="media-subtitle-copy">
                    <div class="media-subtitle-meta"><strong>${escapeHtml(language)}</strong><span>${escapeHtml(subtitleEpisodeLabel(subtitle))}</span><span>${escapeHtml(subtitle.size || '')}</span></div>
                    <p title="${escapeHtml(subtitle.filename || '')}">${escapeHtml(subtitle.filename || 'Unnamed subtitle')}</p>
                    <small><i class="fa-brands fa-telegram"></i> ${escapeHtml(source)} · Storage ${subtitleDbIndex}</small>
                </div>
                <button type="button" class="btn-ui btn-danger" onclick="deleteMediaSubtitle('${subtitleId}', ${subtitleDbIndex})" title="Remove subtitle index"><i class="fa-solid fa-trash"></i><span>Remove</span></button>
            </article>`;
        }).join('');
    }

    async function loadMediaSubtitles(force = false) {
        if (mediaSubtitlesLoading || (mediaSubtitlesLoaded && !force)) return;
        mediaSubtitlesLoading = true;
        const list = document.getElementById('media-subtitle-list');
        const count = document.getElementById('media-subtitle-count');
        if (list && force) list.innerHTML = `<div class="content-empty"><i class="fa-solid fa-spinner fa-spin"></i><strong>Refreshing subtitles</strong><span>Checking matched subtitle records.</span></div>`;
        try {
            const params = new URLSearchParams({
                media_type: CURRENT_MEDIA_TYPE,
                tmdb_id: String(CURRENT_TMDB_ID),
                db_index: String(CURRENT_DB_INDEX),
            });
            const response = await fetch(`/api/media/subtitles?${params.toString()}`);
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || 'Could not load subtitles.');
            renderMediaSubtitles(data.subtitles || []);
            mediaSubtitlesLoaded = true;
        } catch (error) {
            if (count) count.textContent = 'Subtitle list unavailable';
            if (list) list.innerHTML = `<div class="content-empty content-empty-error"><i class="fa-solid fa-triangle-exclamation"></i><strong>Could not load subtitles</strong><span>${escapeHtml(error.message || 'Unknown error')}</span></div>`;
        } finally {
            mediaSubtitlesLoading = false;
        }
    }

    async function deleteMediaSubtitle(subtitleId, subtitleDbIndex) {
        const confirmed = await confirmAction({
            title: 'Remove subtitle index',
            subtitle: 'The Telegram subtitle file will stay in its channel.',
            message: 'Remove this subtitle from the Stremio subtitle list?',
            confirmText: 'Remove subtitle',
            tone: 'danger'
        });
        if (!confirmed) return;
        try {
            const params = new URLSearchParams({ subtitle_db_index: String(subtitleDbIndex) });
            const response = await fetch(`/api/media/subtitles/${encodeURIComponent(subtitleId)}?${params.toString()}`, { method: 'DELETE' });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || 'Could not remove subtitle.');
            showToast(data.message || 'Subtitle removed.', 'success', 'Subtitles');
            mediaSubtitlesLoaded = false;
            await loadMediaSubtitles(true);
        } catch (error) {
            showToast(error.message || 'Could not remove subtitle.', 'error', 'Subtitles');
        }
    }

    async function relinkMediaSubtitles() {
        const button = document.getElementById('media-subtitle-relink');
        if (button) button.disabled = true;
        try {
            const response = await fetch('/api/subtitles/relink', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ limit: 1000 })
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || 'Could not relink subtitles.');
            showToast(data.message || 'Subtitle relink complete.', 'success', 'Subtitles');
            mediaSubtitlesLoaded = false;
            await loadMediaSubtitles(true);
        } catch (error) {
            showToast(error.message || 'Could not relink subtitles.', 'error', 'Subtitles');
        } finally {
            if (button) button.disabled = false;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const requestedTab = window.location.hash.replace('#', '');
        switchMediaEditTab(['details', 'content', 'subtitles', 'catalog', 'rescan', 'move'].includes(requestedTab) ? requestedTab : 'details', false);
        loadMediaSubtitles();
        const select = document.getElementById('custom-catalog-select');
        if (select) select.addEventListener('change', updateCatalogDropdownStatus);
        loadMediaCatalogDropdown();
        resumeRememberedFullMove();
        window.addEventListener('online', () => {
            const remembered = readRememberedFullMoveJob();
            if (remembered && fullMoveBusy) {
                clearTimeout(fullMovePollTimer);
                pollFullTitleMove(remembered.job_id);
            }
        });
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') closeAvailableChannels();
        });
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

/* Page behavior: dashboard */
const streamState = {
        currentEditToken: null,
        activeStreams: []
    };

    function toggleCreateForm() {
        const formContainer = document.getElementById('create-form-container');
        const btnContainer = document.getElementById('create-btn-container');
        if (!formContainer || !btnContainer) return;

        if (formContainer.classList.contains('hidden')) {
            formContainer.classList.remove('hidden');
            btnContainer.classList.add('hidden');
        } else {
            formContainer.classList.add('hidden');
            btnContainer.classList.remove('hidden');
        }
    }

    function openEditModal(token, daily, monthly) {
    const tokenStr = String(token || '');
    streamState.currentEditToken = tokenStr;
    document.getElementById('edit-token-id').value = tokenStr;
    document.getElementById('edit-daily').value = (daily === null || daily === undefined) ? 0 : daily;
    document.getElementById('edit-monthly').value = (monthly === null || monthly === undefined) ? 0 : monthly;
    const modal = document.getElementById('edit-modal');
    modal.classList.remove('hidden');
    }

    function closeEditModal() {
        document.getElementById('edit-modal').classList.add('hidden');
        streamState.currentEditToken = null;
    }

    async function saveTokenLimits() {
        if (!streamState.currentEditToken) return;

        const daily = Number(document.getElementById('edit-daily').value || 0);
        const monthly = Number(document.getElementById('edit-monthly').value || 0);

        try {
            const response = await fetch('/api/tokens/' + encodeURIComponent(streamState.currentEditToken), {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    daily_limit_gb: daily,
                    monthly_limit_gb: monthly
                })
            });

            if (response.ok) {
                closeEditModal();
                showToast('Token limits updated successfully.', 'success', 'Updated');
                setTimeout(() => window.location.reload(), 500);
                return;
            }

            let message = 'Failed to update limits';
            try {
                const data = await response.json();
                message = data.detail || data.message || message;
            } catch (_) {}
            showToast(message, 'error', 'Update failed');
        } catch (error) {
            console.error(error);
            showToast('Error updating limits', 'error', 'Update failed');
        }
    }

    async function createToken(event) {
        event.preventDefault();

        const nameInput = document.getElementById('token-name');
        const dailyInput = document.getElementById('daily-limit');
        const monthlyInput = document.getElementById('monthly-limit');

        const payload = {
            name: nameInput.value.trim(),
            daily_limit_gb: Number(dailyInput.value || 0),
            monthly_limit_gb: Number(monthlyInput.value || 0)
        };

        if (!payload.name) {
            showToast('Token alias is required.', 'error', 'Validation');
            return;
        }

        try {
            const response = await fetch('/api/tokens', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                showToast('Token created successfully.', 'success', 'Created');
                setTimeout(() => window.location.reload(), 500);
                return;
            }

            let message = 'Error creating token';
            try {
                const data = await response.json();
                message = data.detail || data.message || message;
            } catch (_) {}
            showToast(message, 'error', 'Create failed');
        } catch (error) {
            console.error(error);
            showToast('Error creating token', 'error', 'Create failed');
        }
    }

    async function revokeToken(token) {
        const confirmed = await confirmAction({ title: 'Revoke token', subtitle: 'The user loses access immediately.', message: 'Revoke this access token?', confirmText: 'Revoke token', tone: 'danger' });
        if (!confirmed) return;

        try {
            const response = await fetch('/api/tokens/' + encodeURIComponent(String(token || '')), {
                method: 'DELETE'
            });

            if (response.ok) {
                showToast('Token deleted successfully.', 'success', 'Deleted');
                setTimeout(() => window.location.reload(), 500);
                return;
            }

            let message = 'Error deleting token';
            try {
                const data = await response.json();
                message = data.detail || data.message || message;
            } catch (_) {}
            showToast(message, 'error', 'Delete failed');
        } catch (error) {
            console.error(error);
            showToast('Error deleting token', 'error', 'Delete failed');
        }
    }

    async function copyUrl(url) {
        const text = String(url || '');
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(text);
            } else {
                const temp = document.createElement('textarea');
                temp.value = text;
                temp.setAttribute('readonly', '');
                temp.style.position = 'fixed';
                temp.style.left = '-9999px';
                temp.style.top = '0';
                document.body.appendChild(temp);
                temp.focus();
                temp.select();
                const ok = document.execCommand('copy');
                document.body.removeChild(temp);
                if (!ok) throw new Error('copy failed');
            }
            showToast('Manifest URL copied to clipboard.', 'success', 'Copied');
        } catch (error) {
            console.error(error);
            showToast('Failed to copy manifest URL.', 'error', 'Copy failed');
        }
    }

    function escapeHtml(unsafe) {
        if (unsafe === null || unsafe === undefined) return '';
        return String(unsafe)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function formatBytes(bytes) {
        const value = Number(bytes || 0);
        if (!value) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
        return (value / Math.pow(1024, index)).toFixed(index === 0 ? 0 : 2) + ' ' + units[index];
    }

    function formatDuration(seconds) {
        const value = Math.max(0, Number(seconds || 0));
        const total = Math.floor(value);

        const h = Math.floor(total / 3600);
        const m = Math.floor((total % 3600) / 60);
        const s = total % 60;

        if (h > 0) {
            return `${h}h ${m}m ${s}s`;
        }
        if (m > 0) {
            return `${m}m ${s}s`;
        }
        return `${s}s`;
    }

    function formatTimestamp(ts) {
        const value = Number(ts || 0);
        if (!value) return '—';
        const date = new Date(value * 1000);
        if (Number.isNaN(date.getTime())) return '—';
        return date.toLocaleString();
    }

    function getStreamTitle(stream) {
        return stream?.title || stream?.meta?.title || 'Unknown Stream';
    }

    function getClientLabel(stream) {
        const parts = [];
        if (stream?.client_index !== null && stream?.client_index !== undefined) {
            parts.push('Bot ' + (Number(stream.client_index) + 1));
        }
        if (stream?.dc_id !== null && stream?.dc_id !== undefined) {
            parts.push('DC ' + stream.dc_id);
        }
        return parts.length ? parts.join(' • ') : 'Unknown node';
    }

    function getStatusBadge(status) {
        const normalized = String(status || '').toLowerCase();

        if (normalized === 'active') {
            return { className: 'stream-badge-live', text: 'Live' };
        }
        if (normalized === 'cancelled') {
            return { className: 'bg-yellow-500/15 text-yellow-300', text: 'Cancelled' };
        }
        if (normalized === 'completed' || normalized === 'finished') {
            return { className: 'bg-green-500/15 text-green-300', text: 'Completed' };
        }
        if (normalized === 'failed' || normalized === 'error') {
            return { className: 'bg-red-500/15 text-red-300', text: normalized.charAt(0).toUpperCase() + normalized.slice(1) };
        }

        return {
            className: 'stream-badge-recent',
            text: normalized ? normalized.charAt(0).toUpperCase() + normalized.slice(1) : 'Live'
        };
    }

    function getLiveDuration(stream) {
        const startTs = Number(stream?.start_ts || 0);
        if (!startTs) return '0s';
        const now = Date.now() / 1000;
        return formatDuration(now - startTs);
    }

    function renderStreamCard(stream) {
        const status = getStatusBadge(stream?.status);
        const title = escapeHtml(getStreamTitle(stream));
        const streamId = escapeHtml(stream?.stream_id ? String(stream.stream_id).slice(0, 12) + '…' : 'Unknown');
        const label = escapeHtml(getClientLabel(stream));
        const totalBytes = formatBytes(stream?.total_bytes || 0);
        const avgSpeed = stream?.avg_mbps !== null && stream?.avg_mbps !== undefined
            ? Number(stream.avg_mbps).toFixed(3) + ' MB/s'
            : '—';
        const started = formatTimestamp(stream?.start_ts);
        const liveDuration = getLiveDuration(stream);

        return `
            <div class="stream-card rounded-[2rem] p-5">
                <div class="flex justify-between items-start gap-3">
                    <div class="min-w-0 pr-2">
                        <h5 class="font-bold text-sm text-text truncate">${title}</h5>
                        <div class="mt-1 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-widest text-text-secondary">
                            <span>${label}</span>
                            <span>•</span>
                            <span>${streamId}</span>
                        </div>
                    </div>
                    <span class="text-[10px] font-bold px-2 py-1 rounded-lg uppercase whitespace-nowrap ${status.className}">
                        ${escapeHtml(status.text)}
                    </span>
                </div>

                <div class="grid grid-cols-2 gap-3 mt-4 pt-4 border-t border-white/5">
                    <div class="text-center">
                        <p class="text-[9px] text-text-secondary uppercase tracking-widest font-bold">Speed</p>
                        <p class="text-xs font-bold text-text">${avgSpeed}</p>
                    </div>
                    <div class="text-center">
                        <p class="text-[9px] text-text-secondary uppercase tracking-widest font-bold">Total</p>
                        <p class="text-xs font-bold text-text">${escapeHtml(totalBytes)}</p>
                    </div>
                    <div class="text-center">
                        <p class="text-[9px] text-text-secondary uppercase tracking-widest font-bold">Duration</p>
                        <p class="text-xs font-bold text-text live-duration">${escapeHtml(liveDuration)}</p>
                    </div>
                    <div class="text-center">
                        <p class="text-[9px] text-text-secondary uppercase tracking-widest font-bold">Started</p>
                        <p class="text-xs font-bold text-text truncate live-started">${escapeHtml(started)}</p>
                    </div>
                </div>

                <div class="mt-4 pt-4 border-t border-white/5 space-y-2">
                    <div class="flex items-center justify-between text-xs gap-3">
                        <span class="text-text-secondary">Stream ID</span>
                        <span class="font-mono text-text text-right truncate max-w-[65%]">${streamId}</span>
                    </div>
                    <div class="flex items-center justify-between text-xs gap-3">
                        <span class="text-text-secondary">Status</span>
                        <span class="text-text text-right truncate max-w-[65%]">${escapeHtml(stream?.status || 'active')}</span>
                    </div>
                </div>
            </div>
        `;
    }

    function renderEmptyState(icon, title, subtitle) {
        return `
            <div class="glass-panel p-8 rounded-[2rem] text-center border-dashed border-white/10">
                <i class="${icon} text-4xl text-white/10 mb-3"></i>
                <p class="text-sm text-text-secondary font-medium">${escapeHtml(title)}</p>
                <p class="text-xs text-text-secondary mt-1">${escapeHtml(subtitle)}</p>
            </div>
        `;
    }

    async function loadStreamStats() {
        const activeContainer = document.getElementById('active-streams-container');
        const liveCount = document.getElementById('live-stream-count');
        const liveNowCount = document.getElementById('live-now-count');
        const recentCount = document.getElementById('recent-stream-count');

        try {
            const response = await fetch('/stream/stats', { cache: 'no-store' });
            if (!response.ok) throw new Error('Failed to load stream stats');

            const data = await response.json();
            const activeStreams = Array.isArray(data.active_streams) ? data.active_streams : [];
            const recentStreams = Array.isArray(data.recent_streams) ? data.recent_streams : [];

            streamState.activeStreams = activeStreams;

            if (liveCount) liveCount.textContent = activeStreams.length + ' Active';
            if (liveNowCount) liveNowCount.textContent = String(activeStreams.length);
            if (recentCount) recentCount.textContent = String(recentStreams.length);

            if (activeContainer) {
                activeContainer.innerHTML = activeStreams.length
                    ? activeStreams.map(stream => renderStreamCard(stream)).join('')
                    : renderEmptyState(
                        'fa-solid fa-satellite-dish',
                        'No active streams right now',
                        'The live network is idle at the moment.'
                    );
            }
        } catch (error) {
            console.error(error);
            if (activeContainer) {
                activeContainer.innerHTML = renderEmptyState(
                    'fa-solid fa-triangle-exclamation',
                    'Unable to load live network',
                    'Please try refreshing the page.'
                );
            }
        }
    }

    function refreshLiveDurations() {
        const cards = document.querySelectorAll('#active-streams-container .stream-card');
        cards.forEach((card, index) => {
            const durationEl = card.querySelector('.live-duration');
            const stream = streamState.activeStreams[index];
            if (durationEl && stream) {
                durationEl.textContent = getLiveDuration(stream);
            }
        });
    }

    async function refreshDashboard() {
        const icon = document.getElementById('refresh-icon');
        if (icon) icon.classList.add('animate-spin');

        try {
            const response = await fetch('/api/system/stats', { cache: 'no-store' });
            if (response.ok) {
                const stats = await response.json();

                const elUptime = document.getElementById('sys-uptime');
                if (elUptime) elUptime.innerText = stats.uptime || 'N/A';

                const elBotCount = document.getElementById('sys-bots-count');
                if (elBotCount) elBotCount.innerText = (stats.connected_bots ?? 0) + ' Nodes';

                const elLive = document.getElementById('sys-live-streams');
                if (elLive) elLive.innerText = (stats.total_active_streams ?? 0) + ' Active';

                const elVersion = document.getElementById('sys-version');
                if (elVersion) elVersion.innerText = 'v' + (stats.version || '1.0.0');

                if (stats.databases && Array.isArray(stats.databases)) {
                    stats.databases.forEach((db, index) => {
                        const elMovies = document.getElementById(`db-movies-${index}`);
                        if (elMovies) elMovies.innerText = db.movie_count.toLocaleString();

                        const elTv = document.getElementById(`db-tv-${index}`);
                        if (elTv) elTv.innerText = db.tv_count.toLocaleString();

                        const elStorage = document.getElementById(`db-storage-${index}`);
                        if (elStorage) {
                            const mb = db.storageSize / (1024 * 1024);
                            elStorage.innerText = mb.toFixed(1) + ' MB';
                        }
                    });
                }

                if (stats.api_tokens && Array.isArray(stats.api_tokens)) {
                    const rows = document.querySelectorAll('tbody tr');
                    stats.api_tokens.forEach((token, index) => {
                        const dailyBytes = (token.usage && token.usage.daily) ? (token.usage.daily.bytes || 0) : null;
                        const monthlyBytes = (token.usage && token.usage.monthly) ? (token.usage.monthly.bytes || 0) : null;

                        if (rows.length > index && !rows[index].querySelector('[colspan]')) {
                            const row = rows[index];

                            const dailyUsageSpan = row.querySelector('td:nth-child(2) span[data-bytes]');
                            const monthlyUsageSpan = row.querySelectorAll('td:nth-child(2) span[data-bytes]')[1];

                            if (dailyUsageSpan && dailyBytes !== null) {
                                dailyUsageSpan.setAttribute('data-bytes', dailyBytes);
                                dailyUsageSpan.textContent = formatBytes(dailyBytes);
                            }

                            if (monthlyUsageSpan && monthlyBytes !== null) {
                                monthlyUsageSpan.setAttribute('data-bytes', monthlyBytes);
                                monthlyUsageSpan.textContent = formatBytes(monthlyBytes);
                            }
                        }

                        // Keep the mobile card view in sync as well
                        const card = document.getElementById(`token-card-${index}`);
                        if (card) {
                            const cardDaily = card.querySelector('span.text-primary[data-bytes]');
                            const cardMonthly = card.querySelector('span.text-accent[data-bytes]');

                            if (cardDaily && dailyBytes !== null) {
                                cardDaily.setAttribute('data-bytes', dailyBytes);
                                cardDaily.textContent = formatBytes(dailyBytes);
                            }

                            if (cardMonthly && monthlyBytes !== null) {
                                cardMonthly.setAttribute('data-bytes', monthlyBytes);
                                cardMonthly.textContent = formatBytes(monthlyBytes);
                            }
                        }
                    });
                }
            }

            await loadStreamStats();
        } catch (error) {
            console.error('Failed to refresh dashboard:', error);
            showToast('Dashboard refresh failed.', 'error', 'Refresh failed');
        } finally {
            setTimeout(() => {
                if (icon) icon.classList.remove('animate-spin');
            }, 450);
        }
    }

    function formatInitialBytes() {
        document.querySelectorAll('[data-bytes]').forEach(el => {
            const raw = el.getAttribute('data-bytes');
            el.textContent = formatBytes(raw);
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        formatInitialBytes();
        loadStreamStats();
        setInterval(loadStreamStats, 30000);
        setInterval(refreshLiveDurations, 1000);
    });

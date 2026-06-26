/* Page behavior: admin-dashboard */
function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function getStatusBadge(status) {
        const s = String(status || '').toLowerCase();
        if (s === 'degraded' || s === 'cancelled') return 'status-badge status-warn';
        if (s === 'failing' || s === 'error') return 'status-badge status-bad';
        return 'status-badge status-good';
    }

    async function fetchStats() {
        try {
            const res = await fetch('/api/admin/system-stats');
            if (!res.ok) return;

            const data = await res.json();
            document.getElementById('stat-cache-size').textContent = data.cache_size ?? '-';
            document.getElementById('stat-bot-count').textContent = data.total_bots ?? '-';

            const workloadsWrap = document.getElementById('stat-workloads');

            if (data.bot_workloads && data.bot_workloads.length > 0) {
                let html = '<div class="grid grid-cols-1 xl:grid-cols-2 gap-4">';
                data.bot_workloads.forEach(b => {
                    html += `
                        <div class="workload-row rounded-3xl p-4 sm:p-5">
                            <div class="flex flex-col gap-4">
                                <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                                    <div class="min-w-0">
                                        <div class="text-base sm:text-lg font-bold text-text">${escapeHtml(b.display_name)}</div>
                                        <div class="muted text-xs sm:text-sm mt-1">Bot performance summary</div>
                                    </div>
                                    <span class="${getStatusBadge(b.status)}">${escapeHtml(b.status)}</span>
                                </div>

                                <div class="grid grid-cols-3 sm:grid-cols-3 gap-3">
                                    <div class="glass-card-soft rounded-2xl p-4">
                                        <div class="muted text-xs uppercase tracking-wider font-bold">Active Streams</div>
                                        <div class="text-2xl font-black mt-2 text-text">${b.current_load ?? 0}</div>
                                    </div>

                                    <div class="glass-card-soft rounded-2xl p-4">
                                        <div class="muted text-xs uppercase tracking-wider font-bold">Avg Speed</div>
                                        <div class="text-2xl font-black mt-2 text-text">${Number(b.avg_mbps ?? 0).toFixed(1)}</div>
                                        <div class="muted text-xs mt-1">MB/s</div>
                                    </div>

                                    <div class="glass-card-soft rounded-2xl p-4">
                                        <div class="muted text-xs uppercase tracking-wider font-bold">Recent Failures</div>
                                        <div class="text-2xl font-black mt-2 ${Number(b.failures ?? 0) > 0 ? 'text-red-400' : 'text-text'}">${b.failures ?? 0}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                });
                html += '</div>';
                workloadsWrap.innerHTML = html;
            } else {
                workloadsWrap.innerHTML = '<div class="empty-state">No bot data available</div>';
            }
        } catch (err) {
            console.error(err);
            showToast('Failed to load system stats.', 'error', 'Load Error');
        }
    }

    async function fetchAnalytics() {
        try {
            const res = await fetch('/api/admin/stream-analytics');
            const tbody = document.getElementById('analytics-tbody');
            const mobile = document.getElementById('analytics-mobile');

            if (!res.ok) {
                showToast('Failed to load stream analytics.', 'error', 'Load Error');
                return;
            }

            const data = await res.json();
            const streams = data?.data?.recent || [];

            if (!streams.length) {
                tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No recent streams recorded.</td></tr>';
                mobile.innerHTML = '<div class="empty-state">No recent streams recorded.</div>';
                return;
            }

            let tableHtml = '';
            let mobileHtml = '';

            streams.forEach(s => {
                const avg = Number(s.avg_mbps ?? 0);
                const peak = Number(s.peak_mbps ?? 0);
                const bytesStr = ((Number(s.total_bytes ?? 0)) / (1024 * 1024)).toFixed(1) + ' MB';
                const timeStr = s.logged_at ? new Date(s.logged_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—';
                const durationStr = s.duration_sec ? `${Number(s.duration_sec).toFixed(1)}s` : '—';
                const titleStr = s.title || s.meta?.title || '—';
                const status = s.status || 'unknown';

                tableHtml += `
                    <tr>
                        <td><span class="stream-id muted font-mono text-xs" title="${escapeHtml(s.stream_id)}">${escapeHtml(s.stream_id)}</span></td>
                        <td><div class="title-cell font-semibold" title="${escapeHtml(titleStr)}">${escapeHtml(titleStr)}</div></td>
                        <td class="text-center">Bot ${Number(s.client_index ?? 0) + 1} <span class="muted text-xs ml-1">(DC${escapeHtml(s.dc_id)})</span></td>
                        <td class="text-right font-semibold">${bytesStr}</td>
                        <td class="text-right font-semibold">${avg.toFixed(1)} <span class="muted">/ ${peak.toFixed(1)} MB/s</span></td>
                        <td class="text-center muted">${durationStr}</td>
                        <td class="text-center"><span class="${getStatusBadge(status)}">${escapeHtml(status)}</span></td>
                        <td class="text-right muted text-xs">${timeStr}</td>
                    </tr>
                `;

                mobileHtml += `
                    <div class="mobile-card">
                        <div class="flex items-start justify-between gap-3 mb-3">
                            <div class="min-w-0">
                                <div class="font-bold text-text">${escapeHtml(titleStr)}</div>
                                <div class="muted text-xs font-mono mt-1 break-all">${escapeHtml(s.stream_id)}</div>
                            </div>
                            <span class="${getStatusBadge(status)}">${escapeHtml(status)}</span>
                        </div>

                        <div class="mobile-kv">
                            <div class="key">Bot</div><div>Bot ${Number(s.client_index ?? 0) + 1} (DC${escapeHtml(s.dc_id)})</div>
                            <div class="key">Transferred</div><div>${bytesStr}</div>
                            <div class="key">Avg / Peak</div><div>${avg.toFixed(1)} / ${peak.toFixed(1)} MB/s</div>
                            <div class="key">Duration</div><div>${durationStr}</div>
                            <div class="key">Time</div><div>${timeStr}</div>
                        </div>
                    </div>
                `;
            });

            tbody.innerHTML = tableHtml;
            mobile.innerHTML = mobileHtml;
        } catch (err) {
            console.error(err);
            showToast('Failed to load stream analytics.', 'error', 'Load Error');
        }
    }

    async function fetchDeadLinks() {
        try {
            const res = await fetch('/api/admin/dead-links');
            const tbody = document.getElementById('dead-links-tbody');
            const mobile = document.getElementById('dead-links-mobile');

            if (!res.ok) {
                showToast('Failed to load dead links.', 'error', 'Load Error');
                return;
            }

            const data = await res.json();
            const links = data?.data || [];

            if (!links.length) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No dead links found. All files are healthy!</td></tr>';
                mobile.innerHTML = '<div class="empty-state">No dead links found. All files are healthy!</div>';
                return;
            }

            let tableHtml = '';
            let mobileHtml = '';

            links.forEach(l => {
                const isMovie = l.type === 'movie';
                const typeBadge = isMovie
                    ? '<span class="status-badge status-good">Movie</span>'
                    : '<span class="status-badge status-warn">TV Series</span>';

                const dateAdded = l.date_added ? new Date(l.date_added).toLocaleDateString() : '—';
                const qualityIdEsc = String(l.quality_id || '').replace(/'/g, "\\'");

                tableHtml += `
                    <tr>
                        <td>
                            <div class="font-semibold text-text">${escapeHtml(l.title)}</div>
                            <div class="muted text-xs mt-1">${escapeHtml(l.year || '')}</div>
                        </td>
                        <td>${typeBadge}</td>
                        <td>
                            <div class="font-semibold text-red-400">${escapeHtml(l.quality || 'Unknown')}</div>
                            <div class="muted text-xs mt-1">${escapeHtml(l.size || 'Unknown size')}</div>
                        </td>
                        <td class="text-center muted text-xs">${dateAdded}</td>
                        <td class="text-center">
                            <button onclick="deleteDeadLink(${l.tmdb_id}, ${l.db_index}, '${escapeHtml(l.type)}', '${qualityIdEsc}', ${l.season || -1}, ${l.episode || -1})"
                                    class="btn-ui btn-danger px-3 py-2 text-sm w-auto"
                                    title="Delete from Database">
                                <i class="fas fa-trash"></i>
                                Delete
                            </button>
                        </td>
                    </tr>
                `;

                mobileHtml += `
                    <div class="mobile-card">
                        <div class="flex items-start justify-between gap-3 mb-3">
                            <div>
                                <div class="font-bold text-text">${escapeHtml(l.title)}</div>
                                <div class="muted text-xs mt-1">${escapeHtml(l.year || '')}</div>
                            </div>
                            ${typeBadge}
                        </div>

                        <div class="mobile-kv mb-4">
                            <div class="key">Quality</div><div class="text-red-400 font-semibold">${escapeHtml(l.quality || 'Unknown')}</div>
                            <div class="key">Size</div><div>${escapeHtml(l.size || 'Unknown size')}</div>
                            <div class="key">Date Added</div><div>${dateAdded}</div>
                        </div>

                        <button onclick="deleteDeadLink(${l.tmdb_id}, ${l.db_index}, '${escapeHtml(l.type)}', '${qualityIdEsc}', ${l.season || -1}, ${l.episode || -1})"
                                class="btn-ui btn-danger">
                            <i class="fas fa-trash"></i>
                            Delete Dead Link
                        </button>
                    </div>
                `;
            });

            tbody.innerHTML = tableHtml;
            mobile.innerHTML = mobileHtml;
        } catch (err) {
            console.error(err);
            showToast('Failed to load dead links.', 'error', 'Load Error');
        }
    }

    async function clearCache() {
        const confirmed = await confirmAction({ title: 'Clear FileId cache', subtitle: 'Bots will fetch fresh metadata on the next stream.', message: 'Clear the Telegram FileId cache?', confirmText: 'Clear cache', tone: 'danger' });
        if (!confirmed) return;

        try {
            const res = await fetch('/api/admin/clear-cache', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                showToast(data.message || 'Cache cleared successfully.', 'success', 'Cache Cleared');
                fetchStats();
            } else {
                showToast('Failed to clear cache.', 'error', 'Request Failed');
            }
        } catch (err) {
            showToast('Error clearing cache.', 'error', 'Network Error');
        }
    }

    async function clearAnalytics() {
        const confirmed = await confirmAction({ title: 'Clear analytics', subtitle: 'This cannot be undone.', message: 'Clear all stream analytics history?', confirmText: 'Clear analytics', tone: 'danger' });
        if (!confirmed) return;

        try {
            const res = await fetch('/api/admin/clear-analytics', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                showToast(data.message || 'Analytics cleared successfully.', 'success', 'Analytics Cleared');
                fetchAnalytics();
            } else {
                const err = await res.json().catch(() => ({}));
                showToast(err.detail || 'Failed to clear analytics.', 'error', 'Request Failed');
            }
        } catch (err) {
            showToast('Error clearing analytics.', 'error', 'Network Error');
        }
    }

    async function deleteDeadLink(tmdb_id, db_index, type, quality_id, season, episode) {
        const confirmed = await confirmAction({ title: 'Purge dead link', subtitle: 'This quality will disappear from Stremio.', message: 'Remove this dead link from the database?', confirmText: 'Purge link', tone: 'danger' });
        if (!confirmed) return;

        try {
            let endpoint = '';
            if (type === 'movie') {
                endpoint = `/api/media/delete-quality?tmdb_id=${tmdb_id}&db_index=${db_index}&id=${quality_id}`;
            } else {
                endpoint = `/api/media/delete-tv-quality?tmdb_id=${tmdb_id}&db_index=${db_index}&season=${season}&episode=${episode}&id=${quality_id}`;
            }

            const res = await fetch(endpoint, { method: 'DELETE' });
            if (res.ok) {
                showToast('Dead link deleted successfully.', 'success', 'Cleanup Complete');
                fetchDeadLinks();
            } else {
                showToast('Failed to delete the dead link.', 'error', 'Delete Failed');
            }
        } catch (err) {
            showToast('Error communicating with server.', 'error', 'Network Error');
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        fetchStats();
        fetchAnalytics();
        fetchDeadLinks();
        setInterval(fetchStats, 10000);
        setInterval(fetchAnalytics, 15000);
    });

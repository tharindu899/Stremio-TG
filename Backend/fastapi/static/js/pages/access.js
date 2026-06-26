/* Page behavior: access */
let allTokens = [];
    let currentPage = 1;

    function fmtDate(iso) {
        if (!iso) return '—';
        const d = new Date(iso);
        return d.toLocaleDateString('en-IN', {
            timeZone: 'Asia/Kolkata',
            day: '2-digit',
            month: 'short',
            year: 'numeric'
        }) + ' ' + d.toLocaleTimeString('en-IN', {
            timeZone: 'Asia/Kolkata',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    function escHtml(s) {
        return String(s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function getFiltered() {
        const q = document.getElementById('search-input').value.toLowerCase().trim();
        const status = document.getElementById('filter-status').value;

        return allTokens.filter(t => {
            const matchQ = !q ||
                (t.user_name && t.user_name.toLowerCase().includes(q)) ||
                (t.user_id && String(t.user_id).includes(q));

            const matchStatus =
                status === 'all' ||
                (status === 'active' && !t.is_expired) ||
                (status === 'expired' && t.is_expired);

            return matchQ && matchStatus;
        });
    }

    function getStatusBadge(t) {
        return t.is_expired
            ? `<span class="status-badge status-expired"><i class="fas fa-circle text-[8px]"></i> Expired</span>`
            : `<span class="status-badge status-active"><i class="fas fa-circle text-[8px]"></i> Active</span>`;
    }

    function buildAddonHtml(t) {
        if (!t.has_token) {
            return `
                <div class="addon-box">
                    <span class="status-badge status-warning">No Token Yet</span>
                    <div class="text-xs text-soft italic mt-2">User hasn't generated addon token via bot.</div>
                </div>
            `;
        }

        if (t.is_expired) {
            return `
                <div class="addon-box">
                    <span class="status-badge status-expired">Subscription Expired</span>
                    <div class="text-xs text-soft italic mt-2">
                        ${t.user_found ? 'Subscription inactive/expired' : 'No subscription record'}
                    </div>
                    ${t.addon_url ? `
                        <button onclick="copyLink('${escHtml(t.addon_url)}')"
                            class="mt-3 text-xs font-semibold underline opacity-70 hover:opacity-100 transition">
                            Copy URL (admin)
                        </button>
                    ` : ''}
                </div>
            `;
        }

        return t.addon_url
            ? `
                <div class="addon-box">
                    <button onclick="copyLink('${escHtml(t.addon_url)}')"
                        class="glass-btn glass-btn-primary rounded-xl px-3 py-2 text-xs font-bold inline-flex items-center gap-2">
                        <i class="fas fa-copy"></i>
                        Copy Install Link
                    </button>
                </div>
            `
            : `<div class="addon-box text-soft text-xs">—</div>`;
    }

    function buildActions(t) {
        const safeName = escHtml(t.user_name || String(t.user_id || ''));
        let actionBtns = '';

        if (t.user_id) {
            actionBtns = `
                <button onclick="openAssignModal(${t.user_id}, '${safeName}')" class="action-chip glass-btn-primary">
                    Assign
                </button>
                <button onclick="openSubModal(${t.user_id}, '${safeName}', 'extend')" class="action-chip glass-btn-success">
                    Extend
                </button>
                <button onclick="openSubModal(${t.user_id}, '${safeName}', 'reduce')" class="action-chip glass-btn-warning">
                    Reduce
                </button>
                <button onclick="openSubModal(${t.user_id}, '${safeName}', 'delete')" class="action-chip glass-btn-danger">
                    Revoke
                </button>
            `;
        } else if (t.token) {
            actionBtns = `
                <button onclick="linkUser('${escHtml(t.token)}')" class="action-chip glass-btn-purple">
                    Link User ID
                </button>
                <div class="text-xs text-soft italic w-full mt-1">Enter Telegram user_id to enable management.</div>
            `;
        }

        const revokeTokenBtn = t.token ? `
            <button onclick="revokeToken('${escHtml(t.token)}')" class="action-chip glass-btn">
                Del Token
            </button>
        ` : '';

        return actionBtns + revokeTokenBtn;
    }

    function renderDesktopRows(slice) {
        const tbody = document.getElementById('token-table-body');

        if (!slice.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-10 text-soft">No tokens match your search.</td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = slice.map(t => {
            const displayName = t.user_name || (t.user_id ? 'Telegram User' : 'Unknown');
            const idHtml = t.user_id ? `<div class="text-xs text-soft mt-1">ID: ${t.user_id}</div>` : '';
            const rowCls = t.is_expired ? 'row-expired' : '';

            return `
                <tr class="${rowCls}">
                    <td class="px-4 py-4">${getStatusBadge(t)}</td>
                    <td class="px-4 py-4">
                        <div class="font-semibold section-title">${escHtml(displayName)}</div>
                        ${idHtml}
                    </td>
                    <td class="px-4 py-4">${buildAddonHtml(t)}</td>
                    <td class="px-4 py-4 text-soft text-xs">${t.created_at ? fmtDate(t.created_at) : '—'}</td>
                    <td class="px-4 py-4 text-xs">
                        ${t.expires_at
                            ? `<span class="${t.is_expired ? 'text-red-300 font-semibold' : 'section-title'}">${fmtDate(t.expires_at)}</span>`
                            : `<span class="text-red-300 italic">No expiry</span>`
                        }
                    </td>
                    <td class="px-4 py-4">
                        <div class="flex flex-wrap gap-2 justify-center">${buildActions(t)}</div>
                    </td>
                </tr>
            `;
        }).join('');
    }

    function renderMobileCards(slice) {
        const mobileWrap = document.getElementById('token-mobile-list');

        if (!slice.length) {
            mobileWrap.innerHTML = `
                <div class="empty-state text-center px-4 py-8 text-soft">
                    No tokens match your search.
                </div>
            `;
            return;
        }

        mobileWrap.innerHTML = slice.map(t => {
            const displayName = t.user_name || (t.user_id ? 'Telegram User' : 'Unknown');

            return `
                <div class="mobile-token-card ${t.is_expired ? 'row-expired' : ''}">
                    <div class="flex items-start justify-between gap-3 mb-3">
                        <div class="min-w-0">
                            <div class="font-semibold section-title break-words">${escHtml(displayName)}</div>
                            <div class="text-xs text-soft mt-1 break-all">${t.user_id ? 'ID: ' + t.user_id : 'No linked user'}</div>
                        </div>
                        <div class="shrink-0">${getStatusBadge(t)}</div>
                    </div>

                    <div class="grid grid-cols-1 gap-3 mb-3">
                        <div class="rounded-2xl px-4 py-3"
                             style="background: color-mix(in srgb, var(--bg) 55%, transparent); border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);">
                            <div class="text-[11px] uppercase tracking-[0.14em] text-soft font-bold mb-1">Addon Access</div>
                            ${buildAddonHtml(t)}
                        </div>

                        <div class="grid grid-cols-2 gap-3">
                            <div class="rounded-2xl px-4 py-3"
                                 style="background: color-mix(in srgb, var(--bg) 55%, transparent); border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);">
                                <div class="text-[11px] uppercase tracking-[0.14em] text-soft font-bold mb-1">Created</div>
                                <div class="text-sm font-semibold section-title break-words">${t.created_at ? fmtDate(t.created_at) : '—'}</div>
                            </div>
                            <div class="rounded-2xl px-4 py-3"
                                 style="background: color-mix(in srgb, var(--bg) 55%, transparent); border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);">
                                <div class="text-[11px] uppercase tracking-[0.14em] text-soft font-bold mb-1">Expires</div>
                                <div class="text-sm font-semibold ${t.is_expired ? 'text-red-300' : 'section-title'} break-words">
                                    ${t.expires_at ? fmtDate(t.expires_at) : 'No expiry'}
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="flex flex-wrap gap-2">
                        ${buildActions(t)}
                    </div>
                </div>
            `;
        }).join('');
    }

    function renderPage() {
        const filtered = getFiltered();
        const pageSize = parseInt(document.getElementById('page-size').value);
        const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));

        if (currentPage > totalPages) currentPage = totalPages;

        const start = filtered.length ? (currentPage - 1) * pageSize : 0;
        const slice = filtered.slice(start, start + pageSize);

        document.getElementById('page-info').textContent =
            filtered.length
                ? `Showing ${start + 1}–${Math.min(start + pageSize, filtered.length)} of ${filtered.length}`
                : 'Showing 0 of 0';

        document.getElementById('page-num').textContent = `Page ${currentPage} / ${totalPages}`;

        const prevBtn = document.getElementById('btn-prev');
        const nextBtn = document.getElementById('btn-next');

        prevBtn.disabled = currentPage <= 1;
        nextBtn.disabled = currentPage >= totalPages;

        prevBtn.style.opacity = currentPage <= 1 ? '0.45' : '1';
        nextBtn.style.opacity = currentPage >= totalPages ? '0.45' : '1';

        renderDesktopRows(slice);
        renderMobileCards(slice);
    }

    function changePage(dir) {
        const filtered = getFiltered();
        const pageSize = parseInt(document.getElementById('page-size').value);
        const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));

        currentPage += dir;
        if (currentPage < 1) currentPage = 1;
        if (currentPage > totalPages) currentPage = totalPages;

        renderPage();
    }

    async function loadTokens() {
        document.getElementById('token-table-body').innerHTML = `
            <tr><td colspan="6" class="text-center py-10 text-soft">Loading…</td></tr>
        `;
        document.getElementById('token-mobile-list').innerHTML = `
            <div class="empty-state text-center px-4 py-8 text-soft">Loading…</div>
        `;

        try {
            const resp = await fetch('/api/admin/access/tokens');
            const data = await resp.json();
            allTokens = data.tokens || [];

            document.getElementById('stat-total').textContent = allTokens.length;
            document.getElementById('stat-active').textContent = allTokens.filter(t => !t.is_expired).length;
            document.getElementById('stat-expired').textContent = allTokens.filter(t => t.is_expired).length;

            currentPage = 1;
            renderPage();
        } catch (err) {
            document.getElementById('token-table-body').innerHTML = `
                <tr><td colspan="6" class="text-center py-10 text-red-300">Error: ${err.message}</td></tr>
            `;
            document.getElementById('token-mobile-list').innerHTML = `
                <div class="empty-state text-center px-4 py-8 text-red-300">Error: ${err.message}</div>
            `;
            showToast('Failed to load access tokens.', 'error', 'Load Error');
        }
    }

    async function loadPlans() {
    try {
        const resp = await fetch('/api/admin/subscriptions/plans');
        if (!resp.ok) throw new Error(`HTTP error! status: ${resp.status}`);
        const result = await resp.json();
        const plans = result.data || [];
        const sel = document.getElementById('assign-plan-select');
        if (!sel) return;
        sel.innerHTML = '<option value="">— Select a plan —</option>' +
            plans.map(p => `
                <option value="${p.days}">
                    ${p.days} days${p.price ? ' — ₹' + p.price : ''}
                </option>
            `).join('');

    } catch (e) {
        console.warn('Could not load plans', e);
        showToast('Could not load subscription plans.', 'error', 'Plan Error');
    }
                }
    function openModal(modalId) {
        const modal = document.getElementById(modalId);
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        document.body.classList.add('overflow-hidden');
    }

    function closeModal(modalId) {
        const modal = document.getElementById(modalId);
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        document.body.classList.remove('overflow-hidden');
    }

    function openAssignModal(userId, userName) {
        document.getElementById('assign-user-id').value = userId;
        document.getElementById('assign-user-label').textContent = `User: ${userName} (ID: ${userId})`;
        document.getElementById('assign-custom-days').value = '';
        document.getElementById('assign-plan-select').value = '';
        openModal('assign-modal');
    }

    function closeAssignModal() {
        closeModal('assign-modal');
    }

    async function assignPlan() {
        const userId = parseInt(document.getElementById('assign-user-id').value);
        const customDays = parseInt(document.getElementById('assign-custom-days').value) || 0;
        const planDays = parseInt(document.getElementById('assign-plan-select').value) || 0;
        const days = customDays || planDays;

        if (!days || days < 1) {
            showToast('Please select a plan or enter custom days.', 'error', 'Validation');
            return;
        }

        try {
            const resp = await fetch(`/api/admin/access/users/${userId}/assign-plan`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ days })
            });

            const data = await resp.json();

            if (resp.ok) {
                showToast(`Assigned ${days} days to user ${userId}.`, 'success', 'Plan Assigned');
                closeAssignModal();
                loadTokens();
            } else {
                showToast(data.detail || 'Failed to assign plan.', 'error', 'Request Failed');
            }
        } catch (err) {
            showToast('Error: ' + err.message, 'error', 'Network Error');
        }
    }

    async function revokeToken(token) {
        const confirmed = await confirmAction({
            title: 'Delete access token',
            subtitle: 'This immediately removes the user’s add-on access.',
            message: 'Delete this token?',
            confirmText: 'Delete token',
            tone: 'danger'
        });
        if (!confirmed) return;

        try {
            const resp = await fetch(`/api/admin/access/tokens/${encodeURIComponent(token)}`, { method: 'DELETE' });
            const data = await resp.json();

            if (resp.ok) {
                showToast('Token deleted.', 'success', 'Access Updated');
                loadTokens();
            } else {
                showToast(data.detail || 'Failed.', 'error', 'Delete Failed');
            }
        } catch (err) {
            showToast('Error: ' + err.message, 'error', 'Network Error');
        }
    }

    async function linkUser(token) {
        const userId = prompt('Enter the Telegram User ID to link this token to:');
        if (!userId || isNaN(parseInt(userId))) {
            showToast('Invalid user ID.', 'error', 'Invalid Input');
            return;
        }

        try {
            const resp = await fetch(`/api/admin/access/tokens/${encodeURIComponent(token)}/link-user`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: parseInt(userId) })
            });

            const data = await resp.json();

            if (resp.ok) {
                showToast(`Token linked to user ${userId}.`, 'success', 'User Linked');
                loadTokens();
            } else {
                showToast(data.detail || 'Failed to link.', 'error', 'Link Failed');
            }
        } catch (err) {
            showToast('Error: ' + err.message, 'error', 'Network Error');
        }
    }

    function openSubModal(userId, userName, action) {
        document.getElementById('sub-action-user-id').value = userId;
        document.getElementById('sub-action-action').value = action;

        const titles = {
            extend: 'Extend Subscription',
            reduce: 'Reduce Subscription',
            delete: 'Revoke Subscription'
        };

        const descs = {
            extend: `Add days to <b>${userName}</b>'s subscription.`,
            reduce: `Remove days from <b>${userName}</b>'s subscription.`,
            delete: `<b>Warning:</b> Revoke <b>${userName}</b>'s subscription entirely.`
        };

        document.getElementById('sub-action-title').textContent = titles[action];
        document.getElementById('sub-action-desc').innerHTML = descs[action];

        const daysGroup = document.getElementById('sub-action-days-group');
        const btn = document.getElementById('sub-action-btn');

        if (action === 'delete') {
            daysGroup.style.display = 'none';
            btn.className = 'glass-btn glass-btn-danger rounded-2xl px-5 py-3 text-sm font-bold';
        } else if (action === 'reduce') {
            daysGroup.style.display = 'block';
            btn.className = 'glass-btn glass-btn-warning rounded-2xl px-5 py-3 text-sm font-bold';
        } else {
            daysGroup.style.display = 'block';
            btn.className = 'glass-btn glass-btn-success rounded-2xl px-5 py-3 text-sm font-bold';
        }

        document.getElementById('sub-action-days').value = 30;
        openModal('sub-action-modal');
    }

    function closeSubModal() {
        closeModal('sub-action-modal');
    }

    async function submitSubAction() {
        const userId = parseInt(document.getElementById('sub-action-user-id').value);
        const action = document.getElementById('sub-action-action').value;
        const days = parseInt(document.getElementById('sub-action-days').value) || 0;

        try {
            const resp = await fetch(`/api/admin/subscriptions/users/${userId}/manage`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action, days })
            });

            const data = await resp.json();

            if (resp.ok) {
                showToast(`${action.charAt(0).toUpperCase() + action.slice(1)}d subscription for user ${userId}.`, 'success', 'Subscription Updated');
                closeSubModal();
                loadTokens();
            } else {
                showToast(data.detail || 'Failed.', 'error', 'Update Failed');
            }
        } catch (err) {
            showToast('Error: ' + err.message, 'error', 'Network Error');
        }
    }

    async function copyLink(url) {
        try {
            await navigator.clipboard.writeText(url);
            showToast('Link copied!', 'success', 'Copied');
        } catch {
            prompt('Copy this link:', url);
        }
    }

    document.getElementById('assign-modal').addEventListener('click', function (e) {
        if (e.target === this) closeAssignModal();
    });

    document.getElementById('sub-action-modal').addEventListener('click', function (e) {
        if (e.target === this) closeSubModal();
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeAssignModal();
            closeSubModal();
        }
    });

    loadPlans();
    loadTokens();

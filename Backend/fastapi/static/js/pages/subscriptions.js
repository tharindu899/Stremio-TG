/* Page behavior: subscriptions */
let allUsers = [];
let subPage = 1;

function syncSubscriptionsChoice(selectId, triggerId) {
    const select = document.getElementById(selectId);
    const trigger = document.getElementById(triggerId);
    if (!select || !trigger) return;
    const selected = select.options[select.selectedIndex];
    trigger.querySelector('span').textContent = selected ? selected.textContent : 'Select';
}

async function openSubscriptionsChoice(selectId, title) {
    const select = document.getElementById(selectId);
    if (!select || typeof showChoiceDialog !== 'function') return;
    const value = await showChoiceDialog({
        title,
        subtitle: 'Choose one option to update the list instantly.',
        value: select.value,
        options: Array.from(select.options).map(option => ({ value: option.value, label: option.textContent }))
    });
    if (value === null) return;
    select.value = value;
    syncSubscriptionsChoice(selectId, `${selectId}-trigger`);
    select.dispatchEvent(new Event('change', { bubbles: true }));
}

function formatExpiry(expiryValue) {
    if (!expiryValue) return 'N/A';
    const d = new Date(expiryValue);
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

function getUserDisplayName(u) {
    let name = u.first_name || '';
    if (u.username) name += (name ? ' ' : '') + `(@${u.username})`;
    if (!name) name = `User ${u._id}`;
    return name;
}

function getStatusBadge(status) {
    return status === 'active'
        ? '<span class="metric-badge badge-active"><i class="fas fa-circle text-[8px]"></i> Active</span>'
        : '<span class="metric-badge badge-expired"><i class="fas fa-circle text-[8px]"></i> Expired</span>';
}

async function fetchPlans() {
    const container = document.getElementById('plans-container');
    container.innerHTML = `
        <div class="empty-state col-span-full text-center px-6 py-10 text-soft">
            <i class="fas fa-spinner fa-spin mr-2"></i> Loading plans...
        </div>
    `;
    try {
        const res = await fetch('/api/admin/subscriptions/plans');
        if (!res.ok) throw new Error('Failed to fetch plans');

        const data = await res.json();
        const plans = data.data || data.plans || [];

        if (!plans.length) {
            container.innerHTML = `
                <div class="empty-state col-span-full text-center px-6 py-10 text-soft">
                    <i class="fas fa-box-open text-2xl mb-3"></i>
                    <div class="font-semibold mb-1">No plans found</div>
                    <div class="text-sm">Create your first subscription plan.</div>
                </div>
            `;
            return;
        }

        container.innerHTML = plans.map(p => `
            <div class="plan-card p-5 sm:p-6">
                <div class="plan-actions absolute right-4 top-4 flex gap-2">
                    <button onclick="openPlanModal('${p._id}', ${p.days}, ${p.price})"
                        class="glass-btn rounded-full w-9 h-9 flex items-center justify-center" title="Edit plan">
                        <i class="fas fa-pen text-sm"></i>
                    </button>
                    <button onclick="deletePlan('${p._id}')"
                        class="glass-btn glass-btn-danger rounded-full w-9 h-9 flex items-center justify-center" title="Delete plan">
                        <i class="fas fa-trash text-sm"></i>
                    </button>
                </div>

                <div class="flex items-start gap-4">
                    <div class="w-14 h-14 rounded-2xl flex items-center justify-center shrink-0"
                         style="background: color-mix(in srgb, var(--primary) 16%, transparent); border: 1px solid color-mix(in srgb, var(--primary) 24%, transparent);">
                        <i class="fas fa-calendar-alt text-xl" style="color: var(--primary);"></i>
                    </div>

                    <div class="min-w-0">
                        <div class="text-sm font-semibold section-muted">${p.days} Days Plan</div>
                        <div class="mt-1 text-3xl font-extrabold section-title tracking-tight">₹${p.price}</div>
                        <div class="mt-3 inline-flex items-center gap-2 text-xs font-bold rounded-full px-3 py-1"
                             style="background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--text-sec); border: 1px solid color-mix(in srgb, var(--accent) 20%, transparent);">
                            <i class="fas fa-bolt" style="color: var(--accent);"></i>
                            Premium Access
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (err) {
        console.error(err);
        container.innerHTML = `
            <div class="empty-state col-span-full text-center px-6 py-10 text-soft">
                <i class="fas fa-triangle-exclamation mr-2"></i> Failed to load plans.
            </div>
        `;
    }
}

function openPlanModal(id = '', days = '', price = '') {
    document.getElementById('plan-id').value = id;
    document.getElementById('plan-days').value = days;
    document.getElementById('plan-price').value = price;
    document.getElementById('plan-modal-title').innerText = id ? 'Edit Plan' : 'Add New Plan';

    const modal = document.getElementById('plan-modal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.classList.add('overflow-hidden');
}

function closePlanModal() {
    const modal = document.getElementById('plan-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.classList.remove('overflow-hidden');
}

async function submitPlanForm(e) {
    e.preventDefault();

    const id = document.getElementById('plan-id').value;
    const payload = {
        days: parseInt(document.getElementById('plan-days').value),
        price: parseFloat(document.getElementById('plan-price').value)
    };

    try {
        const res = await fetch(id ? `/api/admin/subscriptions/plans/${id}` : '/api/admin/subscriptions/plans', {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error('Failed to save plan');

        closePlanModal();
        fetchPlans();
    } catch (err) {
        console.error(err);
        showToast('Failed to save plan.', 'error', 'Save Failed');
    }
}

async function deletePlan(id) {
    const ok = typeof showConfirmDialog === 'function'
        ? await showConfirmDialog({
            title: 'Delete plan',
            subtitle: 'This removes the selected subscription plan from your pricing list.',
            message: 'Delete this plan?',
            note: 'Existing subscribers are not deleted automatically.',
            confirmText: 'Delete plan',
            tone: 'danger'
          })
        : false;
    if (!ok) return;

    try {
        const res = await fetch(`/api/admin/subscriptions/plans/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed');
        fetchPlans();
    } catch (err) {
        console.error(err);
        showToast('Failed to delete plan.', 'error', 'Delete Failed');
    }
}

function getSubFiltered() {
    const q = document.getElementById('sub-search').value.toLowerCase().trim();
    const status = document.getElementById('sub-filter').value;

    return allUsers.filter(u => {
        const name = ((u.first_name || '') + ' ' + (u.username || '') + ' ' + (u._id || '')).toLowerCase();
        const matchQ = !q || name.includes(q);
        const matchStatus = status === 'all' || u.subscription_status === status;
        return matchQ && matchStatus;
    });
}

function renderDesktopRows(slice) {
    const tbody = document.getElementById('subscribers-tbody');

    if (!slice.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="px-6 py-10 text-center text-soft">
                    No users match your search.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = slice.map(u => {
        const expiry = formatExpiry(u.subscription_expiry);
        const name = getUserDisplayName(u);
        const safeName = name.replace(/'/g, "\'");
        const statusBadge = getStatusBadge(u.subscription_status);

        return `
            <tr>
                <td class="px-6 py-4">
                    <div class="font-semibold section-title">${name}</div>
                    <div class="text-xs text-soft mt-1">ID: ${u._id}</div>
                </td>
                <td class="px-6 py-4 text-center">${statusBadge}</td>
                <td class="px-6 py-4 text-center text-sm section-title">${expiry}</td>
                <td class="px-6 py-4">
                    <div class="flex justify-end gap-2 flex-wrap">
                        <button onclick="openUserModal(${u._id}, '${safeName}', 'extend')" class="action-chip glass-btn-success">Extend</button>
                        <button onclick="openUserModal(${u._id}, '${safeName}', 'reduce')" class="action-chip glass-btn-warning">Reduce</button>
                        <button onclick="openUserModal(${u._id}, '${safeName}', 'delete')" class="action-chip glass-btn-danger">Revoke</button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function renderMobileCards(slice) {
    const mobileWrap = document.getElementById('subscribers-mobile');

    if (!slice.length) {
        mobileWrap.innerHTML = `
            <div class="empty-state text-center px-4 py-8 text-soft">
                No users match your search.
            </div>
        `;
        return;
    }

    mobileWrap.innerHTML = slice.map(u => {
        const expiry = formatExpiry(u.subscription_expiry);
        const name = getUserDisplayName(u);
        const safeName = name.replace(/'/g, "\'");
        const statusBadge = getStatusBadge(u.subscription_status);

        return `
            <div class="mobile-user-card">
                <div class="flex items-start justify-between gap-3 mb-3">
                    <div class="min-w-0">
                        <div class="font-semibold section-title break-words">${name}</div>
                        <div class="text-xs text-soft mt-1 break-all">ID: ${u._id}</div>
                    </div>
                    <div class="shrink-0">${statusBadge}</div>
                </div>

                <div class="grid grid-cols-1 gap-3 mb-4">
                    <div class="rounded-2xl px-4 py-3" style="background: color-mix(in srgb, var(--bg) 55%, transparent); border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);">
                        <div class="text-[11px] uppercase tracking-[0.14em] text-soft font-bold mb-1">Expiry</div>
                        <div class="text-sm font-semibold section-title">${expiry}</div>
                    </div>
                </div>

                <div class="grid grid-cols-3 gap-2">
                    <button onclick="openUserModal(${u._id}, '${safeName}', 'extend')" class="action-chip glass-btn-success w-full">Extend</button>
                    <button onclick="openUserModal(${u._id}, '${safeName}', 'reduce')" class="action-chip glass-btn-warning w-full">Reduce</button>
                    <button onclick="openUserModal(${u._id}, '${safeName}', 'delete')" class="action-chip glass-btn-danger w-full">Revoke</button>
                </div>
            </div>
        `;
    }).join('');
}

function renderSubPage() {
    syncSubscriptionsChoice('sub-filter', 'sub-filter-trigger');
    syncSubscriptionsChoice('sub-page-size', 'sub-page-size-trigger');

    const filtered = getSubFiltered();
    const pageSize = parseInt(document.getElementById('sub-page-size').value);
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    if (subPage > totalPages) subPage = totalPages;

    const start = filtered.length ? (subPage - 1) * pageSize : 0;
    const slice = filtered.slice(start, start + pageSize);

    document.getElementById('sub-page-info').textContent =
        filtered.length
            ? `Showing ${start + 1}–${Math.min(start + pageSize, filtered.length)} of ${filtered.length}`
            : 'Showing 0 of 0';

    document.getElementById('sub-page-num').textContent = `Page ${subPage} / ${totalPages}`;

    const prevBtn = document.getElementById('sub-btn-prev');
    const nextBtn = document.getElementById('sub-btn-next');

    prevBtn.disabled = subPage <= 1;
    nextBtn.disabled = subPage >= totalPages;

    prevBtn.style.opacity = subPage <= 1 ? '0.45' : '1';
    nextBtn.style.opacity = subPage >= totalPages ? '0.45' : '1';

    renderDesktopRows(slice);
    renderMobileCards(slice);
}

function subChangePage(dir) {
    const filtered = getSubFiltered();
    const pageSize = parseInt(document.getElementById('sub-page-size').value);
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));

    subPage += dir;
    if (subPage < 1) subPage = 1;
    if (subPage > totalPages) subPage = totalPages;

    renderSubPage();
}

async function fetchSubscribers() {
    document.getElementById('subscribers-tbody').innerHTML = `
        <tr>
            <td colspan="4" class="px-6 py-8 text-center text-soft">
                <i class="fas fa-spinner fa-spin mr-2"></i> Loading...
            </td>
        </tr>
    `;

    document.getElementById('subscribers-mobile').innerHTML = `
        <div class="empty-state text-center px-4 py-8 text-soft">
            <i class="fas fa-spinner fa-spin mr-2"></i> Loading...
        </div>
    `;

    try {
        const res = await fetch('/api/admin/subscriptions/users');
        if (!res.ok) throw new Error('Failed to fetch users');

        const data = await res.json();
        allUsers = data.data || [];
        subPage = 1;
        renderSubPage();
    } catch (err) {
        console.error(err);

        document.getElementById('subscribers-tbody').innerHTML = `
            <tr>
                <td colspan="4" class="px-6 py-8 text-center text-soft">
                    <i class="fas fa-triangle-exclamation mr-2"></i> Failed to load users.
                </td>
            </tr>
        `;

        document.getElementById('subscribers-mobile').innerHTML = `
            <div class="empty-state text-center px-4 py-8 text-soft">
                <i class="fas fa-triangle-exclamation mr-2"></i> Failed to load users.
            </div>
        `;
    }
}

function openUserModal(userId, userName, action) {
    document.getElementById('manage-user-id').value = userId;
    document.getElementById('manage-action').value = action;

    let title = '';
    let desc = '';
    let btnClasses = 'glass-btn glass-btn-primary rounded-2xl px-5 py-3 text-sm font-bold';
    let showDays = true;

    if (action === 'extend') {
        title = 'Extend Subscription';
        desc = `Add extra days to <b>${userName}</b>'s subscription.`;
        document.getElementById('days-action-label').innerText = 'add';
        btnClasses = 'glass-btn glass-btn-success rounded-2xl px-5 py-3 text-sm font-bold';
    } else if (action === 'reduce') {
        title = 'Reduce Subscription';
        desc = `Subtract days from <b>${userName}</b>'s subscription.`;
        document.getElementById('days-action-label').innerText = 'subtract';
        btnClasses = 'glass-btn glass-btn-warning rounded-2xl px-5 py-3 text-sm font-bold';
    } else {
        title = 'Revoke Subscription';
        desc = `<b>Warning:</b> This will remove <b>${userName}</b>'s subscription access completely.`;
        showDays = false;
        btnClasses = 'glass-btn glass-btn-danger rounded-2xl px-5 py-3 text-sm font-bold';
    }

    document.getElementById('user-modal-title').innerText = title;
    document.getElementById('user-modal-desc').innerHTML = desc;
    document.getElementById('days-input-group').style.display = showDays ? 'block' : 'none';
    document.getElementById('btn-user-save').className = btnClasses;

    if (!showDays) {
        document.getElementById('manage-days').value = 0;
        document.getElementById('manage-days').removeAttribute('required');
    } else {
        document.getElementById('manage-days').setAttribute('required', 'required');
        if (!document.getElementById('manage-days').value || document.getElementById('manage-days').value === '0') {
            document.getElementById('manage-days').value = 30;
        }
    }

    const modal = document.getElementById('user-modal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.classList.add('overflow-hidden');
}

function closeUserModal() {
    const modal = document.getElementById('user-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.classList.remove('overflow-hidden');
}

async function submitUserForm(e) {
    e.preventDefault();

    const userId = document.getElementById('manage-user-id').value;
    const action = document.getElementById('manage-action').value;
    const days = document.getElementById('manage-days').value;

    try {
        const res = await fetch(`/api/admin/subscriptions/users/${userId}/manage`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, days: parseInt(days) || 0 })
        });

        if (!res.ok) throw new Error('Failed to update user');

        closeUserModal();
        showToast('Subscription updated successfully.', 'success', 'Updated');
        fetchSubscribers();
    } catch (err) {
        console.error(err);
        showToast('Failed to update user subscription.', 'error', 'Update Failed');
    }
}

document.addEventListener('click', (e) => {
    const planModal = document.getElementById('plan-modal');
    const userModal = document.getElementById('user-modal');

    if (e.target === planModal) closePlanModal();
    if (e.target === userModal) closeUserModal();
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closePlanModal();
        closeUserModal();
    }
});

document.addEventListener('DOMContentLoaded', () => {
    syncSubscriptionsChoice('sub-filter', 'sub-filter-trigger');
    syncSubscriptionsChoice('sub-page-size', 'sub-page-size-trigger');
    document.getElementById('sub-filter').addEventListener('change', () => syncSubscriptionsChoice('sub-filter', 'sub-filter-trigger'));
    document.getElementById('sub-page-size').addEventListener('change', () => syncSubscriptionsChoice('sub-page-size', 'sub-page-size-trigger'));
    fetchPlans();
    fetchSubscribers();
});

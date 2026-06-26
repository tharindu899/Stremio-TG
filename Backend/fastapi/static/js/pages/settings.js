/* Page behavior: settings */
function byId(id) {
    return document.getElementById(id);
}

function toggleSubFields() {
    const enabled = Boolean(byId('subscription')?.checked);
    byId('sub-fields')?.classList.toggle('is-hidden', !enabled);
}

function toggleGlobalSearchFields() {
    const enabled = Boolean(byId('global_search')?.checked);
    byId('global-search-fields')?.classList.toggle('is-hidden', !enabled);
}

function togglePwdVisibility() {
    const input = byId('admin_password');
    const icon = byId('eye-icon');
    if (!input || !icon) return;
    const isHidden = input.type === 'password';
    input.type = isHidden ? 'text' : 'password';
    icon.className = isHidden ? 'fa-solid fa-eye-slash' : 'fa-solid fa-eye';
}

function escapeHtmlAttr(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function addItem(listKey) {
    const newInput = byId(`${listKey}_new`);
    const container = byId(`${listKey}_items`);
    if (!newInput || !container) return;

    const value = newInput.value.trim();
    if (!value) return;

    const isNumeric = listKey === 'approver_ids';
    const item = document.createElement('div');
    item.className = 'multi-item';
    item.innerHTML = `
        <input type="${isNumeric ? 'number' : 'text'}" value="${escapeHtmlAttr(value)}" data-list="${listKey}">
        <button type="button" class="remove-btn" onclick="removeItem(this)" title="Remove"><i class="fa-solid fa-xmark"></i></button>
    `;
    container.appendChild(item);
    newInput.value = '';
    newInput.focus();
}

function removeItem(button) {
    button?.closest('.multi-item')?.remove();
}

function collectList(listKey) {
    const container = byId(`${listKey}_items`);
    if (!container) return [];
    return [...container.querySelectorAll('input[data-list]')]
        .map((input) => input.value.trim())
        .filter(Boolean);
}

function setSavingState(isSaving) {
    document.querySelectorAll('[data-save-settings]').forEach((button) => {
        button.disabled = isSaving;
    });
    const label = byId('save-label');
    if (label) label.textContent = isSaving ? 'Saving…' : 'Save changes';
}

async function saveSettings() {
    setSavingState(true);

    const payload = {
        replace_mode: Boolean(byId('replace_mode')?.checked),
        hide_catalog: Boolean(byId('hide_catalog')?.checked),
        admin_username: byId('admin_username')?.value.trim() || '',
        admin_password: byId('admin_password')?.value || '',
        tmdb_api: byId('tmdb_api')?.value.trim() || '',
        base_url: byId('base_url')?.value.trim() || '',
        upstream_repo: byId('upstream_repo')?.value.trim() || '',
        upstream_branch: byId('upstream_branch')?.value.trim() || '',
        auth_channels: collectList('auth_channels'),
        subscription: Boolean(byId('subscription')?.checked),
        subscription_group_id: parseInt(byId('subscription_group_id')?.value || '0', 10),
        subscription_url: byId('subscription_url')?.value.trim() || '',
        payment_instructions: byId('payment_instructions')?.value.trim() || '',
        payment_qr_url: byId('payment_qr_url')?.value.trim() || '',
        approver_ids: collectList('approver_ids').map(Number).filter(Number.isFinite),
        http_proxy_url: byId('http_proxy_url')?.value.trim() || '',
        show_proxy_and_non_proxy_both: Boolean(byId('show_proxy_and_non_proxy_both')?.checked),
        multi_tokens: collectList('multi_tokens'),
        extra_databases: collectList('extra_databases'),
        global_search: Boolean(byId('global_search')?.checked),
        global_search_channels: collectList('global_search_channels'),
    };

    // Empty fields are commonly caused by stale/browser-cached settings pages.
    // Keep the saved server value unless the user explicitly edits a non-empty value.
    [
        'tmdb_api', 'base_url', 'upstream_repo', 'upstream_branch',
        'http_proxy_url', 'subscription_url', 'payment_instructions', 'payment_qr_url',
    ].forEach((key) => {
        if (!payload[key]) delete payload[key];
    });

    try {
        const response = await fetch('/api/admin/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            showToast(data.detail || 'Settings could not be saved.', 'error', 'Save failed');
            return;
        }

        const revision = data.persistence?.revision;
        showToast(
            revision ? `Saved to MongoDB · revision ${revision}` : 'Settings saved and verified in MongoDB.',
            'success',
            'Saved'
        );
        const status = byId('settings-persistence-status');
        if (status && revision) {
            status.textContent = `Saved to MongoDB · revision ${revision}${data.persistence?.updated_at ? ` · ${new Date(data.persistence.updated_at).toLocaleString()}` : ''}`;
        }
        if (Array.isArray(data.preserved_empty_fields) && data.preserved_empty_fields.length) {
            showToast(`Kept existing saved values for: ${data.preserved_empty_fields.join(', ')}`, 'info', 'Protected settings');
        }
        for (const [subsystem, message] of Object.entries(data.reinit || {})) {
            showToast(`${capitalize(subsystem)}: ${message}`, 'info');
        }
        await refreshSettingsFromServer();
    } catch (error) {
        console.error('Settings save failed:', error);
        showToast('Network error — the app could not be reached.', 'error', 'Save failed');
    } finally {
        setSavingState(false);
    }
}

function capitalize(value) {
    return String(value || '').charAt(0).toUpperCase() + String(value || '').slice(1).replace(/_/g, ' ');
}

async function refreshSettingsFromServer() {
    try {
        const response = await fetch('/api/admin/settings');
        if (!response.ok) return;
        const data = await response.json().catch(() => ({}));
        renderSettings(data.settings || {});
    } catch (error) {
        console.error('Settings refresh failed:', error);
    }
}

function renderSettings(settings) {
    byId('replace_mode').checked = Boolean(settings.replace_mode);
    byId('hide_catalog').checked = Boolean(settings.hide_catalog);
    byId('subscription').checked = Boolean(settings.subscription);
    byId('show_proxy_and_non_proxy_both').checked = Boolean(settings.show_proxy_and_non_proxy_both);
    byId('global_search').checked = Boolean(settings.global_search);

    byId('admin_username').value = settings.admin_username || '';
    byId('admin_password').value = '';
    byId('tmdb_api').value = settings.tmdb_api || '';
    byId('base_url').value = settings.base_url || '';
    byId('upstream_repo').value = settings.upstream_repo || '';
    byId('upstream_branch').value = settings.upstream_branch || '';
    byId('subscription_group_id').value = settings.subscription_group_id || 0;
    byId('subscription_url').value = settings.subscription_url || '';
    byId('payment_instructions').value = settings.payment_instructions || '';
    byId('payment_qr_url').value = settings.payment_qr_url || '';
    byId('http_proxy_url').value = settings.http_proxy_url || '';

    rebuildSimpleList('auth_channels_items', settings.auth_channels, 'text');
    rebuildSimpleList('approver_ids_items', settings.approver_ids, 'number');
    rebuildSimpleList('multi_tokens_items', settings.multi_tokens, 'text');
    rebuildSimpleList('global_search_channels_items', settings.global_search_channels, 'text');
    rebuildDatabaseList(settings.database_list || []);

    const persistenceStatus = byId('settings-persistence-status');
    if (persistenceStatus && settings.settings_revision) {
        persistenceStatus.textContent = `Loaded from MongoDB · revision ${settings.settings_revision}${settings.updated_at ? ` · ${new Date(settings.updated_at).toLocaleString()}` : ''}`;
    }

    toggleSubFields();
    toggleGlobalSearchFields();
}

function rebuildSimpleList(containerId, values, inputType) {
    const container = byId(containerId);
    if (!container) return;
    const listKey = containerId.replace('_items', '');
    container.innerHTML = '';

    (values || []).forEach((value) => {
        const item = document.createElement('div');
        item.className = 'multi-item';
        item.innerHTML = `
            <input type="${inputType}" value="${escapeHtmlAttr(value)}" data-list="${listKey}">
            <button type="button" class="remove-btn" onclick="removeItem(this)" title="Remove"><i class="fa-solid fa-xmark"></i></button>
        `;
        container.appendChild(item);
    });
}

function rebuildDatabaseList(databaseList) {
    const container = byId('extra_databases_items');
    if (!container) return;
    container.innerHTML = '';

    databaseList.filter((entry) => !entry.locked).forEach((entry) => {
        const item = document.createElement('div');
        item.className = 'multi-item';
        item.innerHTML = `
            <input type="text" spellcheck="false" value="${escapeHtmlAttr(entry.full_uri || '')}" data-list="extra_databases">
            <span class="db-dot ${entry.connected ? 'is-connected' : 'is-disconnected'}" title="${entry.connected ? 'Connected' : 'Disconnected'}"></span>
            <button type="button" class="remove-btn" onclick="removeItem(this)" title="Remove last database"><i class="fa-solid fa-xmark"></i></button>
        `;
        container.appendChild(item);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    toggleSubFields();
    toggleGlobalSearchFields();
});

/* Catalog workspace · v3.6.1 · v3.5.8 catalog layout + revision-aware sync */
let catalogs = [];
let selectedCatalogId = null;
let catalogListExpanded = false;
let autoSyncPollTimer = null;
let autoCatalogSettings = null;

const html = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#039;');

const posterOrFallback = (item) => item?.poster || '/static/placeholder.svg';
const getSelectedCatalog = () => catalogs.find((catalog) => catalog._id === selectedCatalogId);

function updateStats() {
  const total = catalogs.length;
  const visible = catalogs.filter((catalog) => catalog.visible).length;
  const items = catalogs.reduce((sum, catalog) => sum + ((catalog.items || []).length), 0);
  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-visible').textContent = visible;
  document.getElementById('stat-items').textContent = items;
}

function emptyState(icon, title, message) {
  return `<div class="catalog-empty-state">
    <span class="catalog-empty-icon"><i class="fa-solid ${icon}"></i></span>
    <h4>${html(title)}</h4>
    <p>${html(message)}</p>
  </div>`;
}

function mediaCard(item, actionHtml) {
  const mediaType = item.media_type === 'tv' ? 'Series' : 'Movie';
  const genres = Array.isArray(item.genres) ? item.genres.slice(0, 2).join(' · ') : '';
  const title = html(item.title || 'Untitled');
  return `<article class="catalog-media-row">
    <img src="${html(posterOrFallback(item))}" class="catalog-media-poster" onerror="this.src='/static/placeholder.svg'" alt="${title}">
    <div class="catalog-media-copy">
      <div class="catalog-media-title-row"><h4 title="${title}">${title}</h4><span class="catalog-type-pill">${html(mediaType)}</span></div>
      <p>${html(mediaType)} · ${html(item.release_year || 'Unknown')} · TMDb ${html(item.tmdb_id || '—')}</p>
      ${genres ? `<small>${html(genres)}</small>` : ''}
      <div class="catalog-media-action">${actionHtml}</div>
    </div>
  </article>`;
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

async function loadCatalogs() {
  const box = document.getElementById('catalog-list');
  box.innerHTML = '<div class="catalog-skeleton"></div><div class="catalog-skeleton"></div>';
  try {
    const data = await request('/api/custom-catalogs');
    catalogs = data.catalogs || [];
    if (selectedCatalogId && !catalogs.some((catalog) => catalog._id === selectedCatalogId)) selectedCatalogId = null;
    updateStats();
    renderCatalogs();
    updateSelectedHeader();
  } catch (error) {
    box.innerHTML = emptyState('fa-circle-exclamation', 'Unable to load catalogs', error.message || 'Please refresh and try again.');
    showToast(error.message || 'Unable to load catalogs', 'error', 'Catalogs');
  }
}

function renderCatalogs() {
  const box = document.getElementById('catalog-list');
  const expandBtn = document.getElementById('catalog-expand-btn');
  const wrapper = document.getElementById('catalog-list-wrapper');

  if (!catalogs.length) {
    box.innerHTML = emptyState('fa-folder-open', 'No custom catalog yet', 'Create your first Stremio shelf above.');
    expandBtn?.classList.add('hidden');
    wrapper?.classList.remove('collapsed');
    return;
  }

  box.innerHTML = catalogs.map((catalog) => {
    const active = catalog._id === selectedCatalogId;
    const count = (catalog.items || []).length;
    const icon = catalog.auto ? 'fa-wand-magic-sparkles' : (catalog.visible ? 'fa-eye' : 'fa-eye-slash');
    return `<article class="catalog-list-card${active ? ' active' : ''}">
      <button class="catalog-select" type="button" onclick="selectCatalog('${html(catalog._id)}')">
        <span class="catalog-list-icon"><i class="fa-solid ${icon}"></i></span>
        <span class="catalog-list-copy"><strong>${html(catalog.name)}</strong><small>${count} title${count === 1 ? '' : 's'} · ${catalog.visible ? 'Visible in Stremio' : 'Hidden'}</small></span>
        ${catalog.auto ? '<span class="catalog-auto-tag">Auto</span>' : ''}
      </button>
      <label class="catalog-visibility" title="Toggle Stremio visibility">
        <input type="checkbox" ${catalog.visible ? 'checked' : ''} onchange="toggleVisibility('${html(catalog._id)}', this.checked)">
        <span aria-hidden="true"></span>
      </label>
    </article>`;
  }).join('');

  if (catalogs.length > 3) {
    expandBtn?.classList.remove('hidden');
    expandBtn.textContent = catalogListExpanded ? 'Show less' : 'Show all catalogs';
    wrapper?.classList.toggle('collapsed', !catalogListExpanded);
  } else {
    expandBtn?.classList.add('hidden');
    wrapper?.classList.remove('collapsed');
  }
}

function updateSelectedHeader() {
  const catalog = getSelectedCatalog();
  const workspace = document.getElementById('catalog-workspace');
  const guide = document.getElementById('catalog-empty-guide');
  const deleteBtn = document.getElementById('delete-catalog-btn');
  const visibilityPill = document.getElementById('selected-visibility-pill');
  const countPill = document.getElementById('selected-count-pill');

  if (!catalog) {
    workspace.classList.add('hidden');
    guide.classList.remove('hidden');
    deleteBtn.classList.add('hidden');
    visibilityPill.classList.add('hidden');
    countPill.classList.add('hidden');
    document.getElementById('selected-title').textContent = 'Select a catalog';
    document.getElementById('selected-subtitle').textContent = 'Choose a catalog from the list to add or remove titles.';
    return;
  }

  workspace.classList.remove('hidden');
  guide.classList.add('hidden');
  deleteBtn.classList.remove('hidden');
  visibilityPill.classList.remove('hidden');
  countPill.classList.remove('hidden');
  visibilityPill.textContent = catalog.visible ? 'Visible in Stremio' : 'Hidden from Stremio';
  countPill.textContent = `${(catalog.items || []).length} title${(catalog.items || []).length === 1 ? '' : 's'}`;
  document.getElementById('selected-title').textContent = catalog.name || 'Selected catalog';
  document.getElementById('selected-subtitle').textContent = catalog.visible
    ? 'This shelf appears in the Stremio catalog screen.'
    : 'This shelf is private in the WebUI and hidden from Stremio.';
}

async function createCatalog(event) {
  event.preventDefault();
  const name = document.getElementById('catalog-name').value.trim();
  const visible = document.getElementById('catalog-visible').checked;
  if (!name) return showToast('Catalog name is required.', 'error', 'Catalogs');
  try {
    await request('/api/custom-catalogs', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name, visible}) });
    document.getElementById('catalog-name').value = '';
    showToast('Catalog created.', 'success', 'Catalogs');
    await loadCatalogs();
  } catch (error) { showToast(error.message || 'Failed to create catalog.', 'error', 'Catalogs'); }
}

async function toggleVisibility(id, visible) {
  const catalog = catalogs.find((item) => item._id === id);
  try {
    await request(`/api/custom-catalogs/${id}`, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: catalog?.name, visible}) });
    await loadCatalogs();
  } catch (error) { showToast(error.message || 'Failed to update visibility.', 'error', 'Catalogs'); }
}

async function selectCatalog(id) {
  selectedCatalogId = id;
  renderCatalogs();
  updateSelectedHeader();
  await loadCatalogItems();
}

async function searchMedia() {
  if (!selectedCatalogId) return showToast('Select a catalog first.', 'error', 'Catalogs');
  const query = document.getElementById('search-query').value.trim();
  const mediaType = document.getElementById('search-media-type').value;
  if (!query) return showToast('Type a title to search.', 'error', 'Catalogs');
  const wrap = document.getElementById('search-results-wrap');
  const box = document.getElementById('search-results');
  wrap.classList.remove('hidden');
  box.innerHTML = '<div class="catalog-skeleton"></div><div class="catalog-skeleton"></div>';
  try {
    const data = await request(`/api/custom-catalogs/search-media?query=${encodeURIComponent(query)}&media_type=${mediaType}`);
    const results = data.results || [];
    box.innerHTML = results.length
      ? results.map((item) => mediaCard(item, `<button class="btn-ui btn-primary catalog-row-action" type="button" onclick="addItem(${item.tmdb_id}, ${item.db_index}, '${item.media_type}')"><i class="fa-solid fa-plus"></i><span>Add</span></button>`)).join('')
      : emptyState('fa-magnifying-glass', 'No title found', 'Try a shorter title or change the media type.');
  } catch (error) { box.innerHTML = emptyState('fa-circle-exclamation', 'Search failed', error.message || 'Please try again.'); }
}

function clearSearchResults() {
  document.getElementById('search-results-wrap').classList.add('hidden');
  document.getElementById('search-results').innerHTML = '';
}

async function addItem(tmdbId, dbIndex, mediaType) {
  try {
    const data = await request(`/api/custom-catalogs/${selectedCatalogId}/items`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tmdb_id: tmdbId, db_index: dbIndex, media_type: mediaType}) });
    showToast(data.message || 'Title added.', 'success', 'Catalogs');
    await loadCatalogs();
    await loadCatalogItems();
  } catch (error) { showToast(error.message || 'Failed to add title.', 'error', 'Catalogs'); }
}

async function loadCatalogItems() {
  if (!selectedCatalogId) return;
  const box = document.getElementById('catalog-items');
  box.innerHTML = '<div class="catalog-skeleton"></div><div class="catalog-skeleton"></div>';
  try {
    const data = await request(`/api/custom-catalogs/${selectedCatalogId}/items?page_size=100`);
    const items = data.items || [];
    box.innerHTML = items.length
      ? items.map((item) => mediaCard(item, `<button class="btn-ui btn-danger catalog-row-action" type="button" onclick="removeItem(${item.tmdb_id}, ${item.db_index}, '${item.media_type}')"><i class="fa-solid fa-trash"></i><span>Remove</span></button>`)).join('')
      : emptyState('fa-box-open', 'No titles added yet', 'Use the search above to add media to this catalog.');
  } catch (error) { box.innerHTML = emptyState('fa-circle-exclamation', 'Unable to load titles', error.message || 'Please try again.'); }
}

async function removeItem(tmdbId, dbIndex, mediaType) {
  try {
    const data = await request(`/api/custom-catalogs/${selectedCatalogId}/items?tmdb_id=${tmdbId}&db_index=${dbIndex}&media_type=${mediaType}`, { method: 'DELETE' });
    showToast(data.message || 'Title removed.', 'success', 'Catalogs');
    await loadCatalogs();
    await loadCatalogItems();
  } catch (error) { showToast(error.message || 'Failed to remove title.', 'error', 'Catalogs'); }
}

async function deleteSelectedCatalog() {
  if (!selectedCatalogId) return;
  const confirmed = typeof showConfirmDialog === 'function'
    ? await showConfirmDialog({
        title: 'Delete catalog',
        subtitle: 'This removes only the catalog shelf.',
        message: 'Delete this catalog?',
        note: 'Titles remain safe in your media library.',
        confirmText: 'Delete catalog',
        tone: 'danger',
      })
    : window.confirm('Delete this catalog? Titles will remain in your media library.');
  if (!confirmed) return;
  try {
    await request(`/api/custom-catalogs/${selectedCatalogId}`, { method: 'DELETE' });
    selectedCatalogId = null;
    clearSearchResults();
    updateSelectedHeader();
    showToast('Catalog deleted.', 'success', 'Catalogs');
    await loadCatalogs();
  } catch (error) { showToast(error.message || 'Failed to delete catalog.', 'error', 'Catalogs'); }
}

function autoChoiceCount() {
  return document.querySelectorAll('.auto-setting-checkbox:checked').length;
}

function updateAutoSelectionSummary() {
  const summary = document.getElementById('auto-selection-summary');
  if (!summary) return;
  const selected = autoChoiceCount();
  summary.textContent = selected ? `${selected} shelf${selected === 1 ? '' : 's'} selected` : 'No shelves selected';
  summary.classList.toggle('empty', selected === 0);
}

function setAllAutoSettings(enabled) {
  document.querySelectorAll('.auto-setting-checkbox').forEach((box) => { box.checked = Boolean(enabled); });
  updateAutoSelectionSummary();
}

async function loadAutoCatalogSettings() {
  const box = document.getElementById('auto-settings-list');
  if (!box) return;
  try {
    const data = await request('/api/custom-catalogs/auto-sync/settings');
    autoCatalogSettings = data.settings || {};
    const definitions = autoCatalogSettings.definitions || [];
    if (!definitions.length) {
      box.innerHTML = emptyState('fa-sliders', 'No automatic options', 'No auto catalog rules are available yet.');
      return;
    }

    const groups = definitions.reduce((output, item) => {
      (output[item.group] ||= []).push(item);
      return output;
    }, {});

    // Keep the compact v3.5.8 accordion cards. The sync backend is still the
    // revision-aware v3.5.9 implementation, so old media is reclassified after
    // a saved selection changes.
    box.innerHTML = Object.entries(groups).map(([group, items]) => `<article class="auto-group-card">
      <button type="button" class="auto-group-head" onclick="toggleAutoGroup(this.closest('.auto-group-card'))">
        <span><strong>${html(group)}</strong><small>${items.length} option${items.length === 1 ? '' : 's'}</small></span>
        <i class="fa-solid fa-chevron-down" aria-hidden="true"></i>
      </button>
      <div class="auto-group-items"><div>
        ${items.map((item) => `<label class="auto-setting-row">
          <span>${html(item.name)}</span>
          <input type="checkbox" class="auto-setting-checkbox" value="${html(item.key)}" ${item.enabled ? 'checked' : ''}>
          <i aria-hidden="true"></i>
        </label>`).join('')}
      </div></div>
    </article>`).join('');
  } catch (error) {
    box.innerHTML = emptyState('fa-circle-exclamation', 'Could not load options', error.message || 'Please refresh and try again.');
  }
}

async function saveAutoCatalogSettings() {
  const button = document.getElementById('save-auto-settings-btn');
  const original = button?.innerHTML || '';
  const enabledKeys = [...document.querySelectorAll('.auto-setting-checkbox:checked')].map((element) => element.value);
  if (!enabledKeys.length) {
    showToast('Choose at least one automatic shelf before saving.', 'error', 'Catalogs');
    return;
  }
  try {
    if (button) { button.disabled = true; button.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving…'; }
    const data = await request('/api/custom-catalogs/auto-sync/settings', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enabled_keys: enabledKeys}),
    });
    autoCatalogSettings = data.settings || autoCatalogSettings;
    showToast(data.message || 'Choices saved. Catalog sync started.', 'success', 'Catalogs');
    await Promise.all([loadAutoCatalogSettings(), loadAutoSyncStatus()]);
  } catch (error) {
    showToast(error.message || 'Failed to save choices.', 'error', 'Catalogs');
  } finally {
    if (button) { button.disabled = false; button.innerHTML = original; }
  }
}

async function loadAutoSyncStatus() {
  const pill = document.getElementById('auto-sync-status');
  const syncBtn = document.getElementById('auto-sync-btn');
  const rebuildBtn = document.getElementById('auto-rebuild-btn');
  const saveBtn = document.getElementById('save-auto-settings-btn');
  if (!pill) return;

  try {
    const data = await request('/api/custom-catalogs/auto-sync/status');
    const status = data.status || {};
    const settings = data.settings || autoCatalogSettings || {};
    autoCatalogSettings = settings;
    const mode = status.mode === 'full_rebuild' ? 'Full rebuild' : 'Quick sync';

    if (status.running) {
      pill.textContent = `${mode} · ${status.scanned || 0} scanned · ${status.classified || 0} matched`;
      [syncBtn, rebuildBtn, saveBtn].forEach((button) => { if (button) button.disabled = true; });
      if (!autoSyncPollTimer) autoSyncPollTimer = setInterval(loadAutoSyncStatus, 2500);
      return;
    }

    [syncBtn, rebuildBtn, saveBtn].forEach((button) => { if (button) button.disabled = false; });
    if (autoSyncPollTimer) {
      clearInterval(autoSyncPollTimer);
      autoSyncPollTimer = null;
      await loadCatalogs();
    }

    if (!settings.configured) {
      pill.textContent = 'Choose shelves to begin';
    } else if (!(settings.enabled_keys || []).length) {
      pill.textContent = 'No automatic shelves selected';
    } else if (status.error) {
      pill.textContent = `${mode} failed`;
    } else if (status.finished_at) {
      pill.textContent = status.message || `${mode} complete · ${status.catalogs || 0} shelves`;
    } else {
      pill.textContent = `Ready · ${(settings.enabled_keys || []).length} shelves selected`;
    }
  } catch {
    pill.textContent = 'Status unavailable';
  }
}

async function runAutoSync(fullRebuild = false) {
  const enabled = autoCatalogSettings?.enabled_keys || [];
  if (!enabled.length) {
    showToast('Save at least one automatic shelf before syncing.', 'error', 'Catalogs');
    return;
  }

  const button = document.getElementById(fullRebuild ? 'auto-rebuild-btn' : 'auto-sync-btn');
  const other = document.getElementById(fullRebuild ? 'auto-sync-btn' : 'auto-rebuild-btn');
  const original = button?.innerHTML || '';
  try {
    if (button) { button.disabled = true; button.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${fullRebuild ? 'Rebuilding…' : 'Syncing…'}`; }
    if (other) other.disabled = true;
    const data = await request(`/api/custom-catalogs/auto-sync?full_rebuild=${fullRebuild ? 'true' : 'false'}`, { method: 'POST' });
    showToast(data.result?.message || data.message || 'Catalog task started.', 'info', fullRebuild ? 'Full rebuild' : 'Quick sync');
    await loadAutoSyncStatus();
  } catch (error) {
    showToast(error.message || 'Auto sync failed.', 'error', 'Catalogs');
  } finally {
    if (button) button.innerHTML = original;
    await loadAutoSyncStatus();
  }
}

function toggleAutoGroup(card) { card?.classList.toggle('expanded'); }

function toggleCatalogExpand() {
  catalogListExpanded = !catalogListExpanded;
  document.getElementById('catalog-list-wrapper')?.classList.toggle('collapsed', !catalogListExpanded);
  const button = document.getElementById('catalog-expand-btn');
  if (button) button.textContent = catalogListExpanded ? 'Show less' : 'Show all catalogs';
}

document.addEventListener('DOMContentLoaded', () => { loadCatalogs(); loadAutoSyncStatus(); loadAutoCatalogSettings(); });

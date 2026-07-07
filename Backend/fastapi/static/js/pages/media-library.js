/* Media library: reliable pagination, search and card actions. */
const PAGE_SIZE = 24;
let currentPage = 1;
let currentSearch = '';
let isLoading = false;
let activeRequest = null;
let requestSequence = 0;
const mediaType = window.TG_STREMIO_PAGE?.mediaType === 'tv' ? 'tv' : 'movie';

function getElement(id) {
    return document.getElementById(id);
}

function showLoading() {
    isLoading = true;
    getElement('loading').classList.remove('hidden');
    getElement('media-grid').classList.add('hidden');
    getElement('no-results').classList.add('hidden');
    getElement('pagination').classList.add('hidden');
    getElement('media-info').classList.add('hidden');
    getElement('error-display').classList.add('hidden');
}

function hideLoading() {
    isLoading = false;
    getElement('loading').classList.add('hidden');
    getElement('media-grid').classList.remove('hidden');
}

function showError(message) {
    getElement('error-message').textContent = message;
    getElement('error-display').classList.remove('hidden');
    getElement('loading').classList.add('hidden');
    getElement('media-grid').classList.add('hidden');
    getElement('no-results').classList.add('hidden');
    getElement('pagination').classList.add('hidden');
    getElement('media-info').classList.add('hidden');
}

function normalisePage(value) {
    const parsed = Number.parseInt(String(value), 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function updateLocation(page, search) {
    const url = new URL(window.location.href);
    url.searchParams.set('media_type', mediaType);
    url.searchParams.set('page', String(page));
    if (search) {
        url.searchParams.set('search', search);
    } else {
        url.searchParams.delete('search');
    }
    window.history.replaceState({}, '', `${url.pathname}${url.search}`);
}

function scrollToResults() {
    const target = getElement('media-grid');
    const top = target.getBoundingClientRect().top + window.scrollY - 88;
    window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
}

async function loadMedia(page = 1, search = '', options = {}) {
    const requestedPage = normalisePage(page);
    const requestedSearch = String(search || '').trim();
    const scrollAfterLoad = Boolean(options.scrollAfterLoad);

    activeRequest?.abort();
    const controller = new AbortController();
    activeRequest = controller;
    const requestId = ++requestSequence;

    showLoading();

    try {
        const params = new URLSearchParams({
            media_type: mediaType,
            page: String(requestedPage),
            page_size: String(PAGE_SIZE),
            search: requestedSearch,
        });
        const response = await fetch(`/api/media/list?${params.toString()}`, {
            method: 'GET',
            credentials: 'same-origin',
            headers: { Accept: 'application/json' },
            signal: controller.signal,
        });

        if (requestId !== requestSequence) return;

        if (!response.ok) {
            if (response.status === 401) {
                window.location.assign('/login');
                return;
            }
            const body = await response.json().catch(() => ({}));
            throw new Error(body.detail || `Server responded with ${response.status}`);
        }

        const data = await response.json();
        if (requestId !== requestSequence) return;

        const renderedPage = normalisePage(data.current_page || requestedPage);
        currentPage = renderedPage;
        currentSearch = requestedSearch;
        updateLocation(renderedPage, requestedSearch);

        hideLoading();
        const grid = getElement('media-grid');
        const mediaKey = mediaType === 'movie' ? 'movies' : 'tv_shows';
        const mediaItems = Array.isArray(data[mediaKey]) ? data[mediaKey] : [];

        if (mediaItems.length === 0) {
            grid.innerHTML = '';
            getElement('no-results').classList.remove('hidden');
            getElement('pagination').classList.add('hidden');
            getElement('media-info').classList.add('hidden');
            return;
        }

        getElement('no-results').classList.add('hidden');
        grid.innerHTML = mediaItems.map(createMediaCard).join('');
        updatePagination(renderedPage, Number(data.total_pages || 1));
        updateMediaInfo(data);
        if (scrollAfterLoad) scrollToResults();
    } catch (error) {
        if (error.name === 'AbortError' || requestId !== requestSequence) return;
        console.error('Error loading media:', error);
        hideLoading();
        showError(`Failed to load ${mediaType}s: ${error.message}`);
        if (typeof showToast === 'function') {
            showToast(`Failed to load ${mediaType}s.`, 'error', 'Load Error');
        }
    } finally {
        if (requestId === requestSequence) {
            activeRequest = null;
        }
    }
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[character]));
}

function subtitleBadge(item) {
    const count = Number(item.subtitle_count || 0);
    const languages = Array.isArray(item.subtitle_languages) ? item.subtitle_languages : [];
    if (!count) return '';
    const names = languages.map(language => language?.name || language?.code).filter(Boolean);
    const visible = names.slice(0, 2).map(escapeHtml);
    const extra = names.length > 2 ? ` +${names.length - 2}` : '';
    const label = visible.length ? `${visible.join(' · ')}${extra}` : `${count} subtitle${count === 1 ? '' : 's'}`;
    const tooltip = escapeHtml(names.join(', ') || `${count} linked subtitle${count === 1 ? '' : 's'}`);
    return `<span title="${tooltip}" class="subtitle-tag"><i class="fa-solid fa-closed-captioning"></i><span>SUB · ${label}</span></span>`;
}

function createMediaCard(item) {
    const rawTitle = item.title || item.name || 'Unknown Title';
    const title = escapeHtml(rawTitle);
    const year = escapeHtml(item.release_year || 'Unknown');
    const poster = escapeHtml(item.poster || '/static/placeholder.svg');
    const subtitlePosterBadge = subtitleBadge(item);
    const subtitleCardBadge = subtitleBadge(item);
    const kind = mediaType === 'movie' ? 'Movie' : 'Series';
    const tmdbId = escapeHtml(item.tmdb_id ?? '');
    const dbIndex = escapeHtml(item.db_index ?? '');

    return `
      <article class="media-card">
        <div class="media-visual">
          <img src="${poster}" alt="${title}" class="media-poster" data-fallback="/static/placeholder.svg" loading="lazy">
          <span class="media-year"><i class="fa-regular fa-calendar"></i>${year}</span>
          ${subtitlePosterBadge ? `<span class="media-subs">${subtitlePosterBadge}</span>` : ''}
          <span class="media-type">${kind}</span>
        </div>
        <div class="media-body">
          <h3 title="${title}">${title}</h3>
          <div class="media-meta"><span>DB #${dbIndex || '-'}</span><span>${kind}</span></div>
          <div class="media-subtitle-row">${subtitleCardBadge || ''}</div>
          <div class="media-actions">
            <a href="/media/edit?tmdb_id=${encodeURIComponent(item.tmdb_id)}&db_index=${encodeURIComponent(item.db_index)}&media_type=${encodeURIComponent(mediaType)}" class="media-edit" title="Manage ${title}" aria-label="Manage ${title}"><i class="fa-solid fa-pen"></i><span>Manage</span></a>
            <button type="button" data-action="delete-media" data-tmdb-id="${tmdbId}" data-db-index="${dbIndex}" data-title="${title}" class="media-remove" title="Remove ${title}" aria-label="Remove ${title}"><i class="fa-solid fa-trash"></i></button>
          </div>
        </div>
      </article>`;
}

function updatePagination(page, totalPages) {
    const pagination = getElement('pagination');
    const paginationInner = getElement('pagination-inner');
    const current = normalisePage(page);
    const total = Math.max(0, Number.parseInt(String(totalPages), 10) || 0);

    if (total <= 1) {
        pagination.classList.add('hidden');
        paginationInner.innerHTML = '';
        return;
    }

    const button = (label, target, { active = false, disabled = false, extra = '', ariaLabel = '' } = {}) =>
        `<button type="button" class="pagination-btn${active ? ' pagination-active' : ''}${extra ? ` ${extra}` : ''}" data-page="${target}" ${active ? 'aria-current="page"' : ''} ${ariaLabel ? `aria-label="${ariaLabel}"` : ''} ${disabled ? 'disabled' : ''}>${label}</button>`;
    const gap = '<span class="pagination-gap" aria-hidden="true">…</span>';
    const pages = new Set([1, total, current - 1, current, current + 1]);
    const sortedPages = [...pages].filter(pageNumber => pageNumber >= 1 && pageNumber <= total).sort((a, b) => a - b);
    const parts = [
        button('<i class="fa-solid fa-chevron-left"></i><span>Prev</span>', Math.max(1, current - 1), {
            disabled: current <= 1,
            extra: 'pagination-prev',
            ariaLabel: 'Previous page',
        }),
    ];

    let previous = 0;
    for (const pageNumber of sortedPages) {
        if (previous && pageNumber - previous > 1) parts.push(gap);
        parts.push(button(String(pageNumber), pageNumber, {
            active: pageNumber === current,
            ariaLabel: `Page ${pageNumber}`,
        }));
        previous = pageNumber;
    }

    parts.push(button('<span>Next</span><i class="fa-solid fa-chevron-right"></i>', Math.min(total, current + 1), {
        disabled: current >= total,
        extra: 'pagination-next',
        ariaLabel: 'Next page',
    }));

    paginationInner.innerHTML = parts.join('');
    pagination.classList.remove('hidden');
}

function updateMediaInfo(data) {
    const mediaInfo = getElement('media-info');
    const resultsInfo = getElement('results-info');
    const dbInfo = getElement('db-info');
    const totalCount = Number(data.total_count || 0);
    const current = normalisePage(data.current_page || currentPage);
    const startItem = totalCount === 0 ? 0 : ((current - 1) * PAGE_SIZE) + 1;
    const endItem = Math.min(current * PAGE_SIZE, totalCount);

    resultsInfo.textContent = `Showing ${startItem}-${endItem} of ${totalCount} ${mediaType}s`;
    const databases = Array.isArray(data.databases_checked) ? data.databases_checked : [];
    dbInfo.textContent = databases.length ? `Databases checked: ${databases.join(', ')}` : '';
    mediaInfo.classList.remove('hidden');
}

function searchMedia() {
    loadMedia(1, getElement('search-input').value, { scrollAfterLoad: true });
}

function clearSearch() {
    getElement('search-input').value = '';
    loadMedia(1, '', { scrollAfterLoad: true });
}

function retryLoad() {
    loadMedia(currentPage, currentSearch);
}

async function deleteMedia(buttonElement) {
    const tmdbId = buttonElement.dataset.tmdbId;
    const dbIndex = buttonElement.dataset.dbIndex;
    const title = buttonElement.dataset.title || 'this title';

    if (!tmdbId || !dbIndex) {
        if (typeof showToast === 'function') showToast('This media item has no valid database reference.', 'error', 'Delete Failed');
        return;
    }

    const confirmed = await confirmAction({
        title: 'Delete media',
        subtitle: 'This cannot be undone.',
        message: `Delete “${title}”?`,
        confirmText: 'Delete media',
        tone: 'danger',
    });
    if (!confirmed) return;

    buttonElement.disabled = true;
    try {
        const response = await fetch(`/api/media/delete?tmdb_id=${encodeURIComponent(tmdbId)}&db_index=${encodeURIComponent(dbIndex)}&media_type=${encodeURIComponent(mediaType)}`, {
            method: 'DELETE',
            credentials: 'same-origin',
            headers: { Accept: 'application/json' },
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || `Server responded with ${response.status}`);
        }
        if (typeof showToast === 'function') showToast(`“${title}” deleted successfully`, 'success', 'Deleted');
        loadMedia(currentPage, currentSearch);
    } catch (error) {
        console.error('Error deleting media:', error);
        if (typeof showToast === 'function') showToast(`Could not delete “${title}”: ${error.message}`, 'error', 'Delete Failed');
        buttonElement.disabled = false;
    }
}

function bindPageEvents() {
    getElement('pagination-inner').addEventListener('click', event => {
        const button = event.target.closest('button[data-page]');
        if (!button || button.disabled) return;
        const targetPage = normalisePage(button.dataset.page);
        if (targetPage !== currentPage) {
            loadMedia(targetPage, currentSearch, { scrollAfterLoad: true });
        }
    });

    const grid = getElement('media-grid');
    grid.addEventListener('click', event => {
        const button = event.target.closest('[data-action="delete-media"]');
        if (button) deleteMedia(button);
    });
    grid.addEventListener('error', event => {
        const image = event.target;
        if (!image.matches?.('.media-poster')) return;
        const fallback = image.dataset.fallback;
        if (fallback && image.src !== new URL(fallback, window.location.origin).href) image.src = fallback;
    }, true);

    getElement('media-search-button').addEventListener('click', searchMedia);
    getElement('media-clear-button').addEventListener('click', clearSearch);
    getElement('media-retry-button').addEventListener('click', retryLoad);
    getElement('media-empty-reset-button').addEventListener('click', clearSearch);

    getElement('search-input').addEventListener('keydown', event => {
        if (event.key === 'Enter') {
            event.preventDefault();
            searchMedia();
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const initialSearch = params.get('search') || '';
    const initialPage = normalisePage(params.get('page'));
    getElement('search-input').value = initialSearch;
    bindPageEvents();
    loadMedia(initialPage, initialSearch);
});

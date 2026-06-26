/* Page behavior: media-library */
let currentPage = 1;
    let currentSearch = '';
    let isLoading = false;
    const mediaType = window.TG_STREMIO_PAGE.mediaType;

    function showLoading() {
        isLoading = true;
        document.getElementById('loading').classList.remove('hidden');
        document.getElementById('media-grid').classList.add('hidden');
        document.getElementById('no-results').classList.add('hidden');
        document.getElementById('pagination').classList.add('hidden');
        document.getElementById('media-info').classList.add('hidden');
        document.getElementById('error-display').classList.add('hidden');
    }

    function hideLoading() {
        isLoading = false;
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('media-grid').classList.remove('hidden');
    }

    function showError(message) {
        document.getElementById('error-message').textContent = message;
        document.getElementById('error-display').classList.remove('hidden');
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('media-grid').classList.add('hidden');
        document.getElementById('no-results').classList.add('hidden');
        document.getElementById('pagination').classList.add('hidden');
        document.getElementById('media-info').classList.add('hidden');
    }

    async function loadMedia(page = 1, search = '') {
        if (isLoading) return;

        showLoading();
        currentPage = page;
        currentSearch = search;

        try {
            const url = `/api/media/list?media_type=${mediaType}&page=${page}&page_size=24&search=${encodeURIComponent(search)}`;
            const response = await fetch(url, {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                if (response.status === 401) {
                    window.location.href = '/login';
                    return;
                }
                throw new Error(`Server responded with ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            hideLoading();

            const grid = document.getElementById('media-grid');
            const mediaKey = mediaType === 'movie' ? 'movies' : 'tv_shows';
            const mediaItems = data[mediaKey] || [];

            if (mediaItems.length === 0) {
                grid.innerHTML = '';
                document.getElementById('no-results').classList.remove('hidden');
                document.getElementById('pagination').classList.add('hidden');
                document.getElementById('media-info').classList.add('hidden');
                return;
            }

            document.getElementById('no-results').classList.add('hidden');
            grid.innerHTML = mediaItems.map(item => createMediaCard(item)).join('');
            updatePagination(data.current_page || page, data.total_pages || 1);
            updateMediaInfo(data);

        } catch (error) {
            console.error('Error loading media:', error);
            hideLoading();
            showError(`Failed to load ${mediaType}s: ${error.message}`);
            showToast(`Failed to load ${mediaType}s.`, 'error', 'Load Error');
        }
    }


    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>'"]/g, character => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
        }[character]));
    }

    function subtitleBadge(item, poster = false) {
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
        const safeTitle = escapeHtml(rawTitle);
        const subtitlePosterBadge = subtitleBadge(item, true);
        const subtitleCardBadge = subtitleBadge(item);
        const kind = mediaType === 'movie' ? 'Movie' : 'Series';
        return `
          <article class="media-card">
            <div class="media-visual">
              <img src="${poster}" alt="${title}" class="media-poster" onerror="this.src='/static/placeholder.svg'" loading="lazy">
              <span class="media-year"><i class="fa-regular fa-calendar"></i>${year}</span>
              ${subtitlePosterBadge ? `<span class="media-subs">${subtitlePosterBadge}</span>` : ''}
              <span class="media-type">${kind}</span>
            </div>
            <div class="media-body">
              <h3 title="${title}">${title}</h3>
              <div class="media-meta"><span>DB #${escapeHtml(item.db_index ?? '-')}</span><span>${kind}</span></div>
              <div class="media-subtitle-row">${subtitleCardBadge || ''}</div>
              <div class="media-actions">
                <a href="/media/edit?tmdb_id=${encodeURIComponent(item.tmdb_id)}&db_index=${encodeURIComponent(item.db_index)}&media_type=${encodeURIComponent(mediaType)}" class="media-edit" title="Manage ${title}" aria-label="Manage ${title}"><i class="fa-solid fa-pen"></i><span>Manage</span></a>
                <button onclick="deleteMedia(this)" data-tmdb-id="${escapeHtml(item.tmdb_id)}" data-db-index="${escapeHtml(item.db_index ?? '')}" data-title="${safeTitle}" class="media-remove" title="Remove ${title}" aria-label="Remove ${title}"><i class="fa-solid fa-trash"></i></button>
              </div>
            </div>
          </article>`;
    }

    function updatePagination(currentPage, totalPages) {
        const pagination = document.getElementById('pagination');
        const paginationInner = document.getElementById('pagination-inner');

        if (totalPages <= 1) {
            pagination.classList.add('hidden');
            paginationInner.innerHTML = '';
            return;
        }

        pagination.classList.remove('hidden');
        const button = (label, target, active = false, disabled = false, extra = '') =>
            `<button type="button" class="pagination-btn${active ? ' pagination-active' : ''}${extra ? ` ${extra}` : ''}" ${disabled ? 'disabled' : ''} onclick="loadMedia(${target}, ${JSON.stringify(currentSearch)})">${label}</button>`;
        const gap = '<span class="pagination-gap" aria-hidden="true">…</span>';
        const parts = [];
        parts.push(button('<i class="fa-solid fa-chevron-left"></i><span>Prev</span>', Math.max(1, currentPage - 1), false, currentPage <= 1, 'pagination-prev'));

        const startPage = Math.max(1, currentPage - 1);
        const endPage = Math.min(totalPages, currentPage + 1);
        if (startPage > 1) {
            parts.push(button('1', 1));
            if (startPage > 2) parts.push(gap);
        }
        for (let pageNumber = startPage; pageNumber <= endPage; pageNumber++) {
            parts.push(button(String(pageNumber), pageNumber, pageNumber === currentPage));
        }
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) parts.push(gap);
            parts.push(button(String(totalPages), totalPages));
        }
        parts.push(button('<span>Next</span><i class="fa-solid fa-chevron-right"></i>', Math.min(totalPages, currentPage + 1), false, currentPage >= totalPages, 'pagination-next'));
        paginationInner.innerHTML = parts.join('');
    }

    function updateMediaInfo(data) {
        const mediaInfo = document.getElementById('media-info');
        const resultsInfo = document.getElementById('results-info');
        const dbInfo = document.getElementById('db-info');

        const totalCount = data.total_count || 0;
        const pageSize = 24;
        const current = data.current_page || 1;
        const startItem = totalCount === 0 ? 0 : ((current - 1) * pageSize) + 1;
        const endItem = Math.min(current * pageSize, totalCount);

        resultsInfo.textContent = `Showing ${startItem}-${endItem} of ${totalCount} ${mediaType}s`;

        if (data.databases_checked && data.databases_checked.length > 0) {
            dbInfo.textContent = `Databases checked: ${data.databases_checked.join(', ')}`;
        } else {
            dbInfo.textContent = '';
        }

        mediaInfo.classList.remove('hidden');
    }

    function searchMedia() {
        const searchInput = document.getElementById('search-input');
        const search = searchInput.value.trim();
        loadMedia(1, search);
    }

    function clearSearch() {
        document.getElementById('search-input').value = '';
        loadMedia(1, '');
    }

    function retryLoad() {
        loadMedia(currentPage, currentSearch);
    }

    async function deleteMedia(buttonElement) {
    const tmdbId = buttonElement.getAttribute('data-tmdb-id');
    const dbIndex = buttonElement.getAttribute('data-db-index');
    const title = buttonElement.getAttribute('data-title');

    const confirmed = await confirmAction({ title: 'Delete media', subtitle: 'This cannot be undone.', message: `Delete “${title}”?`, confirmText: 'Delete media', tone: 'danger' });
    if (!confirmed) return;

    try {
        const response = await fetch(`/api/media/delete?tmdb_id=${encodeURIComponent(tmdbId)}&db_index=${encodeURIComponent(dbIndex)}&media_type=${encodeURIComponent(mediaType)}`, {
            method: 'DELETE',
            credentials: 'same-origin',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            showToast(`"${title}" deleted successfully`, 'success', 'Deleted');
            loadMedia(currentPage, currentSearch); // Refresh grid
        } else {
            const error = await response.json().catch(() => ({}));
            showToast(error.detail || `Error deleting "${title}"`, 'error', 'Delete Failed');
        }
    } catch (error) {
        console.error('Error deleting media:', error);
        showToast(`Error deleting "${title}": ${error.message}`, 'error', 'Network Error');
    }
}

    document.addEventListener('DOMContentLoaded', () => {
        loadMedia();

        const searchInput = document.getElementById('search-input');

        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                searchMedia();
            }
        });

        let searchTimeout;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            const searchValue = e.target.value.trim();

            if (searchValue.length === 0) {
                searchTimeout = setTimeout(() => {
                    loadMedia(1, '');
                }, 250);
            }
        });
    });

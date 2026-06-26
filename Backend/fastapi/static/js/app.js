(() => {
  'use strict';

  const byId = (id) => document.getElementById(id);
  const route = document.body?.dataset?.route || window.location.pathname;
  const overlay = byId('overlay');
  const mobileDrawer = byId('mobileDrawer');
  const mobileNavBtn = byId('mobileNavBtn');
  const mobileDrawerClose = byId('mobileDrawerClose');
  const userButton = byId('user-btn');
  const userDropdown = byId('user-dropdown');
  const topbarPageTitle = byId('topbarPageTitle');

  let drawerOpen = false;
  let userOpen = false;

  function setOverlay(open) {
    if (!overlay) return;
    overlay.classList.toggle('is-visible', Boolean(open));
    overlay.setAttribute('aria-hidden', open ? 'false' : 'true');
  }

  function syncHeaderLayer() {
    document.querySelector('.studio-header')?.classList.toggle('menu-open', userOpen);
  }

  // The drawer needs a scrim. The compact profile menu does not; using a shared
  // scrim on mobile previously hid the profile menu behind the overlay.
  function syncOverlay() {
    setOverlay(drawerOpen);
    syncHeaderLayer();
  }

  function closeDrawer() {
    if (!mobileDrawer) return;
    drawerOpen = false;
    mobileDrawer.classList.remove('is-open');
    mobileDrawer.setAttribute('aria-hidden', 'true');
    syncOverlay();
  }

  function openDrawer() {
    if (!mobileDrawer) return;
    closeUserMenu();
    drawerOpen = true;
    mobileDrawer.classList.add('is-open');
    mobileDrawer.setAttribute('aria-hidden', 'false');
    syncOverlay();
  }

  function closeUserMenu() {
    if (!userDropdown || !userButton) return;
    userOpen = false;
    userDropdown.classList.remove('is-open');
    userButton.setAttribute('aria-expanded', 'false');
    syncOverlay();
  }

  function toggleUserMenu(event) {
    event?.stopPropagation();
    if (!userDropdown || !userButton) return;
    if (userOpen) { closeUserMenu(); return; }
    closeDrawer();
    userOpen = true;
    userDropdown.classList.add('is-open');
    userButton.setAttribute('aria-expanded', 'true');
    syncOverlay();
  }

  function isRouteActive(linkRoute) {
    if (!linkRoute) return false;
    if (linkRoute === '/') return route === '/';
    return route === linkRoute || route.startsWith(`${linkRoute}/`) || (linkRoute === '/media/manage' && route === '/media/edit');
  }

  function setActiveNavigation() {
    const links = [...document.querySelectorAll('[data-nav-link]')];
    let activeLinks = links.filter((link) => isRouteActive(link.getAttribute('href')));
    if (!activeLinks.length) activeLinks = links.filter((link) => link.getAttribute('href') === '/');

    links.forEach((link) => {
      const active = activeLinks.includes(link);
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');

      // Keep the current page recognisable but quiet: a small colour change
      // and aria-current are enough; do not add labels or large highlight cards.
      link.querySelector('.nav-current')?.remove();
    });

    const active = activeLinks[0];
    if (topbarPageTitle && active) {
      const label = active.querySelector('span')?.textContent?.trim() || active.getAttribute('data-tooltip') || 'Overview';
      topbarPageTitle.textContent = label;
    }
  }

  function revealCurrentDrawerLink() {
    const activeLink = mobileDrawer?.querySelector('.mobile-panel-link.active');
    if (!activeLink) return;
    window.setTimeout(() => activeLink.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 80);
  }

  function registerOnlineOnlyPwa() {
    // Registration is intentionally silent: Chrome exposes its own install
    // action in the browser menu, while this app never shows an install popup.
    if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
    navigator.serviceWorker.register('/service-worker.js', { scope: '/' }).catch(() => {});
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  window.escapeHtml = window.escapeHtml || escapeHtml;
  window.showToast = window.showToast || function showToast(message, type = 'info', title = '') {
    const container = byId('toast-container');
    if (!container) return;
    const icon = type === 'success' ? 'fa-circle-check' : type === 'error' ? 'fa-triangle-exclamation' : 'fa-circle-info';
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span class="toast-icon"><i class="fa-solid ${icon}"></i></span><div class="toast-copy">${title ? `<strong>${escapeHtml(title)}</strong>` : ''}<span>${escapeHtml(message)}</span></div>`;
    container.appendChild(toast);
    window.setTimeout(() => { toast.classList.add('toast-leave'); window.setTimeout(() => toast.remove(), 220); }, 3200);
  };

  document.addEventListener('DOMContentLoaded', () => {
    setActiveNavigation();
    registerOnlineOnlyPwa();
    mobileNavBtn?.addEventListener('click', () => { openDrawer(); revealCurrentDrawerLink(); mobileNavBtn.setAttribute('aria-expanded', 'true'); });
    mobileDrawerClose?.addEventListener('click', () => { closeDrawer(); mobileNavBtn?.setAttribute('aria-expanded', 'false'); });
    userButton?.addEventListener('click', toggleUserMenu);
    overlay?.addEventListener('click', () => { closeDrawer(); mobileNavBtn?.setAttribute('aria-expanded', 'false'); closeUserMenu(); });
    userDropdown?.addEventListener('click', (event) => event.stopPropagation());
    document.addEventListener('click', (event) => {
      if (!userDropdown?.contains(event.target) && !userButton?.contains(event.target)) closeUserMenu();
    });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') { closeDrawer(); mobileNavBtn?.setAttribute('aria-expanded', 'false'); closeUserMenu(); } });
    window.addEventListener('resize', () => { if (window.innerWidth > 900) closeDrawer(); });
  });
})();


(() => {
  let helperCount = 0;
  let choiceResolver = null;
  let confirmResolver = null;

  function ensureHelpers() {
    if (document.getElementById('app-helper-root')) return;
    const root = document.createElement('div');
    root.id = 'app-helper-root';
    root.innerHTML = `
      <div id="app-choice-shell" class="app-helper-shell" aria-hidden="true">
        <div class="app-helper-card" role="dialog" aria-modal="true" aria-labelledby="app-choice-title">
          <div class="app-helper-handle"></div>
          <div class="app-helper-head">
            <div>
              <span class="app-helper-kicker">Quick picker</span>
              <h3 id="app-choice-title">Choose</h3>
              <p id="app-choice-copy" class="app-helper-copy">Select an option below.</p>
            </div>
            <button type="button" id="app-choice-close" class="app-helper-close" aria-label="Close chooser"><i class="fa-solid fa-xmark"></i></button>
          </div>
          <div id="app-choice-list" class="app-choice-list"></div>
        </div>
      </div>
      <div id="app-confirm-shell" class="app-helper-shell" aria-hidden="true">
        <div class="app-helper-card" role="dialog" aria-modal="true" aria-labelledby="app-confirm-title">
          <div class="app-helper-handle"></div>
          <div class="app-helper-head">
            <div>
              <span class="app-helper-kicker">Confirm action</span>
              <h3 id="app-confirm-title">Please confirm</h3>
              <p id="app-confirm-copy" class="app-helper-copy">Review this action before continuing.</p>
            </div>
            <button type="button" id="app-confirm-close" class="app-helper-close" aria-label="Close confirmation"><i class="fa-solid fa-xmark"></i></button>
          </div>
          <div class="app-confirm-body">
            <p id="app-confirm-message"></p>
            <p id="app-confirm-note" class="app-confirm-note"></p>
          </div>
          <div class="app-confirm-actions">
            <button type="button" id="app-confirm-cancel" class="app-confirm-btn">Cancel</button>
            <button type="button" id="app-confirm-accept" class="app-confirm-btn primary">Confirm</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(root);

    const choiceShell = document.getElementById('app-choice-shell');
    const confirmShell = document.getElementById('app-confirm-shell');

    function closeChoice(value = null) {
      choiceShell.classList.remove('is-open');
      choiceShell.setAttribute('aria-hidden', 'true');
      unlockHelpers();
      if (choiceResolver) { const resolve = choiceResolver; choiceResolver = null; resolve(value); }
    }
    function closeConfirm(value = false) {
      confirmShell.classList.remove('is-open');
      confirmShell.setAttribute('aria-hidden', 'true');
      unlockHelpers();
      if (confirmResolver) { const resolve = confirmResolver; confirmResolver = null; resolve(value); }
    }

    document.getElementById('app-choice-close').addEventListener('click', () => closeChoice(null));
    document.getElementById('app-confirm-close').addEventListener('click', () => closeConfirm(false));
    document.getElementById('app-confirm-cancel').addEventListener('click', () => closeConfirm(false));
    document.getElementById('app-confirm-accept').addEventListener('click', () => closeConfirm(true));
    choiceShell.addEventListener('click', (event) => { if (event.target === choiceShell) closeChoice(null); });
    confirmShell.addEventListener('click', (event) => { if (event.target === confirmShell) closeConfirm(false); });

    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      if (choiceShell.classList.contains('is-open')) closeChoice(null);
      if (confirmShell.classList.contains('is-open')) closeConfirm(false);
    });

    window.__appCloseChoiceDialog = closeChoice;
    window.__appCloseConfirmDialog = closeConfirm;
  }

  function lockHelpers() {
    helperCount += 1;
    document.body.classList.add('overflow-hidden');
  }
  function unlockHelpers() {
    helperCount = Math.max(0, helperCount - 1);
    if (!helperCount) document.body.classList.remove('overflow-hidden');
  }

  window.showChoiceDialog = function showChoiceDialog({ title = 'Choose', subtitle = 'Select an option below.', options = [], value = null } = {}) {
    ensureHelpers();
    const shell = document.getElementById('app-choice-shell');
    const list = document.getElementById('app-choice-list');
    document.getElementById('app-choice-title').textContent = title;
    document.getElementById('app-choice-copy').textContent = subtitle;
    list.innerHTML = options.map((option) => {
      const active = String(option.value) === String(value);
      return `<button type="button" class="app-choice-item ${active ? 'is-active' : ''}" data-choice-value="${window.escapeHtml(option.value)}">
        <span><strong>${window.escapeHtml(option.label || option.value)}</strong>${option.description ? `<small>${window.escapeHtml(option.description)}</small>` : ''}</span>
        <span class="app-choice-mark"><i class="fa-solid fa-circle-dot"></i></span>
      </button>`;
    }).join('');
    list.querySelectorAll('[data-choice-value]').forEach((btn) => {
      btn.addEventListener('click', () => window.__appCloseChoiceDialog(btn.getAttribute('data-choice-value')));
    });
    shell.classList.add('is-open');
    shell.setAttribute('aria-hidden', 'false');
    lockHelpers();
    return new Promise((resolve) => { choiceResolver = resolve; });
  };

  window.confirmAction = window.confirmAction || async function confirmAction(options = {}) {
    if (typeof window.showConfirmDialog !== 'function') return false;
    return window.showConfirmDialog(options);
  };

  window.showConfirmDialog = function showConfirmDialog({ title = 'Please confirm', subtitle = 'Review this action before continuing.', message = '', note = '', confirmText = 'Confirm', cancelText = 'Cancel', tone = 'primary' } = {}) {
    ensureHelpers();
    const shell = document.getElementById('app-confirm-shell');
    document.getElementById('app-confirm-title').textContent = title;
    document.getElementById('app-confirm-copy').textContent = subtitle;
    document.getElementById('app-confirm-message').textContent = message;
    const noteEl = document.getElementById('app-confirm-note');
    noteEl.textContent = note || '';
    noteEl.style.display = note ? 'block' : 'none';
    document.getElementById('app-confirm-cancel').textContent = cancelText;
    const accept = document.getElementById('app-confirm-accept');
    accept.textContent = confirmText;
    accept.className = `app-confirm-btn ${tone === 'danger' ? 'danger' : 'primary'}`;
    shell.classList.add('is-open');
    shell.setAttribute('aria-hidden', 'false');
    lockHelpers();
    return new Promise((resolve) => { confirmResolver = resolve; });
  };
})();

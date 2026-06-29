/* ===== SPA Router & App Initialization ===== */

function navigate(page, params) {
    // Abort any in-flight streaming request when leaving the chat page
    if (page !== 'chat' && AppState.currentAbortController) {
        AppState.currentAbortController.abort();
        AppState.currentAbortController = null;
        AppState.isStreaming = false;
        const btnSend = document.getElementById('btn-send');
        if (btnSend) btnSend.disabled = false;
    }

    const pages = document.querySelectorAll('.page');
    pages.forEach(p => p.classList.add('hidden'));

    AppState.currentPage = page;
    const _p = document.getElementById(`page-${page}`); if (_p) _p.classList.remove('hidden');

    if (page === 'config') {
        loadConfigPage();
    } else if (page === 'people') {
        if (typeof initPeoplePage === 'function') initPeoplePage();
    } else if (page === 'chat') {
        initChatPage();
    }

    // Update hash
    if (params && params.sessionId) {
        window.location.hash = `#/chat/${params.sessionId}`;
    } else {
        window.location.hash = `#/${page}`;
    }
}

function handleHashChange() {
    const hash = window.location.hash.slice(1) || '/chat';
    const parts = hash.split('/');

    if (parts[1] === 'config') {
        navigate('config');
    } else if (parts[1] === 'people') {
        navigate('people');
    } else if (parts[1] === 'chat' && parts[2]) {
        // Set currentSessionId first so initChatPage (called by navigate) picks it up
        // and loads the session exactly once — no separate loadSession call needed.
        AppState.currentSessionId = parts[2];
        navigate('chat', { sessionId: parts[2] });
    } else {
        navigate('chat');
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const icon = document.getElementById('sidebar-toggle-icon');
    AppState.sidebarCollapsed = !AppState.sidebarCollapsed;
    if (AppState.sidebarCollapsed) {
        sidebar.classList.add('collapsed');
        if (icon) icon.textContent = '▶';
    } else {
        sidebar.classList.remove('collapsed');
        if (icon) icon.textContent = '☰';
    }
}

function closeModal(modalId) {
    const _m = document.getElementById(modalId); if (_m) _m.classList.add('hidden');
    const _mo = document.getElementById('modal-overlay'); if (_mo) _mo.classList.add('hidden');
}

function openModal(modalId) {
    const _mo2 = document.getElementById('modal-overlay'); if (_mo2) _mo2.classList.remove('hidden');
    const _m2 = document.getElementById(modalId); if (_m2) _m2.classList.remove('hidden');
}

// Close popups on outside click
document.addEventListener('click', (e) => {
    const popup = document.getElementById('shishen-popup');
    if (popup && !popup.classList.contains('hidden') && !e.target.closest('.shishen-popup') && !e.target.closest('.hidden-stem-item') && !e.target.closest('.heavenly-stem')) {
        popup.classList.add('hidden');
    }
});

// Initialize
window.addEventListener('DOMContentLoaded', () => {
    loadConfig().then(() => {
        handleHashChange();
    });
});

window.addEventListener('hashchange', handleHashChange);

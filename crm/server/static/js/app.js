/* OCTO CRM APM frontend helpers */
/* Restore native fetch — APM RUM agent patches fetch/XHR and can break API calls */
const _fetch = window.__nativeFetch || window.fetch.bind(window);

function _uuid() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

function getSessionId() {
    const existing = localStorage.getItem('octo-session-id');
    if (existing) return existing;
    const created = _uuid();
    localStorage.setItem('octo-session-id', created);
    return created;
}

async function checkSession() {
    try {
        const resp = await _fetch('/api/auth/session');
        const data = await resp.json();
        window.OCTO_SESSION = data;
        window.dispatchEvent(new CustomEvent('octo:session', {detail: data}));
        const userInfo = document.getElementById('user-info');
        const authBtn = document.getElementById('auth-btn');
        if (data.authenticated && userInfo) {
            userInfo.textContent = `${data.username} (${data.role})`;
            if (authBtn) {
                authBtn.textContent = 'Logout';
                authBtn.href = '#';
                authBtn.className = 'btn-logout';
                authBtn.onclick = async (event) => {
                    event.preventDefault();
                    await _fetch('/api/auth/logout', {method: 'POST'});
                    window.location.href = '/login';
                };
            }
        } else if (userInfo) {
            userInfo.textContent = 'Not logged in';
            if (authBtn) {
                authBtn.textContent = 'Login';
                authBtn.href = '/login';
                authBtn.className = 'btn-login';
                authBtn.onclick = null;
            }
        }
    } catch (error) {
        window.OCTO_SESSION = {authenticated: false};
        window.dispatchEvent(new CustomEvent('octo:session', {detail: {authenticated: false}}));
        console.error('Session check failed:', error);
    }
}

async function trackPageView() {
    try {
        const navEntry = performance.getEntriesByType('navigation')[0];
        const loadTime = navEntry ? Math.round(navEntry.duration) : Math.round(performance.now());
        await _fetch('/api/analytics/track', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                page: window.location.pathname,
                visitor_region: Intl.DateTimeFormat().resolvedOptions().timeZone || '',
                load_time_ms: loadTime,
                referrer: document.referrer || '',
                session_id: getSessionId(),
            }),
        });
    } catch (error) {
        console.error('Page tracking failed:', error);
    }
}

window.addEventListener('load', () => {
    checkSession();
    trackPageView();
});

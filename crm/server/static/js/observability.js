/**
 * Frontend Observability — Web Vitals, JS errors, user journey tracking.
 *
 * Sends telemetry events to /api/observability/frontend via sendBeacon
 * (non-blocking, fire-and-forget). Events include trace correlation for
 * linking frontend performance to backend spans.
 */
(() => {
    'use strict';

    const _fetch = window.__nativeFetch || window.fetch.bind(window);
    const viewId = (crypto.randomUUID ? crypto.randomUUID() :
        'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        }));

    const sessionId = localStorage.getItem('octo-session-id') || '';

    function emit(type, payload) {
        const body = JSON.stringify({
            type: type,
            page: location.pathname,
            session_id: sessionId,
            view_id: viewId,
            ts: Date.now(),
            payload: payload
        });
        // sendBeacon is non-blocking and survives page unload
        if (navigator.sendBeacon) {
            const payload = new Blob([body], {type: 'application/json'});
            navigator.sendBeacon('/api/observability/frontend', payload);
        } else {
            _fetch('/api/observability/frontend', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: body,
                keepalive: true
            }).catch(() => {});
        }
    }

    // ── JS Error Tracking ─────────────────────────────────────────
    window.addEventListener('error', (event) => {
        emit('js_error', {
            message: event.message || 'Unknown error',
            source: event.filename || '',
            line: event.lineno || 0,
            column: event.colno || 0,
            stack: (event.error && event.error.stack) ? event.error.stack.slice(0, 500) : ''
        });
    });

    window.addEventListener('unhandledrejection', (event) => {
        emit('promise_rejection', {
            reason: String(event.reason).slice(0, 300)
        });
    });

    // ── Web Vitals (lightweight inline measurement) ───────────────
    // Uses PerformanceObserver API directly — no external library needed.

    // Largest Contentful Paint (LCP)
    try {
        const lcpObserver = new PerformanceObserver((list) => {
            const entries = list.getEntries();
            const last = entries[entries.length - 1];
            if (last) {
                emit('web_vital', { name: 'LCP', value: Math.round(last.startTime) });
            }
        });
        lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });
    } catch (e) { /* unsupported browser */ }

    // First Input Delay (FID) / Interaction to Next Paint (INP)
    try {
        let maxInp = 0;
        const inpObserver = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                const dur = entry.duration || entry.processingEnd - entry.startTime;
                if (dur > maxInp) maxInp = dur;
            }
        });
        inpObserver.observe({ type: 'event', buffered: true, durationThreshold: 16 });

        // Report INP on page hide (captures the worst interaction)
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden' && maxInp > 0) {
                emit('web_vital', { name: 'INP', value: Math.round(maxInp) });
            }
        });
    } catch (e) { /* unsupported browser */ }

    // Cumulative Layout Shift (CLS)
    try {
        let clsValue = 0;
        const clsObserver = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                if (!entry.hadRecentInput) {
                    clsValue += entry.value;
                }
            }
        });
        clsObserver.observe({ type: 'layout-shift', buffered: true });

        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden' && clsValue > 0) {
                emit('web_vital', { name: 'CLS', value: Math.round(clsValue * 1000) / 1000 });
            }
        });
    } catch (e) { /* unsupported browser */ }

    // Time to First Byte (TTFB)
    try {
        const navEntry = performance.getEntriesByType('navigation')[0];
        if (navEntry && navEntry.responseStart) {
            emit('web_vital', { name: 'TTFB', value: Math.round(navEntry.responseStart) });
        }
    } catch (e) { /* unsupported browser */ }

    // ── User Journey Tracking ─────────────────────────────────────
    // Click any element with data-journey="step_name" to emit a journey event.
    document.addEventListener('click', (event) => {
        const target = event.target.closest('[data-journey]');
        if (!target) return;
        emit('journey_step', {
            step: target.dataset.journey,
            label: (target.dataset.label || target.textContent || '').trim().slice(0, 80)
        });
    });

    // ── Navigation Tracking ───────────────────────────────────────
    // Track client-side navigation for SPA-like behavior.
    let lastPath = location.pathname;
    const navObserver = new MutationObserver(() => {
        if (location.pathname !== lastPath) {
            lastPath = location.pathname;
            emit('navigation', { to: lastPath });
        }
    });
    navObserver.observe(document.body, { childList: true, subtree: true });

    // ── API Call Tracking ─────────────────────────────────────────
    // Wrap fetch to capture API latency and failures from the frontend perspective.
    const originalFetch = _fetch;
    window.__nativeFetch = async function(...args) {
        const url = typeof args[0] === 'string' ? args[0] :
                    (args[0] instanceof Request ? args[0].url : '');

        // Only track API calls, not observability endpoint itself
        if (!url.includes('/api/') || url.includes('/api/observability/')) {
            return originalFetch.apply(this, args);
        }

        const start = performance.now();
        try {
            const response = await originalFetch.apply(this, args);
            const duration = Math.round(performance.now() - start);
            if (response.status >= 400 || duration > 2000) {
                emit('frontend_api', {
                    url: new URL(url, location.origin).pathname,
                    status: response.status,
                    duration_ms: duration,
                    slow: duration > 2000
                });
            }
            return response;
        } catch (err) {
            emit('frontend_api', {
                url: new URL(url, location.origin).pathname,
                status: 0,
                duration_ms: Math.round(performance.now() - start),
                error: err.message
            });
            throw err;
        }
    };
    // Also update the module-level _fetch alias used by app.js
    window._fetch = window.__nativeFetch;
})();

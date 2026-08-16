(() => {
  'use strict';

  const VERSION = '4.0.0';
  const READ_ONLY = new Set([
    'admin.get', 'campaigns.get', 'campaigns.quote', 'catalog.get', 'catalog.quote_order',
    'dashboard.get', 'documents.get', 'engagement.get', 'network.get', 'network.quote',
    'orders.get', 'owner.catalog', 'owner.get', 'owner.operations', 'owner.orders',
    'owner.recent_operations', 'owner.runtime_settings', 'owner.star_payments',
    'owner.system_health', 'owner.user_lookup', 'profile.get', 'referrals.get', 'wallet.get'
  ]);
  const pendingMutationKeys = new Map();
  const originalFetch = window.fetch.bind(window);

  const now = () => Date.now();
  const makeId = () => {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    const random = Math.random().toString(36).slice(2);
    return `b4-${Date.now().toString(36)}-${random}`;
  };

  function cleanPending() {
    const cutoff = now();
    for (const [key, value] of pendingMutationKeys.entries()) {
      if (!value || value.expiresAt <= cutoff) pendingMutationKeys.delete(key);
    }
  }

  function fingerprint(operation, payload) {
    let text = '';
    try {
      text = JSON.stringify(payload || {});
    } catch (_) {
      text = String(payload || '');
    }
    let hash = 2166136261;
    const source = `${operation}|${text}`;
    for (let index = 0; index < source.length; index += 1) {
      hash ^= source.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return `${operation}|${(hash >>> 0).toString(16)}`;
  }

  function banner(message, kind = 'info', ttlMs = 3500) {
    let node = document.getElementById('boostoraV4Banner');
    if (!node) {
      node = document.createElement('div');
      node.id = 'boostoraV4Banner';
      Object.assign(node.style, {
        position: 'fixed', left: '50%', top: 'calc(68px + env(safe-area-inset-top))', zIndex: '150',
        transform: 'translateX(-50%)', width: 'min(calc(100% - 24px), 620px)', padding: '10px 13px',
        borderRadius: '14px', backdropFilter: 'blur(16px)', boxShadow: '0 12px 32px rgba(0,0,0,.3)',
        font: '700 12px/1.35 system-ui,-apple-system,"Segoe UI",sans-serif', textAlign: 'center',
        transition: 'opacity .18s ease', pointerEvents: 'none'
      });
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.style.color = kind === 'error' ? '#ffd0d0' : kind === 'ok' ? '#b8ffe0' : '#fff0c7';
    node.style.background = kind === 'error' ? 'rgba(82,20,30,.94)' : kind === 'ok' ? 'rgba(18,72,51,.94)' : 'rgba(54,35,78,.94)';
    node.style.border = kind === 'error' ? '1px solid rgba(255,116,116,.45)' : kind === 'ok' ? '1px solid rgba(71,223,160,.4)' : '1px solid rgba(243,180,71,.35)';
    node.style.opacity = '1';
    clearTimeout(node._boostoraTimer);
    if (ttlMs > 0) {
      node._boostoraTimer = setTimeout(() => { node.style.opacity = '0'; }, ttlMs);
    }
  }

  function setConnectivityState() {
    if (!navigator.onLine) banner('Нет соединения. Действия не потеряются — повтори после восстановления сети.', 'error', 0);
    else {
      const node = document.getElementById('boostoraV4Banner');
      if (node && node.style.opacity !== '0') banner('Соединение восстановлено.', 'ok', 1800);
    }
  }

  window.fetch = async (input, init = {}) => {
    let requestInit = init || {};
    let mutationFingerprint = '';
    let mutationKey = '';
    let isMiniAppQuery = false;

    try {
      const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
      const method = String(requestInit.method || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
      isMiniAppQuery = method === 'POST' && url.pathname === '/api/miniapp/query';

      if (isMiniAppQuery && typeof requestInit.body === 'string') {
        const body = JSON.parse(requestInit.body);
        const operation = String(body.operation || '').trim().toLowerCase();
        if (operation && !READ_ONLY.has(operation)) {
          cleanPending();
          mutationFingerprint = fingerprint(operation, body.payload || {});
          const previous = pendingMutationKeys.get(mutationFingerprint);
          mutationKey = previous && previous.expiresAt > now() ? previous.key : makeId();
          pendingMutationKeys.set(mutationFingerprint, {key: mutationKey, expiresAt: now() + 180000});
          if (!body.request_id && !body.idempotency_key) body.request_id = mutationKey;
          const headers = new Headers(requestInit.headers || {});
          headers.set('X-Boostora-Client', VERSION);
          requestInit = {...requestInit, headers, body: JSON.stringify(body)};
        }
      }
    } catch (_) {
      // Compatibility first: malformed/non-JSON fetches continue untouched.
    }

    try {
      const response = await originalFetch(input, requestInit);
      if (mutationFingerprint) pendingMutationKeys.delete(mutationFingerprint);
      if (isMiniAppQuery && response.status === 429) {
        try {
          const data = await response.clone().json();
          const seconds = Math.max(1, Number(data.retry_after || 1));
          banner(`Слишком много действий подряд. Повтори через ${seconds} сек.`, 'info', Math.min(8000, seconds * 1000));
        } catch (_) {
          banner('Слишком много действий подряд. Повтори чуть позже.', 'info', 3500);
        }
      }
      return response;
    } catch (error) {
      if (mutationFingerprint && mutationKey) {
        // Keep the same key only after a transport failure. If the server completed
        // the mutation but the response was lost, a manual retry will be replayed
        // instead of executing the financial/task action twice.
        pendingMutationKeys.set(mutationFingerprint, {key: mutationKey, expiresAt: now() + 180000});
      }
      if (!navigator.onLine) setConnectivityState();
      throw error;
    }
  };

  document.documentElement.dataset.boostoraClient = VERSION;
  window.addEventListener('offline', setConnectivityState);
  window.addEventListener('online', setConnectivityState);
  window.addEventListener('pageshow', setConnectivityState);
})();

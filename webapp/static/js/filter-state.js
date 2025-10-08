(function (global) {
  const win = global || window;

  function getLocationComponents() {
    const { pathname, search, hash } = win.location;
    const normalizedHash = typeof hash === 'string' && hash.startsWith('#') ? hash.slice(1) : hash || '';
    return {
      pathname: pathname || '',
      search: search || '',
      hash: normalizedHash,
    };
  }

  function getParams() {
    const { hash } = getLocationComponents();
    return new URLSearchParams(hash);
  }

  function applyParams(params) {
    const nextHash = params.toString();
    const { pathname, search, hash } = getLocationComponents();
    if (nextHash === hash) {
      return;
    }
    const baseUrl = `${pathname}${search}`;
    const nextUrl = nextHash ? `${baseUrl}#${nextHash}` : baseUrl;
    try {
      win.history.replaceState(null, '', nextUrl);
    } catch (error) {
      // Fallback for environments where replaceState is not available.
      win.location.replace(nextUrl);
    }
  }

  function shouldRemoveValue(value) {
    if (value === null || value === undefined) {
      return true;
    }
    if (typeof value === 'string') {
      return value.length === 0;
    }
    if (Array.isArray(value)) {
      return value.length === 0;
    }
    if (typeof value === 'object') {
      return Object.keys(value).length === 0;
    }
    return false;
  }

  function readSection(key) {
    if (!key) {
      return null;
    }
    const params = getParams();
    const raw = params.get(key);
    if (raw === null) {
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch (error) {
      return raw;
    }
  }

  function writeSection(key, value) {
    if (!key) {
      return;
    }
    const params = getParams();
    if (shouldRemoveValue(value)) {
      if (params.has(key)) {
        params.delete(key);
        applyParams(params);
      }
      return;
    }

    let serialized;
    try {
      serialized = JSON.stringify(value);
    } catch (error) {
      // If the value cannot be serialized, skip updating the hash.
      return;
    }

    if (params.get(key) === serialized) {
      return;
    }

    params.set(key, serialized);
    applyParams(params);
  }

  function updateSection(key, updater) {
    if (!key) {
      return;
    }
    if (typeof updater !== 'function') {
      writeSection(key, updater);
      return;
    }
    const currentValue = readSection(key);
    const nextValue = updater(currentValue);
    writeSection(key, nextValue);
  }

  function clearSection(key) {
    writeSection(key, null);
  }

  function subscribeToSection(key, callback, options = {}) {
    if (!key || typeof callback !== 'function') {
      return () => {};
    }

    const handler = () => {
      callback(readSection(key));
    };

    win.addEventListener('hashchange', handler);

    if (options.immediate) {
      handler();
    }

    return () => {
      win.removeEventListener('hashchange', handler);
    };
  }

  function readAllSections() {
    const params = getParams();
    const result = {};
    params.forEach((value, key) => {
      try {
        result[key] = JSON.parse(value);
      } catch (error) {
        result[key] = value;
      }
    });
    return result;
  }

  win.filterState = {
    readSection,
    writeSection,
    updateSection,
    clearSection,
    subscribeToSection,
    readAllSections,
  };
})(typeof window !== 'undefined' ? window : this);

(function (global) {
  const win = global || window;

  function toBase64Url(value) {
    if (!value) {
      return '';
    }

    let bytes;
    if (typeof win.TextEncoder === 'function') {
      bytes = new win.TextEncoder().encode(value);
    } else {
      bytes = Array.from(unescape(encodeURIComponent(value))).map((char) => char.charCodeAt(0));
    }

    let binary = '';
    bytes.forEach((codePoint) => {
      binary += String.fromCharCode(codePoint);
    });

    const base64 = win.btoa(binary);
    return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/u, '');
  }

  function fromBase64Url(value) {
    if (typeof value !== 'string' || value.length === 0) {
      return '';
    }

    const base64 = value.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '==='.slice((base64.length + 3) % 4);

    let binary;
    try {
      binary = win.atob(padded);
    } catch (error) {
      throw new Error('Invalid base64 value');
    }

    if (typeof win.TextDecoder === 'function') {
      const buffer = new Uint8Array(binary.split('').map((char) => char.charCodeAt(0)));
      return new win.TextDecoder().decode(buffer);
    }

    let result = '';
    for (let i = 0; i < binary.length; i += 1) {
      result += `%${(`00${binary.charCodeAt(i).toString(16)}`).slice(-2)}`;
    }
    return decodeURIComponent(result);
  }

  function serializeValue(value) {
    let serialized;
    try {
      serialized = JSON.stringify(value);
    } catch (error) {
      return null;
    }

    return toBase64Url(serialized);
  }

  function deserializeValue(value) {
    if (typeof value !== 'string') {
      return value;
    }

    try {
      const json = fromBase64Url(value);
      return JSON.parse(json);
    } catch (error) {
      try {
        return JSON.parse(value);
      } catch (parseError) {
        return value;
      }
    }
  }

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
    return deserializeValue(raw);
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

    const encoded = serializeValue(value);
    if (encoded === null) {
      return;
    }

    if (params.get(key) === encoded) {
      return;
    }

    params.set(key, encoded);
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
      result[key] = deserializeValue(value);
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

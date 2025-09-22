(function () {
  const docEl = document.documentElement;
  const timezoneMeta = document.querySelector('meta[name="user-timezone"]');

  function normalizeTimezone(value) {
    if (!value) {
      return '';
    }
    return String(value).trim();
  }

  function readCookie(name) {
    try {
      const pattern = new RegExp(`(?:^|;\\s*)${name}=([^;]+)`);
      const match = document.cookie.match(pattern);
      return match ? decodeURIComponent(match[1]) : '';
    } catch (error) {
      console.warn('appTime failed to read cookie', error);
      return '';
    }
  }

  let browserTimezone = '';
  try {
    if (typeof Intl !== 'undefined' && typeof Intl.DateTimeFormat === 'function') {
      browserTimezone = normalizeTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone);
    }
  } catch (error) {
    console.warn('appTime failed to detect browser timezone', error);
    browserTimezone = '';
  }

  const cookieTimezone = normalizeTimezone(readCookie('tz'));
  const metaTimezone = normalizeTimezone(timezoneMeta?.getAttribute('content'));
  const datasetTimezone = normalizeTimezone(docEl?.dataset?.timezone);
  const timezoneName =
    cookieTimezone ||
    browserTimezone ||
    metaTimezone ||
    datasetTimezone ||
    'UTC';

  if (docEl && !docEl.dataset.timezone) {
    docEl.dataset.timezone = timezoneName;
  }

  const locale = docEl?.lang || undefined;

  function parseDate(value) {
    if (!value) {
      return null;
    }
    if (value instanceof Date) {
      return Number.isNaN(value.getTime()) ? null : value;
    }
    if (typeof value === 'number') {
      const fromNumber = new Date(value);
      return Number.isNaN(fromNumber.getTime()) ? null : fromNumber;
    }
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (!trimmed) {
        return null;
      }
      const normalized = trimmed.endsWith('Z') || /[+-]\d\d:?\d\d$/.test(trimmed)
        ? trimmed
        : `${trimmed}Z`;
      const fromString = new Date(normalized);
      if (!Number.isNaN(fromString.getTime())) {
        return fromString;
      }
      const fallback = new Date(trimmed);
      return Number.isNaN(fallback.getTime()) ? null : fallback;
    }
    try {
      const fromValue = new Date(value);
      return Number.isNaN(fromValue.getTime()) ? null : fromValue;
    } catch (error) {
      console.warn('appTime.parseDate failed', error);
      return null;
    }
  }

  function buildOptions(options) {
    const finalOptions = { ...(options || {}) };
    if (!finalOptions.timeZone) {
      finalOptions.timeZone = timezoneName;
    }
    return finalOptions;
  }

  function formatWithFormatter(date, formatterBuilder, fallback) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
      return fallback;
    }
    try {
      return formatterBuilder().format(date);
    } catch (error) {
      console.warn('appTime formatter failed', error);
      try {
        return date.toLocaleString();
      } catch (innerError) {
        console.warn('Fallback formatting failed', innerError);
        return fallback;
      }
    }
  }

  function formatDateTime(value, options) {
    const date = parseDate(value);
    if (!date) {
      return '';
    }
    const finalOptions = buildOptions(options);
    if (!('dateStyle' in finalOptions) && !('timeStyle' in finalOptions) &&
        !('year' in finalOptions) && !('month' in finalOptions) && !('day' in finalOptions) &&
        !('hour' in finalOptions)) {
      finalOptions.dateStyle = 'medium';
      finalOptions.timeStyle = 'short';
    }
    return formatWithFormatter(date, () => new Intl.DateTimeFormat(locale, finalOptions), '');
  }

  function formatDate(value, options) {
    const date = parseDate(value);
    if (!date) {
      return '';
    }
    const finalOptions = buildOptions(options);
    if (!('dateStyle' in finalOptions) &&
        !('year' in finalOptions) && !('month' in finalOptions) && !('day' in finalOptions)) {
      finalOptions.dateStyle = 'medium';
    }
    return formatWithFormatter(date, () => new Intl.DateTimeFormat(locale, finalOptions), '');
  }

  function formatTime(value, options) {
    const date = parseDate(value);
    if (!date) {
      return '';
    }
    const finalOptions = buildOptions(options);
    if (!('timeStyle' in finalOptions) &&
        !('hour' in finalOptions) && !('minute' in finalOptions) && !('second' in finalOptions)) {
      finalOptions.timeStyle = 'short';
    }
    return formatWithFormatter(date, () => new Intl.DateTimeFormat(locale, finalOptions), '');
  }

  window.appTime = {
    timezone: timezoneName,
    locale: locale || undefined,
    parseDate,
    formatDateTime,
    formatDate,
    formatTime,
  };
})();

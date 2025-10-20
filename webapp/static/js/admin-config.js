(function () {
  'use strict';

  const forms = document.querySelectorAll('[data-ajax-config-form]');
  if (!forms.length) {
    return;
  }

  const showSuccess = window.showSuccessToast || ((msg) => console.log(msg));
  const showError = window.showErrorToast || ((msg) => console.error(msg));
  const showWarning = window.showWarningToast || ((msg) => console.warn(msg));

  const cssEscape = (value) => {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(value);
    }
    return String(value).replace(/[^a-zA-Z0-9_\-]/g, (char) => `\\${char}`);
  };

  function formatTimestamp(isoString) {
    if (!isoString) {
      return '';
    }
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) {
      return isoString;
    }
    return date.toLocaleString();
  }

  function updateBadge(badge, usingDefault) {
    if (!badge) {
      return;
    }
    const usingLabel = badge.dataset.labelUsingDefault || badge.textContent || '';
    const overriddenLabel = badge.dataset.labelOverridden || badge.textContent || '';
    badge.textContent = usingDefault ? usingLabel : overriddenLabel;
    badge.classList.toggle('bg-secondary', usingDefault);
    badge.classList.toggle('bg-info', !usingDefault);
  }

  function updateDefaultCell(cell, value) {
    if (!cell) {
      return;
    }
    const noneLabel = cell.dataset.noneLabel || '';
    if (value) {
      cell.textContent = value;
      cell.classList.remove('text-muted');
    } else {
      cell.textContent = noneLabel;
      cell.classList.add('text-muted');
    }
  }

  function updateInputValue(input, value) {
    if (!input) {
      return;
    }
    if (input.tagName === 'SELECT') {
      input.value = value ?? '';
    } else if (input.tagName === 'TEXTAREA') {
      input.value = value ?? '';
    } else {
      input.value = value ?? '';
    }
  }

  function updateApplicationRows(fields) {
    if (!Array.isArray(fields)) {
      return;
    }
    fields.forEach((field) => {
      const row = document.querySelector(`[data-app-key="${cssEscape(field.key)}"]`);
      if (!row) {
        return;
      }
      const badge = row.querySelector('[data-field="status-badge"]');
      updateBadge(badge, !!field.using_default);

      const currentCell = row.querySelector('[data-field="current"]');
      if (currentCell) {
        currentCell.textContent = field.current_json || '';
      }

      const defaultCell = row.querySelector('[data-field="default"]');
      updateDefaultCell(defaultCell, field.default_json);

      const input = row.querySelector('[data-field-input]');
      updateInputValue(input, field.form_value);

      const useDefault = row.querySelector('[data-field-use-default]');
      if (useDefault) {
        useDefault.checked = !!field.use_default;
      }

      const selectCheckbox = row.querySelector('[data-field-select]');
      if (selectCheckbox) {
        selectCheckbox.checked = !!field.selected;
      }
    });
  }

  function updateCorsRows(fields) {
    if (!Array.isArray(fields)) {
      return;
    }
    fields.forEach((field) => {
      const row = document.querySelector(`[data-cors-key="${cssEscape(field.key)}"]`);
      if (!row) {
        return;
      }
      const badge = row.querySelector('[data-field="status-badge"]');
      updateBadge(badge, !!field.using_default);

      const currentCell = row.querySelector('[data-field="current"]');
      if (currentCell) {
        currentCell.textContent = field.current_json || '';
      }

      const defaultCell = row.querySelector('[data-field="default"]');
      updateDefaultCell(defaultCell, field.default_json);

      const input = row.querySelector('[data-cors-input]');
      updateInputValue(input, field.form_value);

      const useDefault = row.querySelector('[data-cors-use-default]');
      if (useDefault) {
        useDefault.checked = !!field.use_default;
      }
    });
  }

  function updateSigningSetting(signingSetting) {
    if (!signingSetting) {
      return;
    }
    const builtinRadio = document.getElementById('access-token-signing-builtin');
    if (signingSetting.mode === 'builtin') {
      if (builtinRadio) {
        builtinRadio.checked = true;
      }
      return;
    }
    if (signingSetting.mode === 'server_signing' && signingSetting.group_code) {
      const value = `server_signing:${signingSetting.group_code}`;
      const radio = document.querySelector(`input[name="access_token_signing"][value="${cssEscape(value)}"]`);
      if (radio) {
        radio.checked = true;
      }
    }
  }

  function updateTimestamps(timestamps, descriptions) {
    if (!timestamps) {
      return;
    }
    const descriptionsMap = descriptions || {};
    const sections = [
      { key: 'application', time: timestamps.application_config_updated_at, desc: descriptionsMap.application_config_description },
      { key: 'cors', time: timestamps.cors_config_updated_at, desc: descriptionsMap.cors_config_description },
      { key: 'signing', time: timestamps.signing_config_updated_at, desc: null },
    ];
    sections.forEach(({ key, time, desc }) => {
      const container = document.querySelector(`[data-timestamp-target="${key}"]`);
      if (!container) {
        return;
      }
      const labelTemplate = container.dataset.labelUpdated || '';
      const descriptionTemplate = container.dataset.descriptionLabel || '';
      const formattedTime = time ? labelTemplate.replace('__TIME__', formatTimestamp(time)) : '';
      const descriptionText = desc ? descriptionTemplate.replace('__DESC__', desc) : '';

      container.textContent = '';
      if (formattedTime) {
        container.append(document.createTextNode(formattedTime));
      }
      if (descriptionText) {
        if (formattedTime) {
          container.append(document.createElement('br'));
        }
        container.append(document.createTextNode(descriptionText));
      }
    });
  }

  function updateConfigTable(configData) {
    const tableBody = document.querySelector('[data-config-table-body]');
    if (!tableBody || !configData) {
      return;
    }
    tableBody.innerHTML = '';
    Object.entries(configData).forEach(([key, value]) => {
      const row = document.createElement('tr');
      const keyCell = document.createElement('td');
      keyCell.textContent = key;
      const valueCell = document.createElement('td');
      valueCell.textContent = value;
      row.append(keyCell, valueCell);
      tableBody.append(row);
    });
  }

  function applyContext(data) {
    if (!data) {
      return;
    }
    updateApplicationRows(data.application_fields);
    updateCorsRows(data.cors_fields);
    updateSigningSetting(data.signing_setting);
    updateTimestamps(data.timestamps, data.descriptions);
    updateConfigTable(data.config);
  }

  async function fetchContext() {
    try {
      const response = await fetch(window.location.href, {
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          Accept: 'application/json',
        },
      });
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      if (payload && payload.status === 'success') {
        applyContext(payload);
      }
    } catch (error) {
      console.error('Failed to refresh config context', error);
    }
  }

  forms.forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      event.stopPropagation();

      const submitButton = form.querySelector('button[type="submit"]');
      if (submitButton) {
        submitButton.disabled = true;
      }

      try {
        const formData = new FormData(form);
        const actionAttribute = form.getAttribute('action');
        const requestUrl = actionAttribute
          ? new URL(actionAttribute, window.location.href).toString()
          : window.location.href;
        const response = await fetch(requestUrl, {
          method: form.method || 'POST',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            Accept: 'application/json',
          },
          body: formData,
        });

        const data = await response.json().catch(() => null);
        if (!response.ok || !data || data.status !== 'success') {
          const message = data && data.message ? data.message : '設定の更新に失敗しました。';
          showError(message);
          if (data && Array.isArray(data.errors)) {
            data.errors.slice(1).forEach((msg) => showError(msg));
          }
          return;
        }

        showSuccess(data.message || '設定を更新しました。');
        if (Array.isArray(data.warnings)) {
          data.warnings.forEach((msg) => showWarning(msg));
        }
        applyContext(data);
      } catch (error) {
        console.error('Failed to submit config form', error);
        showError('リクエストの送信に失敗しました。');
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          const spinner = submitButton.querySelector('.spinner-border');
          if (spinner) {
            spinner.remove();
          }
        }
      }
    });
  });

  // Ensure the latest context is displayed when the page loads.
  fetchContext();
})();

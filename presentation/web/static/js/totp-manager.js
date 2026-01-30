(function () {
  'use strict';

  const api = new APIClient();
  const canWrite = Boolean(window.totpPermissions?.canWrite);
  const state = {
    items: [],
    sort: 'issuer',
    timer: null,
  };

  const elements = {
    tableBody: document.getElementById('totp-table-body'),
    sortSelect: document.getElementById('totp-sort-select'),
    previewCode: document.getElementById('totp-preview-code'),
    previewProgress: document.getElementById('totp-preview-progress'),
    previewRemaining: document.getElementById('totp-preview-remaining'),
    previewBadge: document.getElementById('totp-preview-badge'),
    createForm: document.getElementById('totp-create-form'),
    otpauthInput: document.getElementById('totp-otpauth'),
    parseUriButton: document.getElementById('totp-parse-uri-btn'),
    qrUpload: document.getElementById('totp-qr-upload'),
    qrPasteButton: document.getElementById('totp-qr-paste-btn'),
    qrCanvas: document.getElementById('totp-qr-canvas'),
    qrPreview: document.getElementById('totp-qr-preview'),
    exportButton: document.getElementById('totp-export-btn'),
    importButton: document.getElementById('totp-import-btn'),
    importModalEl: document.getElementById('totp-import-modal'),
    importForm: document.getElementById('totp-import-form'),
    importFile: document.getElementById('totp-import-file'),
    importText: document.getElementById('totp-import-text'),
    importForce: document.getElementById('totp-import-force'),
    importConflicts: document.getElementById('totp-import-conflicts'),
    editModalEl: document.getElementById('totp-edit-modal'),
    editForm: document.getElementById('totp-edit-form'),
    editId: document.getElementById('totp-edit-id'),
    editAccount: document.getElementById('totp-edit-account'),
    editIssuer: document.getElementById('totp-edit-issuer'),
    editDigits: document.getElementById('totp-edit-digits'),
    editPeriod: document.getElementById('totp-edit-period'),
    editDescription: document.getElementById('totp-edit-description'),
    editSecret: document.getElementById('totp-edit-secret'),
  };

  const editModal = elements.editModalEl ? new bootstrap.Modal(elements.editModalEl) : null;
  const importModal = elements.importModalEl ? new bootstrap.Modal(elements.importModalEl) : null;

  function t(key, fallback, params = null) {
    const template = _(key, typeof fallback === 'string' ? fallback : key);
    if (!params) {
      return template;
    }

    let rendered = template.replace(/\{([^{}]+)\}/g, (match, token) => {
      if (Object.prototype.hasOwnProperty.call(params, token)) {
        return params[token];
      }
      return '';
    });

    rendered = rendered.replace(/%\(([^)]+)\)s/g, (match, token) => {
      if (Object.prototype.hasOwnProperty.call(params, token)) {
        return params[token];
      }
      return '';
    });

    return rendered;
  }

  function normalizeSecret(secret) {
    return (secret || '').replace(/\s+/g, '').replace(/-/g, '').toUpperCase();
  }

  function createSecret(secretValue) {
    const normalized = normalizeSecret(secretValue);
    if (!normalized) {
      throw new Error('Secret is empty');
    }

    if (typeof OTPAuth.Secret.fromB32 === 'function') {
      return OTPAuth.Secret.fromB32(normalized);
    }

    if (typeof OTPAuth.Secret.fromBase32 === 'function') {
      return OTPAuth.Secret.fromBase32(normalized);
    }

    const secret = new OTPAuth.Secret();
    if ('base32' in secret) {
      secret.base32 = normalized;
      return secret;
    }

    throw new Error('No supported method to create OTP secret');
  }

  function getTotpGenerator(item) {
    try {
      const secret = createSecret(item.secret);
      return new OTPAuth.TOTP({
        issuer: item.issuer,
        label: item.account,
        algorithm: item.algorithm || 'SHA1',
        digits: Number(item.digits) || 6,
        period: Number(item.period) || 30,
        secret,
      });
    } catch (error) {
      console.error('Failed to create TOTP generator', error);
      return null;
    }
  }

  function computeOtp(item) {
    const totp = getTotpGenerator(item);
    if (!totp) {
      return { code: '------', remaining: 0 };
    }
    try {
      const code = totp.generate();
      const period = Number(item.period) || 30;
      const now = Math.floor(Date.now() / 1000);
      let remaining = period - (now % period);
      if (remaining <= 0) {
        remaining = period;
      }
      return { code, remaining, period };
    } catch (error) {
      console.error('Failed to generate TOTP', error);
      return { code: '------', remaining: 0 };
    }
  }

  function renderTable() {
    if (!elements.tableBody) return;
    const items = [...state.items];
    switch (state.sort) {
      case 'account':
        items.sort((a, b) => a.account.localeCompare(b.account) || a.issuer.localeCompare(b.issuer));
        break;
      case 'updated':
        items.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
        break;
      case 'issuer':
      default:
        items.sort((a, b) => a.issuer.localeCompare(b.issuer) || a.account.localeCompare(b.account));
        break;
    }

    const columnCount = canWrite ? 7 : 6;

    if (!items.length) {
      elements.tableBody.innerHTML = `
        <tr>
          <td colspan="${columnCount}" class="text-center py-4 text-muted">
            <i class="bi bi-inbox me-2"></i>${t('totp.noEntries', 'No TOTP registrations yet.')}
          </td>
        </tr>`;
      return;
    }

    const rows = items.map((item) => {
      const updated = item.updated_at ? new Date(item.updated_at) : null;
      const updatedText = updated ? updated.toLocaleString() : '';
      const description = item.description ? escapeHtml(item.description) : '<span class="text-muted">-</span>';
      const actionsCell = canWrite
        ? `
          <td class="text-start">
            <div class="totp-list-actions">
              <button class="btn btn-sm btn-outline-primary" data-action="edit">${t('totp.actions.edit', 'Edit')}</button>
              <button class="btn btn-sm btn-outline-danger" data-action="delete">${t('totp.actions.delete', 'Delete')}</button>
            </div>
          </td>`
        : '';
      return `
        <tr data-id="${item.id}">
          <td class="fw-semibold">${escapeHtml(item.issuer)}</td>
          <td>${escapeHtml(item.account)}</td>
          <td>
            <div class="otp-code mb-1 otp-copyable" data-role="otp" data-action="copy-otp" role="button" tabindex="0" title="${t('totp.copyHint', 'Click to copy')}" aria-label="${t('totp.copyAriaLabel', 'Copy one-time code')}">------</div>
          </td>
          <td>
            <div class="progress otp-progress mb-1">
              <div class="progress-bar" role="progressbar" data-role="progress" style="width: 0%"></div>
            </div>
            <small class="text-muted" data-role="remaining">--</small>
          </td>
          <td>${description}</td>
          <td class="text-nowrap">${escapeHtml(updatedText)}</td>
          ${actionsCell}
        </tr>`;
    });

    elements.tableBody.innerHTML = rows.join('');
  }

  function escapeHtml(value) {
    if (value == null) return '';
    return value
      .toString()
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function sanitizeOtpText(value) {
    return (value || '').replace(/\s+/g, '');
  }

  async function copyTextToClipboard(text) {
    if (!text) {
      return false;
    }

    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (error) {
      console.warn('Failed to copy via navigator.clipboard', error);
    }

    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'absolute';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    const selection = document.getSelection();
    const selectedRange = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;
    textarea.select();

    let succeeded = false;
    try {
      succeeded = document.execCommand('copy');
    } catch (error) {
      console.error('Fallback copy command failed', error);
      succeeded = false;
    }

    document.body.removeChild(textarea);
    if (selectedRange && selection) {
      selection.removeAllRanges();
      selection.addRange(selectedRange);
    }

    return succeeded;
  }

  function showCopySuccessToast() {
    if (window.showSuccessToast) {
      window.showSuccessToast(t('totp.copy.success', 'Copied the one-time code.'));
    }
  }

  function showCopyErrorToast() {
    if (window.showErrorToast) {
      window.showErrorToast(t('totp.copy.error', 'Failed to copy the one-time code.'));
    }
  }

  async function copyOtpCode(code) {
    const sanitized = sanitizeOtpText(code);
    if (!sanitized || sanitized.includes('-')) {
      return false;
    }
    const success = await copyTextToClipboard(sanitized);
    if (success) {
      showCopySuccessToast();
      return true;
    }
    showCopyErrorToast();
    return false;
  }

  async function handleOtpCopyFromRow(element) {
    const row = element.closest('tr[data-id]');
    if (!row) return;
    const otpEl = row.querySelector('[data-role="otp"]');
    if (!otpEl) return;
    await copyOtpCode(otpEl.textContent || '');
  }

  async function handlePreviewCopy() {
    if (!elements.previewCode) return;
    await copyOtpCode(elements.previewCode.textContent || '');
  }

  function refreshOtpDisplay() {
    if (!elements.tableBody) return;
    const rows = elements.tableBody.querySelectorAll('tr[data-id]');
    rows.forEach((row) => {
      const id = Number(row.getAttribute('data-id'));
      const item = state.items.find((entry) => entry.id === id);
      if (!item) return;
      const { code, remaining, period } = computeOtp(item);
      const otpEl = row.querySelector('[data-role="otp"]');
      const progressEl = row.querySelector('[data-role="progress"]');
      const remainingEl = row.querySelector('[data-role="remaining"]');
      if (otpEl) otpEl.textContent = code;
      if (remainingEl) {
        remainingEl.textContent = t('totp.remainingSeconds', 'Remaining {seconds} seconds', { seconds: remaining });
      }
      if (progressEl) {
        const ratio = period ? ((period - remaining) / period) * 100 : 0;
        progressEl.style.width = `${Math.max(0, Math.min(100, ratio))}%`;
        progressEl.classList.toggle('bg-danger', remaining <= 5);
        progressEl.classList.toggle('bg-success', remaining > 5);
      }
    });
  }

  function updatePreviewFromForm() {
    if (!elements.createForm) return;
    const account = elements.createForm.querySelector('#totp-account').value;
    const issuer = elements.createForm.querySelector('#totp-issuer').value;
    const secret = elements.createForm.querySelector('#totp-secret').value;
    const digits = Number(elements.createForm.querySelector('#totp-digits').value) || 6;
    const period = Number(elements.createForm.querySelector('#totp-period').value) || 30;

    if (!secret) {
      setPreviewState('waiting');
      return;
    }

    const generator = getTotpGenerator({ account, issuer, secret, digits, period, algorithm: 'SHA1' });
    if (!generator) {
      setPreviewState('error');
      return;
    }

    try {
      const code = generator.generate();
      const now = Math.floor(Date.now() / 1000);
      let remaining = period - (now % period);
      if (remaining <= 0) remaining = period;
      if (elements.previewCode) elements.previewCode.textContent = code;
      if (elements.previewRemaining) {
        elements.previewRemaining.textContent = t('totp.remainingSeconds', 'Remaining {seconds} seconds', { seconds: remaining });
      }
      if (elements.previewProgress) {
        const ratio = ((period - remaining) / period) * 100;
        elements.previewProgress.style.width = `${Math.max(0, Math.min(100, ratio))}%`;
      }
      if (elements.previewBadge) {
        elements.previewBadge.textContent = t('totp.preview.active', 'Previewing');
        elements.previewBadge.classList.remove('bg-secondary', 'bg-danger');
        elements.previewBadge.classList.add('bg-success');
      }
    } catch (error) {
      setPreviewState('error');
    }
  }

  function setPreviewState(stateName) {
    if (!elements.previewCode || !elements.previewBadge) return;
    if (stateName === 'waiting') {
      elements.previewCode.textContent = '------';
      if (elements.previewProgress) {
        elements.previewProgress.style.width = '0%';
      }
      if (elements.previewRemaining) {
        elements.previewRemaining.textContent = t('totp.preview.placeholderSeconds', '-- seconds remaining');
      }
      elements.previewBadge.textContent = t('totp.preview.waiting', 'Waiting for preview');
      elements.previewBadge.className = 'badge bg-secondary';
    } else if (stateName === 'error') {
      elements.previewCode.textContent = '------';
      elements.previewBadge.textContent = t('totp.preview.unavailable', 'Preview unavailable');
      elements.previewBadge.className = 'badge bg-danger';
    }
  }

  async function fetchTotpList() {
    try {
      const response = await api.get('/api/totp');
      if (!response.ok) {
        throw new Error(`Failed to load: ${response.status}`);
      }
      const data = await response.json();
      state.items = data.items || [];
      renderTable();
      refreshOtpDisplay();
    } catch (error) {
      console.error('Failed to fetch TOTP list', error);
      if (window.showErrorToast) {
        window.showErrorToast(t('totp.load.error', 'Failed to load the TOTP list.'));
      }
    }
  }

  function startTimer() {
    if (state.timer) clearInterval(state.timer);
    state.timer = setInterval(() => {
      refreshOtpDisplay();
      updatePreviewFromForm();
    }, 1000);
  }

  function parseOtpauthUri(uri) {
    if (!uri) {
      throw new Error('URI is empty');
    }
    let parsed;
    try {
      parsed = new URL(uri);
    } catch (error) {
      throw new Error(t('totp.otpauth.invalidFormat', 'The otpauth URI is not valid.'));
    }
    if (parsed.protocol !== 'otpauth:' || parsed.hostname.toLowerCase() !== 'totp') {
      throw new Error(t('totp.otpauth.invalidType', 'The otpauth URI is not for TOTP.'));
    }
    const label = decodeURIComponent(parsed.pathname.replace(/^\//, ''));
    let issuerFromLabel = '';
    let account = label;
    if (label.includes(':')) {
      const [issuerPart, accountPart] = label.split(':', 2);
      issuerFromLabel = issuerPart.trim();
      account = accountPart.trim();
    }
    const params = parsed.searchParams;
    const secret = params.get('secret');
    const issuer = params.get('issuer') || issuerFromLabel;
    if (!secret || !issuer || !account) {
      throw new Error(t('totp.otpauth.missingData', 'The otpauth URI is missing required information.'));
    }
    const digits = Number(params.get('digits') || '6');
    const period = Number(params.get('period') || '30');
    const algorithm = (params.get('algorithm') || 'SHA1').toUpperCase();
    const description = params.get('description') || params.get('comment') || '';
    return { account, issuer, secret, digits, period, algorithm, description };
  }

  function populateCreateForm(data) {
    elements.createForm.querySelector('#totp-account').value = data.account || '';
    elements.createForm.querySelector('#totp-issuer').value = data.issuer || '';
    elements.createForm.querySelector('#totp-secret').value = data.secret || '';
    elements.createForm.querySelector('#totp-digits').value = data.digits || 6;
    elements.createForm.querySelector('#totp-period').value = data.period || 30;
    elements.createForm.querySelector('#totp-description').value = data.description || '';
    updatePreviewFromForm();
  }

  function bindEvents() {
    if (elements.sortSelect) {
      elements.sortSelect.addEventListener('change', (event) => {
        state.sort = event.target.value;
        renderTable();
        refreshOtpDisplay();
      });
    }

    if (elements.createForm) {
      elements.createForm.addEventListener('input', () => {
        updatePreviewFromForm();
      });
      elements.createForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const formData = new FormData(elements.createForm);
        const payload = Object.fromEntries(formData.entries());
        payload.digits = payload.digits ? Number(payload.digits) : 6;
        payload.period = payload.period ? Number(payload.period) : 30;
        try {
          const response = await api.post('/api/totp', payload);
          const data = await response.json();
          if (!response.ok) {
            if (data && data.error) {
              throw new Error(data.error);
            }
            throw new Error(`Failed: ${response.status}`);
          }
          if (window.showSuccessToast) {
            window.showSuccessToast(t('totp.create.success', 'Registered the TOTP entry.'));
          }
          elements.createForm.reset();
          setPreviewState('waiting');
          await fetchTotpList();
        } catch (error) {
          console.error('Failed to create TOTP', error);
          if (window.showErrorToast) {
            window.showErrorToast(error.message || t('totp.create.error', 'Failed to register the TOTP entry.'));
          }
        }
      });
    }

    if (elements.parseUriButton) {
      elements.parseUriButton.addEventListener('click', () => {
        try {
          const uri = elements.otpauthInput.value.trim();
          const data = parseOtpauthUri(uri);
          populateCreateForm(data);
          if (window.showSuccessToast) {
            window.showSuccessToast(t('totp.parse.success', 'Extracted information from the URI.'));
          }
        } catch (error) {
          console.error('Failed to parse otpauth URI', error);
          if (window.showErrorToast) {
            window.showErrorToast(error.message || t('totp.parse.error', 'Failed to parse the otpauth URI.'));
          }
        }
      });
    }

    if (elements.qrUpload) {
      elements.qrUpload.addEventListener('change', handleQrUpload);
    }

    if (elements.qrPasteButton) {
      elements.qrPasteButton.addEventListener('click', handleQrPasteFromClipboard);
    }

    if (elements.previewCode) {
      elements.previewCode.addEventListener('click', () => {
        handlePreviewCopy();
      });
      elements.previewCode.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar' || event.key === 'Space') {
          event.preventDefault();
          handlePreviewCopy();
        }
      });
    }

    if (elements.tableBody) {
      elements.tableBody.addEventListener('click', (event) => {
        const copyTarget = event.target.closest('[data-action="copy-otp"]');
        if (copyTarget) {
          event.preventDefault();
          handleOtpCopyFromRow(copyTarget);
          return;
        }

        const actionButton = event.target.closest('button[data-action]');
        if (!actionButton) return;
        const row = actionButton.closest('tr[data-id]');
        if (!row) return;
        const id = Number(row.getAttribute('data-id'));
        const item = state.items.find((entry) => entry.id === id);
        if (!item) return;
        const action = actionButton.getAttribute('data-action');
        if (action === 'edit') {
          openEditModal(item);
        } else if (action === 'delete') {
          confirmDelete(item);
        }
      });

      elements.tableBody.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ' && event.key !== 'Spacebar' && event.key !== 'Space') {
          return;
        }
        const copyTarget = event.target.closest('[data-action="copy-otp"]');
        if (!copyTarget) {
          return;
        }
        event.preventDefault();
        handleOtpCopyFromRow(copyTarget);
      });
    }

    if (elements.editForm) {
      elements.editForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const id = Number(elements.editId.value);
        const payload = {
          account: elements.editAccount.value,
          issuer: elements.editIssuer.value,
          description: elements.editDescription.value,
          digits: Number(elements.editDigits.value) || 6,
          period: Number(elements.editPeriod.value) || 30,
        };
        const secret = elements.editSecret.value.trim();
        if (secret) {
          payload.secret = secret;
        }
        try {
          const response = await api.put(`/api/totp/${id}`, payload);
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.error || `Failed: ${response.status}`);
          }
          if (window.showSuccessToast) {
            window.showSuccessToast(t('totp.update.success', 'Updated the TOTP entry.'));
          }
          if (editModal) editModal.hide();
          await fetchTotpList();
        } catch (error) {
          console.error('Failed to update TOTP', error);
          if (window.showErrorToast) {
            window.showErrorToast(error.message || t('totp.update.error', 'Failed to update the TOTP entry.'));
          }
        }
      });
    }

    if (elements.exportButton) {
      elements.exportButton.addEventListener('click', exportTotp);
    }

    if (elements.importButton) {
      elements.importButton.addEventListener('click', () => {
        if (!importModal) return;
        elements.importForm.reset();
        elements.importConflicts.classList.add('d-none');
        importModal.show();
      });
    }

    if (elements.importForm) {
      elements.importForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        try {
          const jsonText = await resolveImportJson();
          const parsed = JSON.parse(jsonText);
          const payload = {
            items: parsed,
            force: elements.importForce.checked,
          };
          const response = await api.post('/api/totp/import', payload);
          const data = await response.json();
          if (response.status === 409 && data.conflicts) {
            showImportConflicts(data.conflicts);
            return;
          }
          if (!response.ok) {
            throw new Error(data.error || `Failed: ${response.status}`);
          }
          if (window.showSuccessToast) {
            window.showSuccessToast(t('totp.import.success', 'Imported TOTP entries.'));
          }
          if (importModal) importModal.hide();
          await fetchTotpList();
        } catch (error) {
          console.error('Failed to import TOTP', error);
          if (window.showErrorToast) {
            window.showErrorToast(error.message || t('totp.import.error', 'Failed to import TOTP entries.'));
          }
        }
      });
    }
  }

  function showImportConflicts(conflicts) {
    if (!elements.importConflicts) return;
    const list = conflicts
      .map((item) => `<li>${escapeHtml(item.issuer)} / ${escapeHtml(item.account)}</li>`)
      .join('');
    elements.importConflicts.innerHTML = `
      <strong>${t('totp.import.duplicatesTitle', 'Duplicate entries detected')}:</strong>
      <ul class="mb-0">${list}</ul>
      <p class="mb-0 mt-2">${t('totp.import.duplicatesHint', 'Select "Overwrite even if duplicates exist" and try again.')}</p>`;
    elements.importConflicts.classList.remove('d-none');
  }

  function resolveImportJson() {
    return new Promise((resolve, reject) => {
      const text = elements.importText.value.trim();
      if (text) {
        resolve(text);
        return;
      }
      const file = elements.importFile.files && elements.importFile.files[0];
      if (!file) {
        reject(new Error(t('totp.import.requireInput', 'Provide JSON text or choose a file.')));
        return;
      }
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error(t('totp.file.readError', 'Failed to read the file.')));
      reader.readAsText(file, 'utf-8');
    });
  }

  async function exportTotp() {
    try {
      const response = await api.get('/api/totp/export');
      if (!response.ok) {
        throw new Error(`Failed: ${response.status}`);
      }
      const data = await response.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const date = new Date().toISOString().replace(/[:.]/g, '-');
      link.download = `totp-export-${date}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      if (window.showSuccessToast) {
        window.showSuccessToast(t('totp.export.success', 'Downloaded the JSON file.'));
      }
    } catch (error) {
      console.error('Failed to export TOTP', error);
      if (window.showErrorToast) {
        window.showErrorToast(error.message || t('totp.export.error', 'Failed to export TOTP entries.'));
      }
    }
  }

  async function confirmDelete(item) {
    const message = t('totp.delete.confirm', 'Delete {issuer} / {account}?', {
      issuer: item.issuer,
      account: item.account,
    });
    if (!window.confirm(message)) {
      return;
    }
    try {
      const response = await api.request({ url: `/api/totp/${item.id}`, method: 'DELETE' });
      if (!response.ok) {
        throw new Error(`Failed: ${response.status}`);
      }
      if (window.showSuccessToast) {
        window.showSuccessToast(t('totp.delete.success', 'Deleted the TOTP entry.'));
      }
      await fetchTotpList();
    } catch (error) {
      console.error('Failed to delete TOTP', error);
      if (window.showErrorToast) {
        window.showErrorToast(error.message || t('totp.delete.error', 'Failed to delete the TOTP entry.'));
      }
    }
  }

  function openEditModal(item) {
    if (!editModal) return;
    elements.editId.value = item.id;
    elements.editAccount.value = item.account;
    elements.editIssuer.value = item.issuer;
    elements.editDigits.value = item.digits;
    elements.editPeriod.value = item.period;
    elements.editDescription.value = item.description || '';
    elements.editSecret.value = '';
    editModal.show();
  }

  async function handleQrUpload(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
      const imageSrc = reader.result;
      try {
        const otpauth = await decodeQrFromImageSource(imageSrc);
        applyOtpauthFromQr(otpauth, imageSrc);
      } catch (error) {
        console.error('Failed to decode QR from file', error);
        if (window.showErrorToast) {
          window.showErrorToast(error.message || t('totp.qr.decodeError', 'Failed to decode the QR code.'));
        }
      }
    };
    reader.onerror = () => {
      if (window.showErrorToast) {
        window.showErrorToast(t('totp.file.readError', 'Failed to read the file.'));
      }
    };
    reader.readAsDataURL(file);
  }

  async function handleQrPasteFromClipboard() {
    if (!navigator.clipboard || typeof navigator.clipboard.read !== 'function') {
      if (window.showErrorToast) {
        window.showErrorToast(t('totp.qr.unsupportedClipboard', 'This browser does not support reading images from the clipboard.'));
      }
      return;
    }
    try {
      const items = await navigator.clipboard.read();
      const imageItem = items.find((item) => item.types.some((type) => type.startsWith('image/')));
      if (!imageItem) {
        throw new Error(t('totp.qr.noClipboardImage', 'No image found in the clipboard.'));
      }
      const imageType = imageItem.types.find((type) => type.startsWith('image/'));
      const blob = await imageItem.getType(imageType);
      const imageSrc = await blobToDataUrl(blob);
      const otpauth = await decodeQrFromImageSource(imageSrc);
      applyOtpauthFromQr(otpauth, imageSrc);
    } catch (error) {
      console.error('Failed to read QR from clipboard', error);
      if (window.showErrorToast) {
        window.showErrorToast(error.message || t('totp.qr.decodeError', 'Failed to decode the QR code.'));
      }
    }
  }

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => {
        reject(new Error(t('totp.qr.imageLoadError', 'Failed to load the image.')));
      };
      reader.readAsDataURL(blob);
    });
  }

  function decodeQrFromImageSource(imageSrc) {
    return new Promise((resolve, reject) => {
      if (!elements.qrCanvas) {
        reject(new Error(t('totp.qr.decodeError', 'Failed to decode the QR code.')));
        return;
      }
      const image = new Image();
      image.onload = () => {
        try {
          const canvas = elements.qrCanvas;
          const context = canvas.getContext('2d');
          if (!context) {
            reject(new Error(t('totp.qr.decodeError', 'Failed to decode the QR code.')));
            return;
          }
          canvas.width = image.width;
          canvas.height = image.height;
          context.drawImage(image, 0, 0);
          const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
          const code = jsQR(imageData.data, canvas.width, canvas.height);
          if (code && code.data) {
            resolve(code.data);
          } else {
            reject(new Error(t('totp.qr.noCodeDetected', 'Could not detect a QR code.')));
          }
        } catch (error) {
          reject(error);
        }
      };
      image.onerror = () => {
        reject(new Error(t('totp.qr.imageLoadError', 'Failed to load the image.')));
      };
      image.src = imageSrc;
    });
  }

  function applyOtpauthFromQr(otpauth, previewSrc) {
    if (elements.otpauthInput) {
      elements.otpauthInput.value = otpauth;
    }
    if (previewSrc && elements.qrPreview) {
      elements.qrPreview.src = previewSrc;
      elements.qrPreview.classList.remove('d-none');
    }
    try {
      const parsed = parseOtpauthUri(otpauth);
      populateCreateForm(parsed);
      if (window.showSuccessToast) {
        window.showSuccessToast(t('totp.qr.readSuccess', 'Read information from the QR code.'));
      }
    } catch (error) {
      console.error('Failed to parse otpauth from QR', error);
      if (window.showErrorToast) {
        window.showErrorToast(error.message || t('totp.qr.decodeError', 'Failed to decode the QR code.'));
      }
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    bindEvents();
    updatePreviewFromForm();
    await fetchTotpList();
    startTimer();
  });
})();

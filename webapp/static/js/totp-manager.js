(function () {
  'use strict';

  const api = new APIClient();
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

  function t(message, params = null) {
    let translated = message;
    if (typeof window.gettext === 'function') {
      translated = window.gettext(message);
    }
    if (params) {
      translated = translated.replace(/%\(([^)]+)\)s/g, (match, key) => {
        if (Object.prototype.hasOwnProperty.call(params, key)) {
          return params[key];
        }
        return '';
      });
    }
    return translated;
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

    if (!items.length) {
      elements.tableBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-4 text-muted">
            <i class="bi bi-inbox me-2"></i>${t('まだ登録がありません')}
          </td>
        </tr>`;
      return;
    }

    const rows = items.map((item) => {
      const updated = item.updated_at ? new Date(item.updated_at) : null;
      const updatedText = updated ? updated.toLocaleString() : '';
      const description = item.description ? escapeHtml(item.description) : '<span class="text-muted">-</span>';
      return `
        <tr data-id="${item.id}">
          <td class="fw-semibold">${escapeHtml(item.issuer)}</td>
          <td>${escapeHtml(item.account)}</td>
          <td>
            <div class="otp-code mb-1" data-role="otp">------</div>
          </td>
          <td>
            <div class="progress otp-progress mb-1">
              <div class="progress-bar" role="progressbar" data-role="progress" style="width: 0%"></div>
            </div>
            <small class="text-muted" data-role="remaining">--</small>
          </td>
          <td>${description}</td>
          <td class="text-nowrap">${escapeHtml(updatedText)}</td>
          <td class="text-end totp-list-actions">
            <button class="btn btn-sm btn-outline-primary" data-action="edit">${t('編集')}</button>
            <button class="btn btn-sm btn-outline-danger" data-action="delete">${t('削除')}</button>
          </td>
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
        remainingEl.textContent = t('残り %(seconds)s 秒', { seconds: remaining });
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
        elements.previewRemaining.textContent = t('残り %(seconds)s 秒', { seconds: remaining });
      }
      if (elements.previewProgress) {
        const ratio = ((period - remaining) / period) * 100;
        elements.previewProgress.style.width = `${Math.max(0, Math.min(100, ratio))}%`;
      }
      if (elements.previewBadge) {
        elements.previewBadge.textContent = t('プレビュー中');
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
        elements.previewRemaining.textContent = t('残り -- 秒');
      }
      elements.previewBadge.textContent = t('プレビュー待ち');
      elements.previewBadge.className = 'badge bg-secondary';
    } else if (stateName === 'error') {
      elements.previewCode.textContent = '------';
      elements.previewBadge.textContent = t('プレビュー不可');
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
        window.showErrorToast(t('TOTP 一覧の取得に失敗しました'));
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
      throw new Error(t('otpauth URI の形式が不正です'));
    }
    if (parsed.protocol !== 'otpauth:' || parsed.hostname.toLowerCase() !== 'totp') {
      throw new Error(t('TOTP 用の otpauth URI ではありません'));
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
      throw new Error(t('otpauth URI に必要な情報が不足しています'));
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
            window.showSuccessToast(t('TOTP を登録しました'));
          }
          elements.createForm.reset();
          setPreviewState('waiting');
          await fetchTotpList();
        } catch (error) {
          console.error('Failed to create TOTP', error);
          if (window.showErrorToast) {
            window.showErrorToast(error.message || t('TOTP 登録に失敗しました'));
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
            window.showSuccessToast(t('URI から情報を展開しました'));
          }
        } catch (error) {
          console.error('Failed to parse otpauth URI', error);
          if (window.showErrorToast) {
            window.showErrorToast(error.message || t('otpauth URI の解析に失敗しました'));
          }
        }
      });
    }

    if (elements.qrUpload) {
      elements.qrUpload.addEventListener('change', handleQrUpload);
    }

    if (elements.tableBody) {
      elements.tableBody.addEventListener('click', (event) => {
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
            window.showSuccessToast(t('TOTP を更新しました'));
          }
          if (editModal) editModal.hide();
          await fetchTotpList();
        } catch (error) {
          console.error('Failed to update TOTP', error);
          if (window.showErrorToast) {
            window.showErrorToast(error.message || t('TOTP 更新に失敗しました'));
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
            window.showSuccessToast(t('TOTP をインポートしました'));
          }
          if (importModal) importModal.hide();
          await fetchTotpList();
        } catch (error) {
          console.error('Failed to import TOTP', error);
          if (window.showErrorToast) {
            window.showErrorToast(error.message || t('TOTP インポートに失敗しました'));
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
      <strong>${t('既存のエントリと重複しています')}:</strong>
      <ul class="mb-0">${list}</ul>
      <p class="mb-0 mt-2">${t('「重複があっても上書きする」にチェックを入れて再実行してください。')}</p>`;
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
        reject(new Error(t('JSON を入力またはファイルを選択してください')));
        return;
      }
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error(t('ファイルの読み込みに失敗しました')));
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
        window.showSuccessToast(t('JSON をダウンロードしました'));
      }
    } catch (error) {
      console.error('Failed to export TOTP', error);
      if (window.showErrorToast) {
        window.showErrorToast(error.message || t('TOTP エクスポートに失敗しました'));
      }
    }
  }

  async function confirmDelete(item) {
    const message = t('%(issuer)s / %(account)s を削除しますか？', { issuer: item.issuer, account: item.account });
    if (!window.confirm(message)) {
      return;
    }
    try {
      const response = await api.request({ url: `/api/totp/${item.id}`, method: 'DELETE' });
      if (!response.ok) {
        throw new Error(`Failed: ${response.status}`);
      }
      if (window.showSuccessToast) {
        window.showSuccessToast(t('TOTP を削除しました'));
      }
      await fetchTotpList();
    } catch (error) {
      console.error('Failed to delete TOTP', error);
      if (window.showErrorToast) {
        window.showErrorToast(error.message || t('TOTP 削除に失敗しました'));
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

  function handleQrUpload(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const image = new Image();
      image.onload = () => {
        const canvas = elements.qrCanvas;
        const context = canvas.getContext('2d');
        canvas.width = image.width;
        canvas.height = image.height;
        context.drawImage(image, 0, 0);
        const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
        const code = jsQR(imageData.data, canvas.width, canvas.height);
        if (code && code.data) {
          elements.otpauthInput.value = code.data;
          elements.qrPreview.src = image.src;
          elements.qrPreview.classList.remove('d-none');
          try {
            const parsed = parseOtpauthUri(code.data);
            populateCreateForm(parsed);
            if (window.showSuccessToast) {
              window.showSuccessToast(t('QR から情報を読み取りました'));
            }
          } catch (error) {
            console.error('Failed to parse otpauth from QR', error);
            if (window.showErrorToast) {
              window.showErrorToast(error.message || t('QR の解析に失敗しました'));
            }
          }
        } else if (window.showErrorToast) {
          window.showErrorToast(t('QR コードを検出できませんでした'));
        }
      };
      image.onerror = () => {
        if (window.showErrorToast) {
          window.showErrorToast(t('画像の読み込みに失敗しました'));
        }
      };
      image.src = reader.result;
    };
    reader.onerror = () => {
      if (window.showErrorToast) {
        window.showErrorToast(t('ファイルの読み込みに失敗しました'));
      }
    };
    reader.readAsDataURL(file);
  }

  document.addEventListener('DOMContentLoaded', async () => {
    bindEvents();
    updatePreviewFromForm();
    await fetchTotpList();
    startTimer();
  });
})();

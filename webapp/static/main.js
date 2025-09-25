// Disable submit buttons to prevent multiple submissions and show spinner
window.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', () => {
      const btn = form.querySelector('button[type="submit"]');
      if (btn && !btn.disabled) {
        btn.disabled = true;
        const spinner = document.createElement('span');
        spinner.className = 'spinner-border spinner-border-sm ms-2';
        spinner.setAttribute('role', 'status');
        spinner.setAttribute('aria-hidden', 'true');
        btn.appendChild(spinner);
      }
    });
  });

  const toggleButtons = document.querySelectorAll('.toggle-password-btn');
  toggleButtons.forEach(button => {
    const wrapper = button.closest('.password-toggle-wrapper');
    const input = wrapper ? wrapper.querySelector('input') : null;

    if (!input) {
      return;
    }

    const icon = button.querySelector('i');
    const showLabel = button.dataset.showLabel || 'Show password';
    const hideLabel = button.dataset.hideLabel || 'Hide password';

    const updateButtonState = visible => {
      if (visible) {
        button.setAttribute('aria-label', hideLabel);
        button.setAttribute('aria-pressed', 'true');
        if (icon) {
          icon.classList.remove('fa-eye');
          icon.classList.add('fa-eye-slash');
        }
      } else {
        button.setAttribute('aria-label', showLabel);
        button.setAttribute('aria-pressed', 'false');
        if (icon) {
          icon.classList.add('fa-eye');
          icon.classList.remove('fa-eye-slash');
        }
      }
    };

    button.addEventListener('click', () => {
      const isVisible = input.type === 'text';
      input.type = isVisible ? 'password' : 'text';
      updateButtonState(!isVisible);

      if (!isVisible) {
        input.focus({ preventScroll: true });
        const valueLength = input.value.length;
        input.setSelectionRange(valueLength, valueLength);
      }
    });

    updateButtonState(input.type === 'text');
  });
});

// Toast notification function
window.showToast = function(message, type = 'success', duration = 5000) {
  const toastContainer = document.getElementById('toast-container');
  if (!toastContainer) {
    console.error('Toast container not found');
    return;
  }

  // Create unique ID for this toast
  const toastId = 'toast-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
  
  // Determine Bootstrap color class
  let bgClass, iconClass;
  switch (type) {
    case 'success':
      bgClass = 'bg-success';
      iconClass = 'bi-check-circle-fill';
      break;
    case 'error':
    case 'danger':
      bgClass = 'bg-danger';
      iconClass = 'bi-exclamation-triangle-fill';
      break;
    case 'warning':
      bgClass = 'bg-warning';
      iconClass = 'bi-exclamation-triangle-fill';
      break;
    case 'info':
      bgClass = 'bg-info';
      iconClass = 'bi-info-circle-fill';
      break;
    default:
      bgClass = 'bg-primary';
      iconClass = 'bi-info-circle-fill';
  }

  // Create toast HTML
  const toastHtml = `
    <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert" aria-live="assertive" aria-atomic="true">
      <div class="d-flex">
        <div class="toast-body">
          <i class="bi ${iconClass} me-2"></i>
          ${message}
        </div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
    </div>
  `;

  // Add toast to container
  toastContainer.insertAdjacentHTML('beforeend', toastHtml);
  
  // Initialize and show toast
  const toastElement = document.getElementById(toastId);
  const toast = new bootstrap.Toast(toastElement, {
    autohide: duration > 0,
    delay: duration
  });
  
  toast.show();
  
  // Remove toast element after it's hidden
  toastElement.addEventListener('hidden.bs.toast', () => {
    toastElement.remove();
  });
  
  return toast;
};

// Convenience functions for different toast types
window.showSuccessToast = function(message, duration = 5000) {
  return showToast(message, 'success', duration);
};

window.showErrorToast = function(message, duration = 8000) {
  return showToast(message, 'error', duration);
};

window.showWarningToast = function(message, duration = 6000) {
  return showToast(message, 'warning', duration);
};

window.showInfoToast = function(message, duration = 5000) {
  return showToast(message, 'info', duration);
};

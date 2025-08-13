// Helper to block repeated clicks and show a spinner on the target button
window.withLoading = async (target, callback) => {
  if (target.dataset.loading) return;
  target.dataset.loading = 'true';
  target.classList.add('disabled');
  const spinner = document.createElement('span');
  spinner.className = 'spinner-border spinner-border-sm ms-1';
  spinner.setAttribute('role', 'status');
  spinner.setAttribute('aria-hidden', 'true');
  target.appendChild(spinner);
  try {
    await callback();
  } finally {
    spinner.remove();
    target.classList.remove('disabled');
    delete target.dataset.loading;
  }
};

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
});

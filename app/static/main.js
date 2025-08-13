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

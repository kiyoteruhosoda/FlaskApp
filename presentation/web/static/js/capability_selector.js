(function(global) {
  if (!global) {
    return;
  }

  class CapabilitySelector {
    constructor(root) {
      this.root = root;
      this.filterInput = root ? root.querySelector('[data-capability-selector-filter]') : null;
      this.toggleButton = root ? root.querySelector('[data-capability-selector-toggle]') : null;
      this.toggleLabel = this.toggleButton ? this.toggleButton.querySelector('[data-capability-selector-toggle-label]') : null;
      this.toggleIcon = this.toggleButton ? this.toggleButton.querySelector('[data-capability-selector-toggle-icon]') : null;
      this.listContainer = root ? root.querySelector('[data-capability-selector-list]') || root : null;
      this.selectText = this.toggleButton ? this.toggleButton.dataset.selectText || '' : '';
      this.deselectText = this.toggleButton ? this.toggleButton.dataset.deselectText || '' : '';
      this.items = [];
      this.filterHandler = null;
      this.changeHandler = null;
      this.toggleHandler = null;
      this.mutationObserver = null;
      this.handleCheckboxChange = this.handleCheckboxChange.bind(this);
      this.updateItemSelectionClasses = this.updateItemSelectionClasses.bind(this);
    }

    init({ onFilter = null, onSelectionChanged = null, onToggle = null } = {}) {
      this.filterHandler = onFilter;
      this.changeHandler = onSelectionChanged;
      this.toggleHandler = onToggle;
      this.refreshItems();

      if (this.filterInput) {
        this.filterInput.addEventListener('input', (event) => {
          this.applyFilter(event.target.value);
        });
      }

      if (this.toggleButton) {
        this.toggleButton.addEventListener('click', () => {
          this.toggleVisible();
        });
      }

      if (this.listContainer) {
        this.listContainer.addEventListener('change', this.handleCheckboxChange);
      }

      if (this.listContainer && typeof MutationObserver !== 'undefined') {
        this.mutationObserver = new MutationObserver(() => {
          this.refreshItems();
        });
        this.mutationObserver.observe(this.listContainer, { childList: true, subtree: true });
      }

      if (this.filterInput) {
        this.applyFilter(this.filterInput.value || '');
      } else {
        this.updateToggleState();
      }
    }

    handleCheckboxChange(event) {
      const checkbox = event.target;
      if (!checkbox || checkbox.type !== 'checkbox') {
        return;
      }
      if (typeof this.changeHandler === 'function') {
        this.changeHandler(event);
      }
      this.updateItemSelectionClasses();
      this.updateToggleState();
    }

    updateItemSelectionClasses() {
      (this.items || []).forEach((item) => {
        if (!item) {
          return;
        }
        const checkbox = item.querySelector('input[type="checkbox"]');
        const isChecked = checkbox ? checkbox.checked : false;
        item.classList.toggle('capability-selector-item-selected', isChecked);
      });
    }

    refreshItems() {
      if (!this.listContainer) {
        this.items = [];
        return;
      }
      this.items = Array.from(this.listContainer.querySelectorAll('[data-capability-selector-item]'));
      this.updateItemSelectionClasses();
      this.updateToggleState();
    }

    refresh() {
      this.refreshItems();
    }

    applyFilter(value) {
      if (typeof this.filterHandler === 'function') {
        this.filterHandler(value);
      }
      this.updateToggleState();
    }

    getTogglableItems() {
      return (this.items || []).filter((item) => {
        if (!item) {
          return false;
        }
        if (item.dataset.capabilitySelectorHidden === 'true') {
          return false;
        }
        const checkbox = item.querySelector('input[type="checkbox"]');
        if (!checkbox || checkbox.disabled) {
          return false;
        }
        if (item.style.display === 'none') {
          return false;
        }
        if (typeof item.offsetParent !== 'undefined' && item.offsetParent === null) {
          return false;
        }
        return true;
      });
    }

    toggleVisible() {
      if (!this.toggleButton) {
        return;
      }
      const action = this.toggleButton.dataset.action || 'select';
      const shouldSelect = action === 'select';
      const items = this.getTogglableItems();
      let changed = false;

      items.forEach((item) => {
        const checkbox = item.querySelector('input[type="checkbox"]');
        if (!checkbox) {
          return;
        }
        if (checkbox.checked === shouldSelect) {
          return;
        }
        checkbox.checked = shouldSelect;
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
        changed = true;
      });

      if (!changed && typeof this.changeHandler === 'function') {
        this.changeHandler();
      }

      if (typeof this.toggleHandler === 'function') {
        this.toggleHandler({ shouldSelect, changed });
      }

      this.updateItemSelectionClasses();
      this.updateToggleState();
    }

    updateToggleState() {
      if (!this.toggleButton) {
        return;
      }
      const togglable = this.getTogglableItems();
      const hasItems = togglable.length > 0;
      this.toggleButton.disabled = !hasItems;

      if (!hasItems) {
        this.setToggleAction('select');
        return;
      }

      const allSelected = togglable.every((item) => {
        const checkbox = item.querySelector('input[type="checkbox"]');
        return checkbox ? checkbox.checked : false;
      });

      this.setToggleAction(allSelected ? 'deselect' : 'select');
    }

    setToggleAction(action) {
      if (!this.toggleButton) {
        return;
      }
      this.toggleButton.dataset.action = action;
      if (this.toggleLabel) {
        this.toggleLabel.textContent = action === 'select' ? this.selectText : this.deselectText;
      }
      if (this.toggleIcon) {
        this.toggleIcon.className = action === 'select'
          ? 'fas fa-check-double me-1'
          : 'fas fa-times-circle me-1';
      }
    }
  }

  global.CapabilitySelector = CapabilitySelector;
})(typeof window !== 'undefined' ? window : null);

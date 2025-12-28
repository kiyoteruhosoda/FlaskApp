/**
 * Internationalization helper utilities
 *
 * These helpers allow JavaScript running inside HTML templates to reference
 * Flask-Babel translation strings that are exposed through the global
 * `window.i18nStrings` object.
 *
 * Example usage in a template:
 * <script>
 *   window.i18nStrings = {
 *     'loading': '{{ _("Loading...") }}',
 *     'loadingMore': '{{ _("Loading more...") }}',
 *     'allLoaded': '{{ _("All items loaded") }}',
 *     'error': '{{ _("Error occurred") }}',
 *     'retry': '{{ _("Retry") }}',
 *     'refresh': '{{ _("Refresh") }}',
 *     'search': '{{ _("Search...") }}',
 *     'noResults': '{{ _("No results found") }}',
 *     'itemsLoaded': '{{ _("items loaded") }}',
 *     'photos': '{{ _("photos") }}',
 *     'albums': '{{ _("albums") }}',
 *     'sessions': '{{ _("sessions") }}',
 *     'users': '{{ _("users") }}'
 *   };
 * </script>
 *
 * In JavaScript code:
 * const message = window.i18nStrings?.loading || 'Loading...';
 */

window.i18nStrings = window.i18nStrings || {};

/**
 * Resolve a translated string from the provided key.
 * @param {string} key - Translation key.
 * @param {string} fallback - Fallback string when the key is missing.
 * @returns {string} Resolved translation or the fallback.
 */
function _(key, fallback = key) {
  return window.i18nStrings?.[key] || fallback;
}

/**
 * Retrieve pluralized translations based on the provided count.
 * @param {number} count - Quantity value.
 * @param {string} singular - Key for the singular form.
 * @param {string} plural - Key for the plural form.
 * @returns {string} Resolved translation for the correct plurality.
 */
function ngettext(count, singular, plural) {
  const key = count === 1 ? singular : plural;
  return window.i18nStrings?.[key] || (count === 1 ? singular : plural);
}

// Expose helpers globally
window._ = _;
window.ngettext = ngettext;

/**
 * 国際化支援ユーティリティ
 * 
 * HTMLテンプレート内でJavaScriptから翻訳文字列を使用するためのヘルパー関数
 * Flask-Babelの翻訳文字列をJavaScriptで利用可能にします。
 */

/**
 * HTMLテンプレート内で使用する翻訳文字列の例：
 * 
 * HTMLテンプレート内で以下のように定義：
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
 * JavaScriptで使用：
 * const message = window.i18nStrings?.loading || 'Loading...';
 */

/**
 * 翻訳文字列を取得する関数
 * @param {string} key - 翻訳キー
 * @param {string} fallback - フォールバック文字列
 * @returns {string} 翻訳された文字列またはフォールバック
 */
function _(key, fallback = key) {
  return window.i18nStrings?.[key] || fallback;
}

/**
 * 数値の複数形対応翻訳
 * @param {number} count - 数値
 * @param {string} singular - 単数形のキー
 * @param {string} plural - 複数形のキー
 * @returns {string} 翻訳された文字列
 */
function ngettext(count, singular, plural) {
  const key = count === 1 ? singular : plural;
  return window.i18nStrings?.[key] || (count === 1 ? singular : plural);
}

// グローバルに公開
window._ = _;
window.ngettext = ngettext;

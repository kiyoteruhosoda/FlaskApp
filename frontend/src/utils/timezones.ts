// Profile のタイムゾーン選択に用いる代表的な IANA タイムゾーン一覧。
// 網羅ではなく主要地域を厚めにしたキュレーション。ここに無いゾーンでも、
// 保存済みの値は ProfilePage 側で選択肢へ補完されるため選択状態は保てる。
export const COMMON_TIMEZONES: string[] = [
  'UTC',
  // アジア
  'Asia/Tokyo',
  'Asia/Seoul',
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Taipei',
  'Asia/Singapore',
  'Asia/Bangkok',
  'Asia/Jakarta',
  'Asia/Kolkata',
  'Asia/Dubai',
  // ヨーロッパ
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Madrid',
  'Europe/Rome',
  'Europe/Moscow',
  // アメリカ
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Sao_Paulo',
  // オセアニア
  'Australia/Sydney',
  'Pacific/Auckland',
  'Pacific/Honolulu',
];

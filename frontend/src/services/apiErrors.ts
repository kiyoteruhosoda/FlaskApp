// FastAPI の HTTPException(detail={"error": "code"}) はレスポンスボディを
// {"detail": {"error": "code"}} という形にラップする。かつての Flask 実装は
// {"error": "code"} をトップレベルに直接返していたため、各画面が
// response.data.error を直接参照するコードが T11 の FastAPI 移行後も
// 数十箇所残っていた。その結果、実際の値は常に undefined になり、エラー
// コードに応じた案内文が一切表示されない不具合になっていた
// （バックエンドの唯一の出所であるこの関数に集約し再発を防ぐ）。
export function getApiErrorCode(error: any): string | undefined {
  return error?.response?.data?.detail?.error ?? error?.response?.data?.error;
}

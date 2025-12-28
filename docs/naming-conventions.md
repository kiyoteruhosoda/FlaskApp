# nolumia 命名規則ガイドライン

## データベース・モデル命名

### テーブル名
- **単数形**を使用する
- 例: `user`, `media`, `album`, `tag`, `role`, `permission`

### 中間テーブル名
- 関連する2つのテーブル名を単数形で結合
- 例: `user_roles`, `media_tag`, `album_item`, `role_permissions`

## URL・ルーティング命名

### RESTful API エンドポイント
- リソース名は**単数形**を使用
- 例:
  - `GET /admin/user` - ユーザー一覧
  - `GET /admin/user/<id>` - 個別ユーザー取得
  - `POST /admin/user` - ユーザー作成
  - `PUT /admin/user/<id>` - ユーザー更新
  - `DELETE /admin/user/<id>` - ユーザー削除

### 管理画面ルート
- `@bp.route("/user", methods=["GET"])` - 一覧画面
- `@bp.route("/user/add", methods=["GET", "POST"])` - 追加画面
- `@bp.route("/user/<id>/edit", methods=["GET", "POST"])` - 編集画面

### APIエンドポイント
- `/api/admin/user` - ユーザー管理API
- `/api/admin/media` - メディア管理API

## 変数・関数命名

### Python変数・関数
- `user` (単数形) - 個別のユーザーオブジェクト
- `users` (複数形) - ユーザーのコレクション
- `user_list` - ユーザーのリスト
- `user_count` - ユーザー数

### JavaScript
- `userId` - 個別ユーザーID
- `userList` - ユーザーのリスト
- `editUser()` - ユーザー編集関数

## 統一後の構造

```
/admin/user                     # ユーザー一覧
/admin/user/add                 # ユーザー追加
/admin/user/<id>/edit-roles     # ロール編集
/admin/user/<id>/reset-totp     # TOTP リセット
/admin/user/<id>/delete         # ユーザー削除

/api/admin/user                 # ユーザー一覧API
/api/admin/user/<id>/toggle-active  # アクティブ状態切り替え
```

## この統一化の利点

1. **一貫性**: プロジェクト全体で統一された命名
2. **RESTful準拠**: 標準的なRESTfulAPI設計に沿った命名
3. **可読性**: URLとコードから機能が予測しやすい
4. **保守性**: 新機能追加時の命名ルールが明確

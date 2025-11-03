# Importer Differences: Google Photos vs Local Import

このドキュメントでは、共通のイベントロギング実装以外で Google フォト取り込み (`GoogleImporter`) とローカル取り込み (`LocalImporter`) の挙動に存在する主な差異を整理します。

## セッション識別子の生成
- LocalImporter: `local-<UUID>` 形式のセッション ID を自動生成し、任意の `session_id` オプションを上書きします。【F:features/photonest/application/importing/strategies/local.py†L30-L35】
- GoogleImporter: `google-<account_id>` 形式を使用し、Google アカウントごとに固定のセッション ID を割り当てます。【F:features/photonest/application/importing/strategies/google.py†L24-L28】

## ソース取得処理
- LocalImporter: `directory_path` 配下のメディアファイルを `LocalFileRepository` から列挙し、対象が見つからない場合はエラーを記録します。【F:features/photonest/application/importing/strategies/local.py†L37-L48】
- GoogleImporter: Google フォト API クライアント (`GoogleMediaClient`) を利用して、アカウントに紐づくメディアを取得します。【F:features/photonest/application/importing/strategies/google.py†L30-L35】

## 正規化ステップ
- LocalImporter: `MediaFactory` を使ってファイルパスから `Media` エンティティを生成し、アカウント情報や元ファイルパスを付与します。解析に失敗したファイルはスキップ扱いとなります。【F:features/photonest/application/importing/strategies/local.py†L50-L76】
- GoogleImporter: まだ変換ロジックが未実装のため、取得したソースをそのまま次のステップへ渡します。【F:features/photonest/application/importing/strategies/google.py†L37-L41】

## メディア登録
- LocalImporter: `ImportDomainService` を通じてメディア登録を実施し、重複・成功・スキップの別に応じて結果カウンタを更新します。【F:features/photonest/application/importing/strategies/local.py†L78-L101】
- GoogleImporter: 取り込み処理が未実装のため、すべてのアイテムをスキップとして扱い、"Google インポートは未実装です" のエラーを付与します。【F:features/photonest/application/importing/strategies/google.py†L43-L50】

## エラーの扱い
- LocalImporter: ファイル未検出・解析失敗・登録例外など個別のケースで `ImportResult` にエラーを追加します。【F:features/photonest/application/importing/strategies/local.py†L42-L43】【F:features/photonest/application/importing/strategies/local.py†L60-L71】【F:features/photonest/application/importing/strategies/local.py†L87-L95】
- GoogleImporter: 未実装である旨のエラーだけを追加し、個別要因の区別は行っていません。【F:features/photonest/application/importing/strategies/google.py†L45-L49】

## ドメインサービス依存性
- LocalImporter: メディア生成と登録のために `MediaFactory` と `ImportDomainService` の両方へ依存します。【F:features/photonest/application/importing/strategies/local.py†L16-L27】
- GoogleImporter: メディア登録に `ImportDomainService` を利用しますが、メディア生成は行っていません（今後の実装が必要）。【F:features/photonest/application/importing/strategies/google.py†L16-L22】

上記の差異は、Google フォト連携がまだ初期段階であり、実際のメディア登録フローが実装されていないことに起因します。今後 Google 側の取り込みを完成させる際には、ローカル取り込みと同等のメディア生成・登録ロジックおよび詳細なエラー分類を導入する必要があります。

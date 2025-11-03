# Importer Differences: Google Photos vs Local Import

このドキュメントでは、共通のイベントロギング実装以外で Google フォト取り込み (`GoogleImporter`) とローカル取り込み (`LocalImporter`) の挙動に存在する主な差異を整理します。

## セッション識別子の生成
- LocalImporter: `local-<UUID>` 形式のセッション ID を自動生成し、任意の `session_id` オプションを上書きします。【F:features/photonest/application/importing/strategies/local.py†L30-L35】
- GoogleImporter: `google-<account_id>` 形式を使用し、Google アカウントごとに固定のセッション ID を割り当てます。【F:features/photonest/application/importing/strategies/google.py†L24-L28】

## ソース取得処理
- LocalImporter: `directory_path` 配下のメディアファイルを `LocalFileRepository` から列挙し、対象が見つからない場合はエラーを記録します。【F:features/photonest/application/importing/strategies/local.py†L37-L48】
- GoogleImporter: Google フォト API クライアント (`GoogleMediaClient`) を利用して、アカウントに紐づくメディアを取得します。【F:features/photonest/application/importing/strategies/google.py†L30-L35】

## 正規化ステップ
- LocalImporter / GoogleImporter 共通: `MediaFactory` を使ってソースから `Media` エンティティを生成し、アカウント情報や元ソース ID を `extras` に付与します。解析に失敗したソースはスキップ扱いとなります。【F:features/photonest/application/importing/strategies/local.py†L50-L76】【F:features/photonest/application/importing/strategies/google.py†L41-L64】

## メディア登録
- LocalImporter / GoogleImporter 共通: `ImportDomainService` を通じてメディア登録を実施し、重複・成功・スキップの別に応じて結果カウンタを更新します。【F:features/photonest/application/importing/strategies/local.py†L78-L101】【F:features/photonest/application/importing/strategies/google.py†L66-L89】

## エラーの扱い
- LocalImporter / GoogleImporter 共通: 解析や登録で例外が発生した場合は `ImportResult` にエラーを追加し、該当ソースをスキップとして扱います。【F:features/photonest/application/importing/strategies/local.py†L60-L95】【F:features/photonest/application/importing/strategies/google.py†L49-L88】

## ドメインサービス依存性
- LocalImporter / GoogleImporter 共通: メディア生成のために `MediaFactory` を使用し、登録は `ImportDomainService` に委譲します。【F:features/photonest/application/importing/strategies/local.py†L16-L27】【F:features/photonest/application/importing/strategies/google.py†L16-L25】

Google フォト取り込みの実装がローカル取り込みの責務分担と揃ったため、差異は主にセッション ID の生成方式とソース取得手段に限定されました。

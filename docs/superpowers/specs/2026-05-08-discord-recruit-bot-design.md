# Discord 遊ぶ募集Bot 設計書

**作成日:** 2026-05-08  
**プロジェクト名:** aso-bot  
**言語/フレームワーク:** Python 3.11+ / discord.py 2.x

---

## 概要

Discordサーバーで「一緒に遊ぶメンバー」を募集するためのBot。
スラッシュコマンドで募集を作成し、ボタンUIで参加・補欠・辞退を管理。
開始前にDM通知、開始時刻にサーバーでメンションを行う。

---

## 要件

1. 誰でも `/recruit` で募集作成可能
2. ボタンUIで参加状況を管理
3. 開始時刻・ゲーム名・参加可能ロール名（ID不要）を指定可能
4. 開始30分前・10分前・5分前にDMで通知
5. 参加ボタン以外に補欠・遅れて参加・途中のみ参加（理由入力可）を用意
6. 辞退は「開始X分前まで」と設定可能
7. 開始時刻に参加メンバー全員をサーバーでメンション
8. 参加可能ロールを募集ごとに作成者が設定可能（任意）
9. 複数サーバー対応、任意チャンネルで使用可能

---

## アーキテクチャ

**採用アプローチ:** シンプル単体Bot（Cogで適度にモジュール分割）

### 使用ライブラリ

| ライブラリ | バージョン | 用途 |
|---|---|---|
| discord.py | 2.x | スラッシュコマンド・モーダル・ボタン |
| aiosqlite | latest | 非同期SQLite操作 |
| APScheduler | 3.x | タイマー通知スケジューリング |
| python-dotenv | latest | .envからトークン読み込み |

### ファイル構成

```
aso-bot/
├── main.py              # Bot起動エントリーポイント
├── config.py            # 設定読み込み（.envから）
├── database.py          # SQLite初期化・共通DB操作
├── scheduler.py         # APSchedulerタイマー管理
├── cogs/
│   ├── recruit.py       # /recruit コマンド・募集管理・ボタンUI
│   └── notifications.py # DM通知・開始時メンション処理
├── models/
│   └── schema.sql       # DBスキーマ定義
├── setup.sh             # Oracle Cloud用セットアップスクリプト
├── .env                 # トークン等（git管理外）
├── .env.example         # テンプレート（git管理）
├── .gitignore
├── requirements.txt
├── CLAUDE.md            # 次回セッション用プロジェクト概要
└── bot.db               # SQLiteファイル（git管理外、実行時生成）
```

---

## データベース設計

### recruitments テーブル

| カラム | 型 | 説明 |
|---|---|---|
| id | INTEGER PRIMARY KEY | 募集ID |
| guild_id | TEXT NOT NULL | サーバーID |
| channel_id | TEXT NOT NULL | 投稿チャンネルID |
| message_id | TEXT | 募集メッセージID（投稿後に更新） |
| creator_id | TEXT NOT NULL | 作成者DiscordユーザーID |
| game | TEXT NOT NULL | ゲーム名（最大100文字） |
| scheduled_time | TEXT NOT NULL | 開始予定時刻（ISO 8601形式） |
| max_players | INTEGER NOT NULL DEFAULT 0 | 最大人数（0=無制限） |
| required_role_name | TEXT | 参加可能ロール名（NULL=全員OK） |
| cancel_deadline_minutes | INTEGER NOT NULL DEFAULT 0 | 辞退期限（開始X分前まで、0=制限なし） |
| status | TEXT NOT NULL DEFAULT 'open' | open / closed / cancelled |
| created_at | TEXT NOT NULL | 作成日時（ISO 8601形式） |

### participants テーブル

| カラム | 型 | 説明 |
|---|---|---|
| id | INTEGER PRIMARY KEY | |
| recruitment_id | INTEGER NOT NULL | recruitments.id FK |
| user_id | TEXT NOT NULL | DiscordユーザーID |
| join_type | TEXT NOT NULL | confirmed / substitute / late / partial |
| reason | TEXT | 理由・メモ（任意、最大200文字） |
| available_until | TEXT | 途中参加の退出予定時刻（ISO 8601形式） |
| joined_at | TEXT NOT NULL | 参加登録日時 |

**UNIQUE制約:** (recruitment_id, user_id) — 同一ユーザーの重複参加を防止

### notifications テーブル

| カラム | 型 | 説明 |
|---|---|---|
| id | INTEGER PRIMARY KEY | |
| recruitment_id | INTEGER NOT NULL | recruitments.id FK |
| minutes_before | INTEGER NOT NULL | 何分前通知か（30/10/5） |
| sent | INTEGER NOT NULL DEFAULT 0 | 送信済みか（0=未送信、1=送信済み） |

---

## ユーザーフロー

### 募集作成

1. ユーザーが `/recruit` を実行
2. モーダルが開く（フィールド一覧）
   - ゲーム名（必須、最大100文字）
   - 開始日時（必須、形式: `YYYY/MM/DD HH:MM`）
   - 最大人数（任意、数字のみ、空欄=無制限）
   - 参加可能ロール名（任意、空欄=全員OK）
   - 辞退期限（任意、数字のみ、例: `30` = 開始30分前まで）
3. Botがバリデーション実施（日時形式・数値チェック、ロール名存在確認）
4. エラーがあれば本人にのみ見えるエラーメッセージ表示
5. 成功すればチャンネルに募集Embedを投稿
6. DBに募集情報を保存し、通知スケジュールを登録

### 募集Embed表示例

```
🎮 [ゲーム名] 募集
─────────────────────────────
📅 開始時刻: 2026/05/10 21:00
👥 参加者: 0/5（最大5名）
🔒 参加条件: @FPSメンバー のみ
⏰ 辞退期限: 開始30分前まで
📋 作成者: @username
─────────────────────────────
✅ 参加 (0)
🔄 補欠 (0)
⏰ 遅れて参加 (0)
🕐 途中のみ (0)

[ ✅ 参加 ] [ 🔄 補欠 ] [ ⏰ 遅れて参加 ] [ 🕐 途中のみ ] [ ❌ 辞退 ]
```

### ボタン動作詳細

| ボタン | 動作 | モーダル |
|---|---|---|
| ✅ 参加 | 即座に参加登録 | なし |
| 🔄 補欠 | 補欠として登録 | なし |
| ⏰ 遅れて参加 | モーダルで理由入力後に登録 | 理由（任意） |
| 🕐 途中のみ | モーダルで情報入力後に登録 | 退出予定時刻（必須）・理由（任意） |
| ❌ 辞退 | 参加取り消し（期限内のみ） | なし |

- ロール制限がある場合、対象外ユーザーのボタン押下は本人のみ見えるエラーで拒否
- 辞退期限超過後の辞退ボタンは本人のみ見えるエラーで拒否
- 満員時の参加ボタンは補欠への変更を促すメッセージを表示
- 各ボタン操作後にEmbedを更新して参加人数を反映

### 通知フロー

- 開始30分前・10分前・5分前: 参加者（confirmed/late/partial）全員にDM送信
- 補欠はDM通知対象外
- 開始時刻になったら投稿チャンネルで参加者全員をメンション
- DM受信が無効なユーザーへの通知失敗はエラーとせずログに記録

---

## セキュリティ

- Botトークンは `.env` のみに保存、コードに直書きしない
- `.gitignore` に `.env` と `bot.db` を追加
- モーダル入力値はすべてバリデーション実施
  - ゲーム名: 1〜100文字
  - 日時: 厳密にパース、過去日時は拒否
  - 人数・辞退期限: 正の整数のみ
  - ロール名: サーバー内ロール一覧で存在確認（外部入力をそのまま使わない）
- 参加ロール制限チェックはBot側（サーバーサイド）で実施
- レート制限: ボタン連打によるスパムはdiscord.pyの標準クールダウンで対処

---

## デプロイ（Oracle Cloud Always Free）

### 構成
- Oracle Cloud Always Free ARM VM（Ubuntu 22.04）
- systemdサービスとして登録（クラッシュ時自動再起動）

### セットアップスクリプト（setup.sh）
```bash
# Python環境構築 → pip install → .env配置 → systemdサービス登録
```

### 更新コマンド
```bash
git pull && sudo systemctl restart aso-bot
```

### ログ確認
```bash
journalctl -u aso-bot -f
```

---

## 作業状況保存（約束1への対応）

- 実装完了ごとに `git commit` でこまめに保存
- 本ドキュメント（設計書）を `docs/` に保存
- `CLAUDE.md` にプロジェクト概要・現在の状態を記載
- 次回セッション開始時に Claude は `CLAUDE.md` と本ドキュメントを読んで文脈を復元する

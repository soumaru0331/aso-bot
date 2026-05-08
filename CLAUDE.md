# AsoBot プロジェクト

## 概要
Discordで遊ぶメンバーを募集するBot。Python + discord.py 2.x。
複数サーバー対応。スラッシュコマンド `/recruit` でモーダルを開いて募集作成。

## 技術スタック
- discord.py 2.x（スラッシュコマンド、モーダル、Persistent View）
- aiosqlite（非同期SQLite）
- APScheduler 3.x（DM通知タイマー）
- python-dotenv（.envからトークン読み込み）

## 主要ファイル
- `main.py` — Bot起動、Persistent View再登録、Cog読み込み
- `cogs/recruit.py` — /recruit コマンド、モーダル、ボタン全種
- `cogs/notifications.py` — DM通知・開始時メンション関数
- `scheduler.py` — APScheduler管理・再起動時リカバリ
- `database.py` — SQLite初期化（DB_PATH は .env で設定）
- `utils/validators.py` — 入力バリデーション（純粋関数）
- `utils/embed_builder.py` — Embed生成（純粋関数）
- `models/schema.sql` — DBスキーマ

## 設計上の注意
- ボタンはPersistent View（custom_id=`recruit:action:recruitment_id`形式）
- Bot再起動時に `main.py` の `setup_hook` でopen募集のViewを全再登録する
- 日時入力はJST（UTC+9）として扱い、isoformat()でDB保存
- DM送信失敗（Forbidden）はエラーとせずprint出力のみ
- トークンは `.env` のみ（絶対にコードに書かない）

## テスト実行
```bash
python -m pytest tests/ -v
```

## ローカル起動
```bash
python main.py
```

## デプロイ（Oracle Cloud Always Free）
```bash
bash setup.sh
```
更新時: `git pull && sudo systemctl restart aso-bot`
ログ確認: `journalctl -u aso-bot -f`

## セキュリティ
- `.env` と `bot.db` は `.gitignore` で除外済み
- ロール制限チェックはBot側（サーバーサイド）で実施
- モーダル入力は全フィールドでバリデーション実施

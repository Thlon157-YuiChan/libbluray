# BDAV/BDMV ディスク再生ラッパーアプリ 要件定義

## 1. 概要

BD-RE 録画ディスク (BDAV) および市販 BD-ROM (BDMV) を再生するための
ラッパーアプリケーション。libbluray + libmmbd (MakeMKV) + mpv を
統合し、環境変数やコマンドラインの手動設定なしで再生可能にする。

## 2. 背景・課題

- VLC 3.0 は BDAV のタイトル切り替えに非対応 (クラッシュ)
- libbluray 単体では AACS 復号ができない (libmmbd/MakeMKV が必要)
- 環境変数 (LD_LIBRARY_PATH, PATH, MAKEMKVCON) の手動設定が必要
- MakeMKV は 30 日の評価期間あり
- Host Certificate が revoke されているため、改造版 libaacs では復号不可

## 3. 機能要件

### 3.1 ディスク検出
- /dev/sr0 等の光学ドライブを自動検出
- BDAV / BDMV の自動判別 (libbluray disc_format)
- ディスクラベル・AACS バージョン表示
- ディスク挿入/排出の検出 (ポーリング or udev)

### 3.2 タイトル管理
- タイトル一覧の取得 (bd_get_titles + bd_get_title_info)
- タイトル名・再生時間・チャプター数の表示
- メインタイトル (最長) の自動選択
- タイトル切り替え (mpv --edition=N 経由)
- チャプター一覧・チャプター移動

### 3.3 再生
- mpv をバックエンドとして使用 (libbluray + libmmbd)
- ハードウェアアクセラレーション (VA-API) 自動有効化
- 音声トラック切り替え
- 字幕 (ARIB) 表示/非表示
- シーク (時間指定・チャプター指定)
- 再生速度変更
- フルスクリーン切り替え

### 3.4 AACS 復号
- libmmbd (MakeMKV) を自動検出・読み込み
- makemkvcon バイナリの自動検出 (PATH / ~/.local/bin)
- libdriveio.so.0 の自動検出
- 復号失敗時のエラーメッセージ表示
- MakeMKV 評価期間の残日数表示

### 3.5 設定
- ライブラリパスの自動設定 (LD_LIBRARY_PATH 不要)
- デフォルト再生タイトル (メインタイトル / 最初のタイトル)
- デフォルト音声・字幕トラック
- ハードウェアアクセラレーション ON/OFF
- リージョンコード設定

## 4. 非機能要件

### 4.1 環境
- OS: Linux (Debian/Ubuntu)
- 依存: libbluray (新ビルド), libmmbd, libdriveio, makemkvcon, mpv
- Python 3 + PyQt6 or GTK4 (GUI フレームワーク)
- または C/C++ + Qt (パフォーマンス重視)

### 4.2 配置
- ユーザー領域 (~/.local/) にインストール (sudo 不要)
- 環境変数の設定不要 (アプリ内部で LD_LIBRARY_PATH を設定)
- .desktop ファイルで GUI ランチャー登録

### 4.3 エラーハンドリング
- ディスク未挿入: 待機画面表示
- AACS 復号失敗: エラーメッセージ + 原因表示
- MakeMKV 評価期間切れ: 警告表示
- libmmbd 未検出: インストールガイド表示

## 5. アーキテクチャ

```
┌─────────────────────────────────────┐
│         GUI (PyQt6 / GTK4)          │
├─────────────────────────────────────┤
│         コントローラー               │
│  - ディスク検出 (udev/polling)       │
│  - タイトル管理                      │
│  - mpv プロセス管理 (subprocess)     │
├──────────┬──────────┬───────────────┤
│ libbluray│ libmmbd  │    mpv        │
│ (BDAV)   │(MakeMKV) │  (再生)       │
├──────────┴──────────┴───────────────┤
│         /dev/sr0 (光学ドライブ)      │
└─────────────────────────────────────┘
```

### 5.1 再生フロー
1. ディスク挿入検出
2. libbluray でディスク構造解析 (BDAV/BDMV 判別)
3. タイトル一覧取得 → GUI に表示
4. ユーザーがタイトルを選択 (またはメインタイトル自動選択)
5. mpv を subprocess で起動 (`mpv bd://N --bluray-device=/dev/sr0`)
6. mpv が libbluray + libmmbd を使用して再生
7. チャプター/タイトル切り替えは mpv の IPC (JSON IPC) で制御

### 5.2 mpv IPC 制御
mpv の `--input-ipc-server` オプションで JSON IPC ソケットを作成し、
タイトル切り替え・シーク・音声/字幕切り替えをプログラムから制御可能。

```bash
mpv --input-ipc-server=/tmp/mpv-socket "bd://longest" --bluray-device=/dev/sr0
```

## 6. 実装優先度

1. **Phase 1**: CLI ラッパー (シェルスクリプト) — 現在の vlc-bd を拡張
2. **Phase 2**: Python + PyQt6 GUI (タイトル選択、再生制御)
3. **Phase 3**: mpv IPC による高度な制御 (チャプター、音声切り替え)
4. **Phase 4**: ディスク挿入自動検出、設定永続化

## 7. 現在のセットアップ (Phase 1 相当)

既に作成済み:
- `~/.local/bin/vlc-bd` — VLC ラッパー
- `~/.local/bin/makemkvcon` — MakeMKV バイナリ
- `~/.local/lib/libmmbd.so.0` — MakeMKV ライブラリ
- `~/.local/lib/libdriveio.so.0` — MakeMKV I/O ライブラリ
- `~/.local/lib/libbluray.so.4.0.0` — 新ビルド libbluray
- `~/.local/lib/libbluray.so.2` — symlink
- `~/.config/mpv/mpv.conf` — hwdec=vaapi
- `~/.local/share/applications/vlc.desktop` — 修正済み .desktop

**推奨**: VLC ではなく **mpv** を使用 (BDAV タイトル切り替えが安定)
```bash
mpv "bd://longest" --bluray-device=/dev/sr0
```
EOF
echo "written"
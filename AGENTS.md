# AGENTS.md

libbluray — Blu-ray 再生支援ライブラリ (C99 / Meson)。
外部 player (VLC, MPlayer 等) から-linking される **ライブラリ** であり、
CLI ツールとライブラリ本体の両方が同居する。

---

## ビルド / 実行

```bash
meson setup build            # 初回のみ
meson compile -C build       # = ninja -C build
```

- CI (.gitlab-ci.yml) は `meson setup build` → `meson compile -C build` を使用。
  Windows は `package/crossfiles/<arch>.meson` のクロスファイルを使う。
- 静的リンクは `meson setup build --default-library=static`。
- 依存: libxml2 / freetype2 / fontconfig (いずれも任意、auto)、libudfread
  (無ければ `contrib/libudfread` をサブプロジェクトとしてビルド)。
- Java + Ant があれば BD-J の JAR も作られる (無ければ自動的に無効化される)。

### よく使うオプション (`meson_options.txt`)

| オプション | 既定 | 効果 |
|---|---|---|
| `enable_tools` | true | `bd_info` / `bd_list_titles` / `bd_splice` をビルド |
| `enable_examples` | false | `index_dump` / `libbluray_test` / `sound_dump` |
| `enable_devtools` | false | `bdjo_dump` / `bdj_test` / `clpi_dump` / `hdmv_test` / `mobj_dump` / `mpls_dump` |
| `enable_docs` | false | Doxygen (doxygen バイナリが必須) |
| `libxml2` / `freetype` / `fontconfig` | auto | 機能検出 |
| `bdj_jar` / `jdk_home` / `bdj_type` | auto / '' / j2se | BD-J 関連 |
| `embed_udfread` | true | libudfread をサブプロジェクトビルドする場合、インストールしない |

> devtools / examples は既定で **ビルドされない**。パーサ単体を試すときは
> `-Denable_devtools=true -Denable_examples=true` を付けること。

### テスト

- Meson の `test()` 定義は **存在しない** (CI もビルドのみ)。
  自動テスト Infrastructure が無いので、手動確認が基本。
- 手動確認の手段:
  - `build/src/tools/bd_info <dir>` — ディスク情報
  - `build/src/tools/bd_list_titles <dir>` — タイトル一覧
  - `build/src/examples/libbluray_test <dir> [title]` — タイトル選択して
    `streamdump.m2ts` にダンプ (再生の疎通確認)
  - `build/src/devtools/mpls_dump <file.mpls>` / `clpi_dump <file.clpi>` —
    **単一ファイルのパーサを単体で検証できる**。パーサ改造時は最速の手段。

---

## ディレクトリ構成と役割

```
src/
  libbluray/          ライブラリ本体 (public API は bluray.h)
    bdnav/            ナビゲーション: index/mpls/clpi/meta/sound の解析と title 構築
    decoders/         m2ts demux/filter, PG/IG/textST のデコード
    disc/             ディスク (BD-ROM) 抽象・UDF・AACS/BD+・properties
    hdmv/             HDMV VM (MovieObject 実行) と命令セット
    bdj/              BD-J (Java) ランタイム + JNI ネイティブ + Java ソース
  file/               ファイル/ディレクトリ/マウントの OS 依存層
  util/               bits, logging, refcnt, array, mutex, event_queue, strutl
  tools/              配布用 CLI (enable_tools)
  examples/           サンプル (enable_examples)
  devtools/           開発用ダンパ (enable_devtools)
doc/                  Doxyfile, CODING.RULES, HOWTO.PATCH
jni/                  JNI ヘッダの同梱 (JDK 不要でビルドする fallback)
contrib/libudfread/   libudfread サブプロジェクト
```

### 処理の流れ (データフロー)

```
bd_open(path)                          [bluray.c]
  └─ disc_open()                       [disc/disc.c]  ディレクトリ or UDF イメージを開く
       └─ bdpriv_dec_init()            [disc/dec.c]   AACS / BD+ 検出 (無ければ dec = NULL)
  └─ _fill_disc_info()                 [bluray.c]     index.bdmv を読む → disc_info

bd_get_titles()                        [bluray.c]
  └─ nav_get_title_list()              [bdnav/navigation.c]
       └─ "BDMV/PLAYLIST" を走査 → mpls_get() で各 .mpls を解析

bd_select_title(idx)                   [bluray.c]
  └─ _open_playlist() → nav_title_open() [bdnav/navigation.c]
       └─ mpls_get() + clpi_get()      [bdnav/mpls_parse.c, clpi_parse.c]
       └─ NAV_TITLE (clip list, marks, chapters) を構築

bd_read(buf, len)                      [bluray.c]
  └─ m2ts_filter → m2ts_demux          [decoders/]
```

- 再生中、BD-J からの要求は `bdpriv_*` 関数群 (bluray.c) が public API を経由して
  内部状態 (__bdpriv_seek, __bdpriv_play_playlist_at, __bdpriv_play_title_internal 等) を操作する。
- メニュー (HDMV) がある場合のみ `hdmv_vm` が起動し、`bd_play()` は
  FIRST_PLAY タイトルから入る。メニュー無しディスクは
  `bd_get_titles()` + `bd_select_title()` を使う運用。

---

## コード規約 (`doc/CODING.RULES`)

- **K&R / 1TBS**: 関数の opening brace は宣言の次の行、制御構文の brace は同じ行。
- **4 スペース**インデント、TAB 禁止、trailing whitespace 禁止。
- 関数名は **全部小文字** (linux kernel 風)。
- 外部公開する関数はヘッダのセクションコメントにまとめる。
  同一 .c 内だけが使う関数は `_` 始まりにして .c 内で forward 宣言する。
- 確保したメモリは必ず `X_FREE()` で解放 (NULL 代入も兼ねる)。
- ポインタは宣言時に `NULL` 初期化することが望ましい。
- 内部 API には `BD_PRIVATE`、公開 API には `BLURAY_API_EXPORT` を付ける。
  公開ヘッダのリストは `src/libbluray/meson.build` の `libbluray_api_headers`。
  ここに追加しないと **インストールされない**。

### ビルドシステム上の注意

- ソースファイルのリストは `src/meson.build` に **明示列挙**されている。
  新しい .c を足したら必ずここに追記すること (自動収集されない)。
- 内部ヘッダの install コピーも `src/libbluray/meson.build` にある。
- プラットフォーム分岐 (Windows / Darwin / POSIX) は `src/meson.build` の
  `file/dir_*.c` 選択と、`src/file/` の OS 別ファイルで吸収する。

---

## 実装上の重要な非自明な点

### UO mask は「1 = 許可」

`BD_UO_MASK` (bdnav/uo_mask_table.h) は 1 ビットが 1 のとき **許可**。
`uo_mask_combine()` (bdnav/uo_mask.h) は **OR** 合成。
mask が 0 だと「シーク不可・停止不可」になる。playlist に mask が無い形式を
扱うときは **全許可のマスク** を明示的に設定すること。

### シグネチャ検査は 1 箇所に集約

`bdmv_parse_header()` (bdnav/bdmv_parse.c) が全ファイル形式の
シグネチャ + バージョン (0100/0200/0240/0300 のみ許可) を検査する。
新しいファイル形式に対応するときはここを拡張するのが本来の入口。
`.h` の `bdmv_parse_header()` は `BD_PRIVATE`。

### パスは disc-relative

`disc_open_path(disc, "BDMV/PLAYLIST/00000.mpls")` のように
**ディスクルートからの相対パス** を渡す。`disc_open_dir()` / `disc_open_file()` も同様。
OS 依存のパス結合は `src/util/strutl.c` の `str_printf` + `DIR_SEP` で行う
(`DIR_SEP_CHAR` は Win で `'\\'`、POSIX で `'/'`)。

### ビットストリーム読み出し

`util/bits.h` の BITSTREAM。`bs_read(bs, n)` は n <= 32。
`bs_read_string()` は NUL 終端しないので、バッファは自分で 0 クリアする。
`bs_seek_byte()` は失敗しうる (戻り値チェック必須)。
可変長フィールドは `len` を読んで `pos + len` へ seek する方式
(区切り長を信用せず、必ず長さで読み飛ばす)。

### refcount

CLPI は `clpi_get()` で取得し、`clpi_unref()` で解放 (disc 側キャッシュ経由)。
NAV_TITLE が所有し、タイトル close 時にまとめて解放される。

### AVCHD 8.3 ファイル名

`disc_open_path()` が `BDMV/index.bdmv` を開けなかった時に
`BDMV/INDEX.BDM` を試し、8.3 命名と判定したら以後
`.mpls`→`.MPL` / `.clpi`→`.CPI` / `.m2ts`→`.MTS` / `.bdmv`→`.BDM` に変換する
(disc/disc.c の `_avchd_file_name`)。disc ごとに 1 回だけ判定し、
`struct bd_disc` の `avchd` (-1 = 未判定) にキャッシュする。

### タイトルとチャプターの数え方

- チャプター = PlayListMark のうち `mark_type == BD_MARK_ENTRY (0x01)` のもの。
- 再生位置の検索は clip 内の SPN と 45kHz タイムスタンプの両方を使う。
  45kHz = 90kHz の 1/2 (`bd_tell_time()` の値は 90kHz)。
- `bd_get_titles()` の `min_title_length` は **秒**。内部では 45000 倍される。

---

## BDAV 対応 (HDMV TS モードまで実装済み)

- 設計・実装メモ: **`doc/BDAV_SUPPORT.md`** (仕様 / 差分 / 方針 / 実装状況)
- 変更点と対応過程のまとめ: **`doc/BDAV_IMPLEMENTATION.md`**
- BDAV (BD-RE Part 3) は `BDAV/` ルート + `index.bdav`/`info.bdav` +
  `PLAYLIST/*.rpls` (PLST0100) + `CLIPINF/*.clpi` (M2TS0100) を持つ。
  BDMV との差分 (PlayItem 20 バイト・STN なし、PlayListMark 46 バイト、
  UO mask なし、MovieObject なし) が同ドキュメントにまとめてある。
- **HDMV TS プレイモード** の読み出しは実装済み。`disc_format()` /
  `disc_root_dir()` / `disc_app_path()` でルートを抽象化し、
  clpi / mpls / index の各パーサに BDAV 分岐を入れた。
- BDAV の `.rpls` には STN テーブルが無いので、**ストリーム情報は CLPI の
  ProgramInfo から合成**している (`navigation.c` の `_stn_from_clpi()`)。
- **UO mask は BDAV には無い**ので `uo_mask_get_all()` (全許可) を使う。
  0 にするとシーク・停止まで塞がる (`uo_mask.h` は OR 合成・1=許可)。
- **チャプター判定は type 1 だけでは無い**。BDAV は type 4 をチャプターに使う
  ので `_pl_is_chapter()` に集約している (BDAV は type 1 と type 4 の両方)。
- 未対応: **HEVC TS** (BDAV v5.0) と **SESF**。メタデータ構造は HEVC TS と
  共通の可能性が高いが、HEVC TS モードの index/playlist が別形式かは未確認。

### BDAV / BDMV 回帰テスト

```bash
meson setup build -Denable_devtools=true -Denable_examples=true
meson compile -C build
./test/bdav/run_tests.sh build
```

`test/bdav/make_testdata.py` が合成 M2TS (PCR 不連続入り) から
BDAV 形式と BDMV 形式のディスクを生成し、`run_tests.sh` が
「ディスク検出 / タイトル列挙 / 読み出しが元とバイト一致」を確認する。
BDAV 側のメタデータは `sorshi/bdav` の writer と同一構造 (chotBDAV 互換)。

---

## その他

- `ChangeLog` はリリース時に更新される。
- ログ出力は `util/log_control.h` の `DBG_*` ビット集合で制御。
  `bd_debug(NULL, ...)` で fatal 扱いも表現できる。
- `disc_property_get/put()` (disc/properties.c) は
  `~/.cache/bluray/properties/` に永続化されたアプリ側の設定を保存する
  (例: 既知の main feature playlist id)。ディスク ID をキーに使う。

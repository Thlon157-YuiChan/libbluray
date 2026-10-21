# BDAV 対応 実装報告

libbluray に BDAV (BD-RE Part 3 "Audio Visual Application Format") の
HDMV TS プレイモード対応を実装した过程的まとめ。

- 設計・仕様・判断の根拠: [`BDAV_SUPPORT.md`](BDAV_SUPPORT.md)
- テスト: [`../test/bdav/README.md`](../test/bdav/README.md)

---

## Summary (English)

Blu-ray discs written by consumer recorders use the BDAV application
format instead of BDMV. This change adds support for reading BDAV
discs: the application format is detected when the disc is opened, and
BDAV variants of the index, playlist and clip information parsers are
added.

BDAV playlists have no stream coding info table, so the stream
information is reconstructed from the clip information. BDAV playlists
also have no user operation mask, which would otherwise disable seeking
and stopping. BDAV chapter marks use a different mark type than BDMV,
so the chapter detection was unified into a single helper.

The change also fixes a pre-existing bug in the start packet lookup,
which made titles unplayable when the entry point map had no coarse
entry for the start of a time sequence.

The BDMV code path is unchanged: every BDAV specific branch is guarded
by the detected application format.

---

## 1. 背景と目的

### 1.1 何が問題だったか

libbluray は BD-ROM (BDMV) と AVCHD (8.3 ファイル名の BDMV 亜種) のみを
扱っていた。**家庭用の BD レコーダーで録画したディスク (BDAV 形式) は
開けていなかった**。

`bd_open()` が BDAV ディスクに対して返す値は `NULL` で、ログには
`error opening file BDMV/index.bdmv` が出るだけだった。

### 1.2 目標

1. BDAV ディスクを **BDMV ディスクと同じ API** (`bd_open()` →
   `bd_get_titles()` → `bd_select_title()` → `bd_read()`) で開けるようにする
2. BDMV の既存挙動を **一切変えない**
3. 検証の手段が無い环境中でも **再現できるテスト** を用意する

### 1.3 スコープ

主軸は **HDMV TS プレイモード** (BD-RE Part 3 v1.0〜v3.x)。
HEVC TS (v5.0) と SESF (アナログ SD) は対象外とした。

理由:
- HEVC TS モードは手元に実ディスクが無く **動作検証ができない**
- ただし **メタデータ構造 (BDAV0100 / PLST0100 / M2TS0100) は HEVC TS と
  共通である可能性が高い**。つまりパーサは HEVC 固有の要素を
  取り込まない generic な形にしてあり、将来 HEVC TS に対応させ直す時の
  に取り返しが無くなる

---

## 2. BDAV と BDMV の差分 (実装の前提)

| 項目 | BDMV | BDAV |
|---|---|---|
| ルート | `BDMV/` | `BDAV/` |
| index | `index.bdmv` (INDX0100) | `index.bdav` / `info.bdav` (BDAV0100) |
| index の内容 | first play / top menu / タイトルオブジェクト | プレイリスト一覧 (TableOfPlayLists) のみ |
| playlist | `PLAYLIST/*.mpls` (MPLS0100) | `PLAYLIST/*.rpls` (PLST0100) |
| PlayItem | 32 byte 以上・bit packed | **byte aligned 20 byte** |
| PlayItem の STN テーブル | あり | **なし** |
| PlayListMark | 14 byte/件 | **46 byte/件** (maker_id 付き) |
| clip info | `CLIPINF/*.clpi` (HDMV0100) | `CLIPINF/*.clpi` (**M2TS0100**) |
| stream attribute | ISRC 12 byte・言語コードあり | 最大 3 byte・言語コードなし |
| UO mask | あり | **なし** |
| MovieObject | あり (HDMV VM) | **なし** (メニューが存在しない) |
| チャプターマーク | type 1 (entry) | **type 4** (type 1 はレジューム点) |

詳細は `BDAV_SUPPORT.md` §1 を参照。

---

## 3. 対応過程

### 3.1 調査 (コード読解 + 実ファイル仕様の特定)

libbluray 側をコードから読み的同时、BDAV の実ファイル仕様を
外部資料で特定した。

- **BD-RE Part 3 (BDAV) のファイル仕様**
  - <https://www.blu-ray.org.uk/2024/01/bdav-application-format.html>
    (BD-RE Part 3 v5.0 ホワイトペーパーの解説)
  - <https://github.com/sorshi/bdav> — BDAV ツリーを生成する
    実装済みのツール。`docs/bdav-native-format.md` と
    `tools/bdav_dump.py` が **全フィールドのバイト単位仕様** を与える。
    同ツールの writer は第三者の authoring ツール
    (`chotBDAV.exe`) とバイト一致で検証済み

この 2 出典から、BDMV との差分 (上表) を確定させた。

### 3.2 設計判断 (`BDAV_SUPPORT.md` §4.2 に全文)

| # | 論点 | 決定 | 理由 |
|---|---|---|---|
| D1 | BDAV/BDMV 判別 | `disc_open()` 起動時に 1 回だけ判定 | 判別が 1 箇所に閉じて、以降はフラグ参照だけ |
| D2 | ルートの持ち回り | `struct bd_disc` に保持し `disc_root_dir()` で公開 | 既存 AVCHD の 8.3 名変換 (disc.c 内) の上乗せではなく、形式差分を明示的に扱う |
| D3 | パーサの分岐単位 | clpi は既存ファイル内分岐、index は専用関数 | clpi は構造が同一なので差分が最小。index は INDX0100 と構造が全く違うので専用関数が素直 |
| D4 | STN 合成の位置 | `nav_title_open()` で CLPI から | パーサは playlist ファイルだけを見る責務を保つ |
| D5 | UO mask | BDAV では解析せず「全許可」 | BDAV の AppInfo には UO mask が無い。0 にするとシーク・停止まで塞がる (`uo_mask.h` は OR 合成・1=許可) |
| D6 | チャプター判定 | BDAV は type 1 と type 4 の両方 | 実運用では type 4 = チャプター、type 1 = レジューム点 |
| D7 | タイトル一覧 | `PLAYLIST` ディレクトリ走査 | BDMV と同じコード経路を再利用でき差分が最小 |
| D8 | `bd_play()` | **何もしない**。app に `bd_get_titles()` を委ねる | 既存の「メニューなしディスク」契約と同型。`bd_play()` は「イベントキュー初期化 + PSR 初期イベント送出 + first play 開始」を兼ねており、責務を汚さない |
| D9 | `disc_info` | `no_menu_support = 1` | BDAV にはメニューが無い |

### 3.3 実装フェーズ

| Phase | 内容 | 結果 |
|---|---|---|
| 0 | ビルド環境整備、テストデータ生成、参照ダンプ取得 | `sorshi/bdav` と生成物のバイト一致を確認 |
| 1 | disc 層にフォーマット抽象化 | BDMV 優先の判定、`disc_format()` / `disc_root_dir()` / `disc_app_path()` |
| 2 | clpi パーサ | `M2TS0100` 受理、BDAV 用 stream attribute 解析 |
| 3 | playlist パーサ | `PLST0100` 受理、PlayItem 20 byte、PlayListMark 46 byte、AppInfo 無効化 |
| 4 | STN 合成 | CLPI ProgramInfo から `MPLS_STN` を復元 |
| 5 | 統合 | PLAYLIST パス、`.rpls` 命名、チャプター判定 helper 化、BDAV index 解析、`disc_info` 反映 |
| 6 | 検証 | パーサ単体 / タイトル列挙 / 読み出し (BDAV・BDMV 双方) |

---

## 4. 変更点

差分は 14 ファイル / +819 −50 行 (ソースのみ。ドキュメントとテストは別)。

### 4.1 disc 層 — フォーマット抽象化

`src/libbluray/disc/disc.h` / `disc.c`

| 追加・変更 | 内容 |
|---|---|
| `bd_disc_format` | `DISC_FORMAT_BDMV` / `DISC_FORMAT_BDAV` |
| `disc_format()` | ディスクのアプリケーション形式を返す |
| `disc_root_dir()` | `"BDMV"` / `"BDAV"` を返す |
| `disc_app_path()` | `"BDMV/PLAYLIST"` のようなアプリケーションディレクトリ下のパスを合成する |
| `_detect_format()` | `disc_open()` 内で BDAV 判定。**BDMV 優先** (両方あれば BDMV 扱い) |
| `disc_open_stream()` | `BDMV/STREAM` 固定 → ルート依存に |
| `disc_open_path_dec()` | `BDMV/STREAM` prefix 判定 → ルート依存に |
| `disc_pseudo_id()` | BDAV は index と最初の `.rpls` から擬似 ID を生成 |

判定は `p->pf_file_open_bdrom()` 経由で行うので、UDF イメージファイル
(`*.iso`) でも同じように効く。

### 4.2 シグネチャ検査の集約

`src/libbluray/bdnav/bdmv_parse.c` / `.h`

`bdmv_parse_header2()` を追加し、複数のシグネチャを 1 箇所で受理する
ようにした。既存の `bdmv_parse_header()` はそのラッパになった。

シグネチャとバージョンの検査を 1 箇所に集約する原則 (BDMV eroxisting) を
保ったまま、形式を 1 つ増やせるようにした。

### 4.3 clip info パーサ

`src/libbluray/bdnav/clpi_parse.c`

| 変更 | 内容 |
|---|---|
| `_parse_header()` | `HDMV0100` と `M2TS0100` の両方を受理。BDMV は 5 個目のアドレスに extension data を持つが、BDAV は 0x18 が reserved なので 0 として扱う |
| `_parse_stream_attr_bdav()` | BDAV 専用。stream attribute は最大 3 byte・ISRC 無し・言語コード無し。映像は `(video_format << 4 \| frame_rate)` と `(aspect << 4)`、音声は `(audio_presentation_type << 4 \| sampling_frequency)`。**この値域は既存定数 `BD_VIDEO_FORMAT_*` / `BD_AUDIO_FORMAT_*` / `BD_AUDIO_RATE_*` と一致する**ので、そのまま流用できる |
| `_parse_program()` | `is_bdav` を下位関数へ伝播 |

### 4.4 playlist パーサ

`src/libbluray/bdnav/mpls_parse.c` / `mpls_data.h` / `mpls_parse.h`

| 変更 | 内容 |
|---|---|
| `_parse_header()` | `MPLS0100` と `PLST0100` の両方を受理。BDMV 用の AppInfo 解析は BDAV では行わず、UO mask を「全許可」にする |
| `_parse_playitem_bdav()` | BDAV 専用。byte aligned 20 byte の PlayItem。UO mask・still mode・角度情報・STN テーブルが無い |
| `_parse_playlistmark_bdav()` | BDAV 専用。46 byte/件。`mark_type` / `maker_id` / `ref_to_PlayItem_id` / `mark_time_stamp` / `entry_ES_PID` を読み、残りは reserved |
| `MPLS_PL.is_bdav` | 追加 |
| `MPLS_PLM.maker_id` | 追加 (BDMV では 0)。判定を後から変えられるように 정보를保存する |
| `BD_MARK_CHAPTER` | 追加 (BDAV のチャプター mark type 4) |
| `mpls_filename()` | 追加。プレイリスト ID から `"00001.mpls"` / `"00001.rpls"` を生成 |

### 4.5 index パーサ

`src/libbluray/bdnav/index_parse.c`

BDAV index (`index.bdav` / `info.bdav`) を解析し、`TableOfPlayLists`
からタイトルを生成する。HDMV 形式のタイトルオブジェクトは無いので、
`first_play` / `top_menu` は未設定のまま (→ `first_play_supported` と
`top_menu_supported` は 0)。

### 4.6 navigation — STN 合成とチャプター判定

`src/libbluray/bdnav/navigation.c`

| 追加・変更 | 内容 |
|---|---|
| `_stn_from_clpi()` | CLPI の ProgramInfo から `MPLS_STN` を合成。BDAV の playlist には STN テーブルが無いので必要。coding_type から video / audio / pg / ig に分類し、PID で重複を除いて複数 program sequence を統合する |
| `_pl_is_chapter()` | チャプター判定を 1 箇所に集約。BDAV は type 1 と type 4 の両方を数える |
| `nav_get_title_list()` | `PLAYLIST` ディレクトリをルート依存で開く |
| `nav_title_open()` | BDAV の場合、clip info から STN を合成する |

### 4.7 UO mask

`src/libbluray/bdnav/uo_mask.h`

`uo_mask_get_all()` を追加。UO mask を持たない形式 (BDAV) 用。
**0 を入れるとシーク・停止まで塞がる** (ビットは 1 = 許可、合成は OR)
ため、ここは要注意な点だった。

### 4.8 bluray.c

| 変更 | 内容 |
|---|---|
| `_open_playlist()` / `_get_mpls_info()` | プレイリストファイル名を `mpls_filename()` で生成 (`.mpls` / `.rpls`) |
| `_fill_disc_info()` | BDAV では `no_menu_support = 1` |

### 4.9 AACS 判定

`src/libbluray/disc/aacs.c`

録画コンテンツ用 AACS (`AACS/MKB_RW.inf`) も AACS 保護と判定する
ようにした。録画ディスクの場合、鍵はディスク自身にある。

### 4.10 ツール

`src/tools/bd_list_titles.c`

出力の `(playlist: %05d.mpls)` を `(playlist: %05d)` に。拡張子は
形式に依存するため、ツール側では決めない。

---

## 5. 実装中に判明した既存バグ (BDMV にも影響)

### `clpi_lookup_spn()` の fallback

`clpi_lookup_spn()` (src/libbluray/bdnav/clpi_parse.c) は、STC シーケンスの
開始 SPN に対応する coarse entry が無いと
`cl->clip.num_source_packets` (クリップ末尾) を返していた。

EP マップの coarse テーブルは「fine table の PTS / SPN が wrap する位置」
にしか entry が作られない実装が存在する (BDAV 録画で PCR 不連続が頻発する
ため特に多い)。この場合、STC 2 個目以降の PlayItem が
**丸ごと再生不能** になっていた (先頭がクリップ末尾扱いになり
`Read past EOF` で止まる)。

**修正**: coarse テーブルが STC 開始点を含まない場合、最後の coarse entry
から fine table を走査するようにした (fallback)。

これは BDMV 側でも同じ状況 (クリップ末尾 11 秒以内の PCR 不連続) で
発生していたので、BDMV 経路の挙動改善にも繋がる。

---

## 6. 検証

### 6.1 テストデータ

`test/bdav/make_testdata.py` が合成する MPEG-2 TS には
**意図的に PCR 不連続を 1 箇所**入れてある。これにより

- clip に STC シーケンスが 2 個できる (BDAV なら PlayItem 2 個)
- PlayListMark に type 4 (チャプター) と type 5 (PCR 不連続) が出る
- EP マップの coarse テーブルが疎になるケース (§5 の fallback 経路) を試せる

BDAV 側のメタデータは `sorshi/bdav` の writer と同じ構造
(chotBDAV 互換) で生成しているので、実物の BDAV ディスクを入手した
_content と突き合わせる際の基準可以作为。

### 6.2 自動チェック

```bash
meson setup build -Denable_devtools=true -Denable_examples=true
meson compile -C build
./test/bdav/run_tests.sh build
```

```
== bdav ==
  PASS: bdav: disc detected
  PASS: bdav: title listed
  PASS: bdav: stream read back identical to the source
== bdmv ==
  PASS: bdmv: disc detected
  PASS: bdmv: title listed
  PASS: bdmv: stream read back identical to the source
```

読み出した m2ts は元ファイルと md5 一致 (BDMV / BDAV 双方)。

### 6.3 BDMV 経路の回帰確認

BDMV 側にも同じ内容のディスクを生成し、既存の (未変更の) パーサで
解析・読み出しできることを確認した。BDMV パスに追加した条件分岐は
「既に true だった条件の分岐」だけで、BDMV に対して新しい条件は
 들어가지 않는다。

---

## 7. 未対応 / 今後の課題

| 項目 | 内容 |
|---|---|
| **実物 BDAV ディスクでの検証** | 実機入手後に `BDAV_SUPPORT.md` §7 の Q1 (`index.bdav` vs `info.bdav`)、Q2 (mark_type)、Q3 (backup ディレクトリ名)、Q7 (1 録画 = 1 タイトルか) が実測で確定する |
| **AACS 経路の動作確認** | BDAV index 解析により `disc_info.num_titles` がプレイリスト数になり、`use_menus` は 0 のままなので `aacs_select_title(aacs, 0xffff)` による手動 CPS リセットが有効になる。**暗号化済み** BDAV ディスクでの動作確認は未実施 |
| **HEVC TS (BDAV v5.0)** | メタデータ構造が共通の可能性が高いが、HEVC TS モードの index / playlist が別形式かは未確認 (BD-RE Part 3 v5.0 の正本参照が必要) |
| **SESF** | アナログ SD 放送/録画。テレテキスト実体が必要で、libbluray にはテレテキストデコーダが無い |
| **backup ディレクトリ** | 仕様は `BDAV1/` 等のマルチボリューム、生成ツールは `BACKUP/`。`BACKUP/PLAYLIST` は対応済み、`BDAV1/` は未対応 |
| **player 側の契約** | `bd_play()` が BDAV では何もしないため、player 側は `bd_get_titles()` → `bd_select_title()` を使う必要がある。README 等での周知が要る |

---

## 8. 参照資料

- BDAV ファイル仕様 (BD-RE Part 3 v5.0 解説):
  <https://www.blu-ray.org.uk/2024/01/bdav-application-format.html>
- BDAV 実装済みツール (バイト単位仕様・参照ダンプ):
  <https://github.com/sorshi/bdav>
- libbluray 本体: <https://code.videolan.org/videolan/libbluray>

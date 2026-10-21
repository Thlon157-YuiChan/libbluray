# libbluray の BDAV 対応 設計メモ

libbluray は BDMV (BD-ROM) と AVCHD (8.3 ファイル名) のみを扱う。
BDAV (BD-RE Part 3 "Audio Visual Application Format") は未対応であり、
`BDMV` というディレクトリ名と `index.bdmv` / `*.mpls` というファイル体系に
強く依存している。本ドキュメントは BDAV 対応に必要な差分と実装方針をまとめたもの。

> **実装済みの範囲と成果のまとめは [`BDAV_IMPLEMENTATION.md`](BDAV_IMPLEMENTATION.md) を参照。**

本メモの記述は次の 2 出典に基づく。

- 実装済みのコード（libbluray 本体）
- BDAV の実ファイル仕様
  - <https://github.com/sorshi/bdav> (`docs/bdav-native-format.md`, `tools/bdav_dump.py`)
    — 実ファイル生成ツール。`chotBDAV.exe` とのバイト一致で検証済み。
  - <https://www.blu-ray.org.uk/2024/01/bdav-application-format.html>
    — BD-RE Part 3 v5.0 ホワイトペーパー (BD-RE_Part3_V5.0_WhitePaper_180124.pdf) 解説。

---

## 1. BDAV のファイル体系

### 1.1 ディレクトリ構成

BDMV と違い、ルートディレクトリ名が `BDAV` であることと、
index ファイル名・playlist の拡張子とシグネチャ・MovieObject の有無・backup 先の命名だけが異なる。
サブディレクトリ名 (PLAYLIST / CLIPINF / STREAM) は BDMV と同じ。

```
BDAV/
  index.bdav        インデックス (シグネチャ "BDAV0100")
  info.bdav         実装済み生成ツールが使う同等の別名 (シグネチャ "BDAV0100")
  menu.tidx         メニュー用サムネイル索引 (BDAV 固有)
  menu.tdt1 ...
  mark.tidx / mark.tdt1 ...
  PLAYLIST/
    00000.rpls      ムービー・プレイリスト (シグネチャ "PLST0100")
  CLIPINF/
    00000.clpi      クリップ情報 (シグネチャ "M2TS0100")
  STREAM/
    00000.m2ts      AV ストリーム
    00000.dvsd
  AACS/             DRM (BDMV とは別ディレクトリ)
  BDAV1/ BDAV2/ ... 管理情報のバックアップ (実ツールは "BACKUP/" も使う)
```

BDMV との対応表:

| 項目 | BDMV | BDAV |
|---|---|---|
| ルート | `BDMV/` | `BDAV/` |
| index | `index.bdmv` (INDX0100) | `index.bdav` / `info.bdav` (BDAV0100) |
| playlist | `PLAYLIST/*.mpls` (MPLS0100) | `PLAYLIST/*.rpls` (PLST0100) |
| clip info | `CLIPINF/*.clpi` (HDMV0100) | `CLIPINF/*.clpi` (M2TS0100) |
| stream | `STREAM/*.m2ts` | `STREAM/*.m2ts` |
| MovieObject | `MovieObject.bdmv` (MOBJ0100) | **なし** (メニュー機構が存在しない) |
| backup | `BACKUP/` | `BDAV1/`, `BDAV2/`, `BACKUP/` |
| メニュー | HDMV VM による対話的メニュー | なし (線形 AV) |
| BD-J | あり | なし |

### 1.2 `index.bdav` / `info.bdav` (BDAV0100)

```
0x00  "BDAV0100"
0x08  u32  TableOfPlayLists_start_address
0x0C  u32  MakersPrivateData_start_address (0 = なし)
0x10  reserved (0x18 まで)
0x28  u32  UIAppInfoBDAV.length
0x2C  UIAppInfoBDAV
        +0x00  u32  予約 (概ね 00 00 01 00)
        +0x04  char[4] 文字セット (例 "0000")
        +0x08  char[10] 名称
        +0x12  u16 予約
      (0x28+4+length から TableOfPlayLists までは 0 パディング)
tbl   u32  TableOfPlayLists.length
tbl+4 u16  num_of_PlayLists
tbl+6 char[10] * num_of_PlayLists   プレイリスト名 ("00000.rpls")
```

BDMV の `index.bdmv` (INDX0100) とは構造が全く異なる。first_play / top_menu オブジェクトも
タイトル一覧 (HDMV/BD-J オブジェクト) も存在しない。

### 1.3 `PLAYLIST/*.rpls` (PLST0100)

```
0x00  "PLST0100"
0x08  u32  PlayList_start_address
0x0C  u32  PlayListMark_start_address
0x10  u32  MakersPrivateData_start_address
0x14  reserved (0x28 まで)
0x28  AppInfoPlayList (u32 length)
        +0x08  u8   タイムゾーン
        +0x0A  BCD 録画日時 (年2B, 月, 日, 時, 分, 秒)
        +0x11  BCD 長さ (時, 分, 秒)
        +0x14  u16  maker_ID
        +0x16  u16  maker_model_code
        +0x18  u16  チャンネル番号
        +0x1B  u8 + 20byte  チャンネル名 (ARIB 8単位符号)
        +0x30  u8 + 255byte 番組名 (ARIB 8単位符号)
        +0x130 u16 + 本文 番組詳細
```

PlayList (BDMV と **ほぼ同一**):

```
u32  length
u16  type
u16  num_of_PlayItems
u16  num_of_SubPlayItems
PlayItem[num_of_PlayItems]
```

PlayItem は **BDMV と完全不同** (バイト境界・20 バイト):

```
+0x00  char[5] clip_id        (例 "00000")
+0x05  char[4] codec_id       ("M2TS")
+0x09  u8     reserved        (0)
+0x0A  u8     connection_condition
+0x0B  u8     ref_to_STC_id
+0x0C  u32    IN_time
+0x10  u32    OUT_time
```

BDMV 側の PlayItem (src/libbluray/bdnav/mpls_parse.c:440) は
`reserved(11bit) | is_multi_angle(1bit) | connection_condition(4bit)` が 2 バイトに
BitPack され、さらに UO mask (8B) / still_mode / still_time / 角度情報 / **STN テーブル**
が続いた 32 バイト以上もの。BDAV には **STN テーブルも UO mask も無い**。

PlayListMark も **1 件 46 バイト** (BDMV は 14 バイト) で項目順も異なる:

```
+0x00  u8   mark_type        (1=エントリ, 4=チャプター, 5=PCR不連続)
+0x01  u8   reserved
+0x02  u16  maker_ID         (Sony = 0x0108)
+0x04  u16  ref_to_PlayItem_id
+0x06  u32  mark_time_stamp
+0x0A  u16  entry_ES_PID
+0x0C  u16  reserved
+0x0E  u8[32] reserved
```

実運用の mark_type 内訳 (実ファイル生成ツールの観測 + chotBDAV 互換出力):

| mark_type | maker | 意味 |
|---|---|---|
| 4 | Sony 0x0108 | **チャプター** (300 秒間隔、番組先頭も type 4) |
| 1 | Sony 0x0108 | レジューム点 (IN + 10 秒) |
| 5 | 0x0000 | PCR 不連続点 (後続 PlayItem の先頭) |

> **要注意**: libbluray はチャプターを `mark_type == BD_MARK_ENTRY (0x01)` だけで数える
> (`_pl_chapter_count()` src/libbluray/bdnav/navigation.c:62、
> `_extrapolate_title()` src/libbluray/bdnav/navigation.c:602)。
> BDAV ではチャプターが **type 4** なので、そのままでは **チャプターが 0 個**になる。
> BDAV モードでは type 4 もチャプターとして数える規則が必要。
> (BDMV との mark_type 意味の対応は規格で要確認)

### 1.4 `CLIPINF/*.clpi` (M2TS0100)

**BDMV の clpi (HDMV0100) と構造は同一**。差異はシグネチャと、拡張データ開始アドレス
(0x18) が無い点だけ。

```
0x00  "M2TS0100"
0x08  u32  SequenceInfo_start_address
0x0C  u32  ProgramInfo_start_address
0x10  u32  CPI_start_address
0x14  u32  ClipMark_start_address
0x18  reserved (0x28 まで)      <- BDMV では ext_data_start_address
0x28  ClipInfo (length = 0xB0)
        clip_stream_type(1) / application_type(0) / is_ATC_delta
        TS_recording_rate (0x386666) / num_of_source_packets
        reserved 128 バイト
        TS_type_info (length = 0x1E): validity, format_id(4), network_id, ts_id, ...
0x28+0xB0+4  SequenceInfo  (ATC x N, STC x M)
              ProgramInfo  (program sequence x N, stream ごとに PID と StreamCodingInfo)
              CPI          (CPI_type=1, EP_map: coarse/fine)
              ClipMark     (length = 0)
```

差異は StreamCodingInfo の中だけで、BDMV は `coding_type + format/rate/aspect + lang(3) +
ISRC(12)`、BDAV は `coding_type + 1〜2 バイト` (言語コードも ISRC も無い)。
BDAV の stream attribute 長 (sci_length) は映像/音声で 3、それ以外で 1。

---

## 2. libbluray 側の BDMV 固定依存箇所

| ファイル:行 | 内容 | BDAV での扱い |
|---|---|---|
| `src/libbluray/disc/disc.c:428` | AVCHD 8.3 名検出 (`BDMV/index.bdmv` → `INDEX.BDM`) | BDAV とは無関係。AVCHD 検出は BDMV 前提のまま |
| `src/libbluray/disc/disc.c:695` | `disc_open_stream()` が `BDMV/STREAM` を固定 | ルート依存に |
| `src/libbluray/disc/disc.c:710` | `disc_open_path_dec()` が `BDMV/STREAM` prefix を判定 | ルート依存に |
| `src/libbluray/disc/disc.c:842-843` | 擬似 disc ID のハッシュ対象 (`BDMV/MovieObject.bdmv`, `BDMV/index.bdmv`) | BDAV 用に追加 or 代替 |
| `src/libbluray/bdnav/index_parse.c:313,317` | `indx_get()` が `BDMV/index.bdmv` | BDAV index 解析を追加 |
| `src/libbluray/bdnav/mpls_parse.c:1175,1181` | `mpls_get()` が `BDMV/PLAYLIST`, `BDMV/BACKUP/PLAYLIST` | ルート・拡張子依存に |
| `src/libbluray/bdnav/clpi_parse.c:876,879` | `clpi_get()` が `BDMV/CLIPINF`, `BDMV/BACKUP/CLIPINF` | ルート依存に |
| `src/libbluray/bdnav/navigation.c:405` | `nav_get_title_list()` が `BDMV/PLAYLIST` を走査 | ルート依存に |
| `src/libbluray/bluray.c:2512` | `_open_playlist()` が `"%05u.mpls"` | BDAV は `"%05u.rpls"` |
| `src/libbluray/bluray.c:2969` | `_get_mpls_info()` が `"%05u.mpls"` | 同上 |
| `src/libbluray/bluray.c:1056` | `_fill_disc_info()` が `indx_get()` | BDAV index  대응 필요 |
| `src/libbluray/hdmv/mobj_parse.c:227,233` | `MovieObject.bdmv` | BDAV には無い → 開かないだけでよい |
| `src/libbluray/bdnav/meta_parse.c:159,185` | `BDMV/META/DL`, `BDMV/META/TN` | BDAV には無い → 開かないだけでよい |
| `src/libbluray/bdnav/sound_parse.c:228` | `BDMV/AUXDATA/sound.bdmv` | 同上 |
| `src/libbluray/bdj/bdjo_parse.c:576,582` | `BDMV/BDJO` | 同上 |
| `src/libbluray/bluray.c:2314,4295` | `BDMV/AUXDATA/*.ttf`, `BDMV/META/DL` | 同上 |

シグネチャ検査は `bdmv_parse_header()` (src/libbluray/bdnav/bdmv_parse.c:34) に集約され、
バージョンは `0100/0200/0240/0300` のみ許可 (src/libbluray/bdnav/bdmv_parse.h:28)。
BDAV の 3 ファイルはいずれも version が `0100` なので **バージョン検査はそのまま通る**。
差し替えが必要なのはシグネチャ判定部分だけ。

---

## 3. 実装上の要点 (落とし穴)

### 3.1 `.rpls` に STN テーブルが無い → ストリーム情報は CLPI から作る

`MPLS_PI.stn` は BDMV では playlist 内に格納された StreamCodingInfo テーブルだが、
BDAV の `.rpls` には存在しない。libbluray は以下で `stn` を参照しているため、
BDAV では **CLPI の ProgramInfo から `MPLS_STN` を合成** する必要がある。

- `src/libbluray/bluray.c:364` `_update_stream_psr_by_lang()` — 音声/PG/IG ストリームの言語選択
- `src/libbluray/bluray.c:419` `_update_playlist_psrs()`
- `src/libbluray/bluray.c:471` `_find_pg_stream()`
- `src/libbluray/bluray.c:683` `_open_m2ts()` — `m2ts_filter_init()` に video/audio/ig/pg 数
- `src/libbluray/bluray.c:2927-2934` `_fill_title_info()` — タイトル情報のストリーム列挙
- `src/libbluray/bdnav/navigation.c:85-90,135-150,297-315` — タイトル重複判定・主タイトル推定

合成の材料は `CLPI_PROG_INFO` (src/libbluray/bdnav/clpi_data.h:105) の
`CLPI_PROG_STREAM` (coding_type / format / rate / aspect / lang)。
coding_type → video/audio/pg/ig の分類規則は BDMV の `_parse_stream()`
(src/libbluray/bdnav/mpls_parse.c:116) と同じ判定表を使う。

注意点: BDAV の clpi には言語コード (lang) が無い。`bd_get_title_info()` が返す
言語は空になる (BDAV 再生では不要だが、CLPI 側にも情報源が無い以上 無理)。

### 3.2 UO mask を 0 にすると seek / stop が塞がる

`BD_UO_MASK` は **1 = 許可** のビットマスクで、`uo_mask_combine()` は OR 合成
(src/libbluray/bdnav/uo_mask.h:29)。**BDMV の playlist から UO mask を読む**。BDAV には UO mask が無いので、
**素直すると UO mask = 0 になり「シーク不可・停止不可」になる**。
`src/libbluray/bluray.c:685` で

```c
st->uo_mask = uo_mask_combine(pl->app_info.uo_mask, pl->play_item[...].uo_mask);
```

と合成する。BDAV の `.rpls` には UO mask が存在しないため、
**素直すると UO mask = 0 になり「シーク不可・停止不可」になる**。
BDAV 用には「全許可」のマスクを設定する必要がある。

さらに BDAV の AppInfoPlayList は BDMV の AppInfoPlayList とは別構造
(録画日時 / チャンネル名 / 番組名) なので、BDMV として解析すると
UO mask に無関係な値が混入する。**BDAV の playlist は appinfo を BDMV として
解釈してはいけない**。

### 3.3 `AppInfoPlayList` を BDMV として解釈すると壊れる

`mpls_parse.c:53` の `_parse_appinfo()` は `length` → `playback_type` → `uo_mask` と
BDMV 前提で読む。BDAV の AppInfoPlayList は先頭が `00 00 01 00` で、その後に
タイムゾーン / 録画日時 が続く。BDMV として読むと `uo_mask` に
録画日時の BCD バイトが混入する。分岐が必須。

### 3.4 `MovieObject` が無い → HDMV VM / メニューは使えない

`_fill_disc_info()` (src/libbluray/bluray.c:1015) は `indx_get()` が NULL の場合、
`nav_get_title_list()` が title を拾えるときだけ
"Possible incomplete BluRay image detected. No menu support." として
`no_menu_support = 1` を立てる (src/libbluray/bluray.c:1057-1066)。
この経路は BDAV にもそのまま当てはまるので、**menu なし作为一个 BDAV として扱える**。

再生の入口は `bd_play()` ではなく、

1. `bd_get_titles()` → `nav_get_title_list()` (PLAYLIST ディレクトリ走査)
2. `bd_select_title()` → `_select_title()` (src/libbluray/bluray.c:2647)
   → `_open_playlist(bd, mpls_id, 0)`

となる。`_open_playlist()` が `MPLS_PL` として playlist を開くので、
BDAV ではファイル名を `.rpls` にするだけで良い (HDMV VM を通らない)。

### 3.5 `_parse_playitem()` は BDAV の PlayItem で破綻する

`mpls_parse.c:440` の `_parse_playitem()` は
`clip_id(5) / codec_id(4) / 12bit / stc_id(1) / IN(4) / OUT(4)` まで読んで
**無条件に** UO mask (8B) / still_mode / still_time を読む。
BDAV の PlayItem は 20 バイトしかないので、STN テーブルの位置が狂って
次の PlayItem の内容を STN として解釈してしまう (最後に `bs_seek_byte(pos+len)` で
位置だけ巻き戻るため、値が壊れた状態で「成功」する)。
BDAV 用の PlayItem 解析を分岐で用意する必要がある。

### 3.6 `_parse_playlistmark()` は BDAV で件数を誤る

`mpls_parse.c:693` は `bs_avail/(8*14)` で 14 バイト前提の件数チェックを行い、
14 バイトずつ読む。BDAV は 46 バイト/件なので、そのままでは件数・オフセットが全滅する。

### 3.7 CLPI の stream attribute に ISRC 12 バイト固定

`clpi_parse.c:45` の `_parse_stream_attr()` は最後に
`bs_read_bytes(bits, ss->isrc, 12)` を無条件に実行する。
BDAV の stream attribute は 1〜3 バイトで ISRC を持たないため、
値は隣の stream の属性を拾ってしまう (位置は末尾の seek で戻るので致命的ではないが、
`format` / `rate` / `lang` が壊れる)。BDAV 用の分岐が必要。

### 3.8 BDAV の clpi には拡張データ (SSIF 等) が無い

BDMV の clpi は 0x18 に `ext_data_start_addr` を持つ (2.4/3D 用)。
BDAV には無い。`clpi_parse.c:138-142` は 5 個の u32 を読み、
`ext_data_start_addr` は 3D 再生の実装 (program_ss / cpi_ss) でのみ使われる。
BDAV では 0 として扱えば問題ないが、0x18..0x1C が reserved であることを
前提にすることは明記しておく。

---

## 4. 実装方針 (HDMV TS プレイモードを主軸とする)

### 4.0 スコープの確定

**主軸: BDAV の "HDMV TS" プレイモード** (BD-RE Part 3 v1.0〜v3.x 系)。
MPEG-2 / H.264 AVC 映像 + LPCM / AC-3 / MPEG-2 AAC 音声 + PG 字幕、
M2TS (192 byte TS) コンテナ。

**重要**: HDMV TS モードの **メタデータ構造 (BDAV0100 / PLST0100 / M2TS0100) は
HEVC TS モードと共通** である可能性が高い。「HEVC TS を実装しない」のではなく
「HEVC TS の動作検証ができない」だけ。したがってパーサは
**HEVC 固有の要素 (HEVC TS 固有の index 構造・拡張子・ストリーム型) を取り込まない
generic な形**にしておく。将来 HEVC TS に対応させ直すときに取り返しが無いようにするため。

明示的に対象外:

- HEVC TS (BDAV v5.0) — 実ディスクが無いので検証不能
- SESF (Self-Encoded Stream Format, アナログ SD 放送/録画) — テレテキスト実体が
  (libbluray にテレテキストデコーダが無い: `decoders/` は PG / IG / TextST のみ)、
  SD 時代のメタデータ構造も未確認。実用価値もほぼ無いため当面対象外
- BDAV のメニュー / サムネイル (`menu.tidx`, `mark.tdt*`, `mark.tidx`)
- `BDAV1/`, `BDAV2/` を使うマルチボリューム管理
- `.vpls` (ボリュームプレイリスト)
- BDAV の作成 (書き込み側) — 本プロジェクトでは読み出しのみ

### 4.1 設計の 3 原則

**(a) BDMV のコードパスは不変**
BDMV 対応は「分岐を足す」だけで、既存挙動を一切変えない。
本リポジトリには BDMV / BDAV どちらのテストデータも無いので、
**BDMV 回帰を担保する手段は差分レビューだけ** である。したがって BDMV 側の条件分岐は
「既に true だった条件の分岐」だけで済ませ、BDMV パスに新しい条件を追加しない。

**(b) 判別は早期・1 箇所**
「BDAV か BDMV か」は `disc_open()` の中で 1 回だけ確定し `struct bd_disc` に保持する。
以降のパーサは `disc->is_bdav` (または `disc_root_dir()`) を見るだけにする。
判定のたびにファイルを再オープンしに行かない。

**(c) フォーマット差分はパーサ内に閉じる**
`navigation.c` / `bluray.c` は BDMV / BDAV を意識しない。
唯一、BDAV だけ playlist の拡張子が違う (`.mpls` / `.rpls`) ので、
ファイル名生成だけは disc 層の helper に集約する。

### 4.2 個別の設計判断

| # | 論点 | 選択肢 | 推奨 | 理由 |
|---|---|---|---|---|
| D1 | BDAV/BDMV 判別 | (a) `disc_open()` で index の存在を検査 (b) パース時にシグネチャで判定 | **(a)** | 判定が 1 箇所。シグネチャ判定 (b) は index 構造が全く違うため成立しない |
| D2 | ルートの持ち回り | (a) disc に保持し `disc_root_dir()` で公開 (b) `disc_open_path()` 内で "BDMV"→"BDAV" 置換 (c) 呼び出し側が毎回連結 | **(a)** | (b) は AVCHD の 8.3 名ハック (disc.c:114) の上乗せで、何が起きているか読めなくなる。(c) は全呼び出しに `DIR_SEP` 文字列が増える |
| D3 | パーサの分岐単位 | (a) 既存ファイル内に分岐 (b) BDAV 専用ファイル新設 | **clpi は (a)、index は (b)** | clpi は構造が同一なので差分が最小。index (BDAV0100) は INDX0100 と構造が全く違うので専用関数 (`_indx_parse_bdav`) が素直。playlist は PlayList 共通部があるため (a) が有利 |
| D4 | STN 合成の位置 | (a) `nav_title_open()` で CLPI から (b) `.rpls` パーサ内 (c) 専用モジュール | **(a)** | パーサは playlist ファイルだけ見る責務で保ちたい。CLPI は navigation が既に `clip->cl` として保持している |
| D5 | AppInfoPlayList / UO mask | BDAV では解析せず「全許可」 | **採用** | BDAV の AppInfoPlayList は録画日時/番組名構造で UO mask を持たない。0 だとシークが塞がる (uo_mask.h:29 は OR 合成・1=許可) |
| D6 | チャプター (mark_type) | BDAV では type 1 と type 4 を chapter 扱い、判定は 1 箇所に集約 | **採用** (§4.3) | 実運用では type 4 = チャプター。libbluray は type 1 しか数えない (navigation.c:62) |
| D7 | タイトル一覧のソース | (a) `PLAYLIST` ディレクトリ走査 (b) `info.bdav` の TableOfPlayLists | **(a)** | BDMV と同じコード経路を再利用でき、差分が最小。index は「BDAV 検出」と `disc_info` 反映にのみ使う |
| D8 | `bd_play()` の BDAV 挙動 | (a) 何もしず app に `bd_get_titles()` を委ねる (b) 最初のタイトルを自動選択 | **(a)** (§4.4) | libbluray 側に「BDAV にはメニューがない」契約 (no_menu_support + `bd_get_titles()`) を持ち、既存 player の incomplete disc 経路と同一形状にする。`bd_play()` は「イベントキュー初期化 + PSR 初期イベント + first play 開始」を兼ねているため、暗黙の title 選択を混ぜると責務が汚れる |
| D9 | `disc_info` | `bluray_detected=1` / `no_menu_support=1` | **既存経路を再利用** | `indx_get()` が NULL のとき bluray.c:1057-1066 が既にこの設定をしている。BDAV は MovieObject が無いので自然にこの経路に入る |

### 4.3 Q2 の決定: BDAV の mark_type とチャプター判定

`MPLS_PLM.mark_type` は `BD_MARK_ENTRY (0x01)` **だけ**が章として扱われる
(`mpls_data.h:28`)。判定は 2 箇所ある。

- `navigation.c:62` `_pl_chapter_count()` — `chap_list` の要素数
- `navigation.c:604` `_extrapolate_title()` — `chap_list` への振り分け

一方 `mark_list` は全マークが入る (`navigation.c:621`)。chap_list と mark_list は別系統。

**BDAV 実運用の mark_type 内訳** (生成ツールの観測 + chotBDAV 互換出力):

| mark_type | maker | 意味 |
|---|---|---|
| 4 | Sony 0x0108 | **チャプター** (300 秒間隔、番組先頭も type 4) |
| 1 | Sony 0x0108 | レジューム点 (IN + 10 秒) |
| 5 | 0x0000 | PCR 不連続点 (後続 PlayItem の先頭) |

**決定: BDAV モードでは type 1 と type 4 の両方をチャプターとして数える。**
(実運用では type 1 は 1 本しか無いので「先頭に 1 個余る」程度のノイズ)

**影響範囲** (type 1 のみのままにした場合):

| API / フィールド | 結果 |
|---|---|
| `bd_get_title_info()` → `chapter_count` / `chapters[]` | 0 になる |
| `bd_seek_chapter()` (bluray.c:1832) | 常に失敗 |
| `bd_chapter_pos()` (bluray.c:1869) | 常に失敗 |
| `bd_get_current_chapter()` | 0 のまま |
| PSR chapter number (bluray.c:455-460) | 更新されない |
| `bd_get_title_info()` → `mark_count` / `marks[]` | 影響なし。`marks[].type` で app 側が型を判別できる |
| `bd_seek_mark()` (bluray.c:1931) | 影響なし |
| 再生コア (M2TS 読み出し・TS demux) | 影響なし |

**データモデル**: BDAV の 46 byte mark → `MPLS_PLM` 写像表。

| BDAV フィールド | `MPLS_PLM` | 状況 |
|---|---|---|
| mark_type | `mark_type` | ✓ |
| **maker_ID** | **存在しない** | ✗ **追加する** |
| ref_to_PlayItem_id | `play_item_ref` | ✓ |
| mark_time_stamp | `time` | ✓ |
| entry_ES_PID | `entry_es_pid` | ✓ |
| (duration フィールドなし) | `duration` | 0 でよい。`_extrapolate_title()` は隣接章との差から chapter duration を計算するので、type 4 の 300 秒間隔がそのまま章長になる |

`MPLS_PLM` に `maker_id` を追加して保存する (BDMV 側は 0 を入れるだけなので BDMV 影響ゼロ)。
これが無いと「仕様判明後に判定を変える」余地が失われる。

**実装上の要求**: 判定ロジックは `_pl_chapter_count()` と `_extrapolate_title()` の
2 箇所を 1 つの helper に集約し、**mark_type 別の件数と maker_id をログに出せるようにする**
(`BD_DEBUG(DBG_NAV, ...)`)。実物ディスクに当たった瞬間に type 4 の意味が判明し、
判定条件 1 箇所の差し替えだけで済む。

**結論: 仕様確定を待たずに実装を進められる。**

### 4.4 Q4 の決定: `bd_play()` の BDAV 挙動

現状のコード追跡:

```
bd_play()                                       bluray.c:3643
 └─ _play_title(bd, BLURAY_TITLE_FIRST_PLAY)    bluray.c:3670
      ├─ if (!bd->disc_info.titles) → return 0        bluray.c:3571  ← BDAV で NULL
      └─ if (bd->disc_info.no_menu_support) → return 0 bluray.c:3576  ← BDAV で 1
```

一方 `bd_get_titles()` → `nav_get_title_list()` は BDAV でも列挙でき、
`bd_select_title()` → `_select_title()` (bluray.c:2647) → `_open_playlist()` は
HDMV VM を通らないので BDAV でも動く。

**決定: (a) を採る。`bd_play()` は BDAV では何もしない。
app / player 側には「`bd_get_titles()` → `bd_select_title()`」の契約を委ねる。**

- libbluray 側: 変更ゼロ
- player 側: BDAV で自動的に 1 本目が始まらない。メニュー前提の player は
  タイトル選択 UI を出さないと何も始まらない
- これは既に存在する「メニューなしディスク」契約 (bluray.c:1057-1066 の
  incomplete image 経路) と同型なので、既存 player の実装がそのまま流用できる

代替案 (b) `bd_play()` が main title を自動 select する案は **不採用**。
`bd_get_main_title()` は `bd->title_list` 済み前提 (bluray.c:2804) なので
`bd_play()` 内で `bd_get_titles()` を呼ぶ必要があり、
さらに `bd_play()` の責務 (イベントキュー初期化 + PSR 初期イベント送出 +
first play 開始) に暗黙の title 選択を混ぜることになる。

### 4.5 実装フェーズ

各フェーズは単独でビルド可能・レビュー可能にする。

| Phase | 内容 | 依存 |
|---|---|---|
| 0 | ビルド環境整備、テストデータ生成 (`sorshi/bdav`)、参照ダンプ (`tools/bdav_dump.py`) の手元実行、**実物の BDAV 標本 (index + playlist + clpi) の入手** (§6.5) | - |
| 1 | disc 層: `is_bdav` / `disc_root_dir()` の追加と BDAV 判定。**BDMV 挙動は不変** | 0 |
| 2 | clpi: `M2TS0100` シグネチャ受理 + BDAV 向け stream attribute 解析 (ISRC なし・1〜3 byte) | 1 |
| 3 | playlist: `.rpls` (PLST0100) パーサ。PlayItem 20 byte / PlayListMark 46 byte / AppInfo 無効化 / `MPLS_PLM.maker_id` 保存 | 1 |
| 4 | STN 合成: `nav_title_open()` で CLPI ProgramInfo → `MPLS_STN` | 2, 3 |
| 5 | 統合: `nav_get_title_list()` の PLAYLIST パス、playlist ファイル名生成 (`.rpls`)、チャプター判定 helper 化、no-menu 再生経路、`disc_info` | 3, 4 |
| 6 | 検証 (下記 §6.2) | 5 |

Phase 2 と Phase 3 は独立に書けるので並行可能。
Phase 1 は「構造体へのフラグ追加と root 文字列の公開」だけで、
BDMV パスには条件分岐を足さない。

### 4.5.1 Phase 0 で実物標本を入手する理由

生成物 (`sorshi/bdav`) は chotBDAV とのバイト一致で検証済みなので
**パーサ検証の基準としては十分**。実物標本が必要なのは
「生成物では確定できない項目」を実測で潰すため:

| 項目 | 実物で解決できる内容 |
|---|---|
| Q1 | `index.bdav` と `info.bdav` のどちらが実際に使われるか、backup は `BDAV1/` か `BACKUP/` か |
| Q2 | `.rpls` 内の mark_type 分布 (type 1 / 4 / 5 の実数と maker_id) |
| Q3 | backup ディレクトリ名 |
| Q7 | 1 録画 = 1 `.rpls` か、1 タイトルに複数 `.rpls` が束ねられるか |
| Q5 | HDMV TS ディスクの index/playlist を見ることで、HEVC TS との共通性を否定的に確認 |

入手経路 (優先順):

1. **ビデオカメラの BDAV 出力** (Sony / Canon / Panasonic 等) — SD カードや USB に
   `BDAV/` フォルダが直接書き出される。**BD ドライブ不要**。最も手早い
2. **BD-R / BD-RE 録画機**でテレビを録画したディスク — ドライブ + 録画機が必要
3. **PS3 の BDAV 録画データ** (HDD からコピー)
4. どれが手に入らない場合は `sorshi/bdav` 生成物で進め、実物解析は
   「§4.3 の判定を helper 1 箇所に集約し log で mark_type 分布を出す」ことで
   後から調整できるようにしておく

実物標本は **実機検証** の優先度和高い: 実物の BDAV は AACS 暗号化されておらず
(UDF 2.5/2.6)、そのまま `dec == NULL` の経路で読める。

### 4.6 未対応プレイモードの検出 (防御)

HEVC TS / SESF の実物ディスクが将来扱えるようになったとき、
「パーサが壊れた」のか「仕様外」なのかを切り分けられるように、
stream / clip の coding_type が HDMV TS の想定外だった場合は
黙って壊れた再生をせず `BD_DEBUG(DBG_NAV | DBG_CRIT, ...)` で
「未対応の BDAV プレイモード」とログ出して title を skip する。
assert は置かない (libbluray の既存スタイルに合わせる)。

---

## 5. 実装プラン (ファイル別)

### A. ルートディレクトリ抽象化 (disc 層)

`src/libbluray/disc/disc.c` / `.h`:

- `struct bd_disc` に root ディレクトリ名を持たせる (`"BDMV"` / `"BDAV"`)。
- `disc_open()` の中で `BDAV/index.bdav` または `BDAV/info.bdav` が存在すれば
  `"BDAV"`、無ければ `"BDMV"` と判定する。判定は
  `p->pf_file_open_bdrom()` 経由で行うので、UDF イメージ (\*.iso) にも対応する。
- `const char *disc_root_dir(BD_DISC *p)` を追加し、parser 側からは
  相対パスの先頭にこれを付けて `disc_open_path()` / `disc_open_dir()` を呼ぶ。

`disc_open_path()` は 相対パス ("BDMV/PLAYLIST/00000.mpls" 形式) を受ける設計なので、
**呼び出し側が root ディレクトリ名を意識するようにする** (parser 側で `disc_root_dir(disc)` を使う)。
AVCHD の 8.3 名変換 (src/libbluray/disc/disc.c:114) のように disc 層で
"BDMV" → "BDAV" へ置換する案もあるが、拡張子 (.mpls/.rpls) も変わるため、
パス生成は parser 側で行う方が素直。

### B. BDAV index の解析

`src/libbluray/bdnav/index_parse.c` に BDAV 用の解析を追加する。

- 既存 `INDX_ROOT` は BDMV 前提 (first_play / top_menu / titles) なので、
  BDAV 用にプレイリスト名一覧を持つ別構造体を用意するのが素直。
  例えば `INDX_ROOT` に `uint16_t playlist_count; char (*playlist_name)[11];` を足す形でもよい。
- `indx_get()` の探索順:
  - BDMV: `BDMV/index.bdmv` → `BDMV/BACKUP/index.bdmv`
  - BDAV: `BDAV/index.bdav` → `BDAV/info.bdav` → `BDAV1/index.bdav` → `BDAV1/info.bdav`
    → `BDAV/BACKUP/...`
- `UIAppInfoBDAV` は BDAV 固有情報 (名称等) で、既存 `INDX_APP_INFO` とは別物。
  取り敢えず読み飛ばして良い。

### C. `.rpls` (playlist) パーサ

`src/libbluray/bdnav/mpls_parse.c` を拡張し、シグネチャで分岐する
(既存ファイル内の `MPLS_SIG1` 定義のそばに `RPLS_SIG1` を追加)。

- `_parse_header()`: `'PLST'` なら BDAV モード。`MPLS_PL` に
  「BDAV かどうか」を表すフラグを持たせる。
- `_parse_appinfo()`: BDAV なら **BDMV として解釈しない**。
  UO mask は「全許可」、random_access_flag = 1 にする。
- `_parse_playitem()`: BDAV なら 20 バイトのバイト境界レイアウトで読む。
  UO mask = 全許可、still_mode = 0、角度数 = 1、STN は空。
- `_parse_playlistmark()`: BDAV なら 46 バイト/件。
  `MPLS_PLM` の `duration` は BDAV には無いので 0。
  maker_ID は `MPLS_PLM` に無い項目 → 必要なら構造体を拡張。
- `mpls_get()`: ファイル名を `.rpls` / `.mpls` のどちらでも開くようにする
  (BDAV は TableOfPlayLists の名前、BDMV は `.mpls`)。

### D. `.clpi` パーサ

`src/libbluray/bdnav/clpi_parse.c`:

- `_parse_header()`: `'M2TS'` シグネチャも受理。
- `_parse_stream_attr()`: BDAV モード (ISRC なし・最大 3 バイト) を用意。
- `clpi_get()`: `CLIPINF` の親ディレクトリをルート依存にする。

### E. navigation

- `nav_get_title_list()` (src/libbluray/bdnav/navigation.c:393):
  `PLAYLIST` ディレクトリをルート依存で開く。
  BDAV では TableOfPlayLists が authoritative だが、ディレクトリ走査でも
  同じリストが得られる。どちらを採るかは要検討 (走査なら BDAV index パース不要)。
- `nav_title_open()`: `_fill_clip()` の後、`pi->stn` が空 (= BDAV) なら
  読み込んだ CLPI の `program.progs[]` から `MPLS_STN` を合成する。
  複数 program sequence がある場合は最初のものを使うか、
  stream PID を引き継いで合成する。
- `_fill_clip()`: `clip->cl` は CLPI。`nav_clip_lookup_aspect()` は既に
  CLPI 由来なので変更不要。

### F. bluray.c

- `_open_playlist()` (src/libbluray/bluray.c:2504) と
  `_get_mpls_info()` (src/libbluray/bluray.c:2958):
  ファイル名生成を `"%05u.mpls"` → BDAV なら `"%05u.rpls"` に。
  拡張子を共有するヘルパーを用意するのが良い
  (例: `disc_playlist_name(disc, id, buf, size)`)。
- `_fill_disc_info()`: BDAV の場合 `disc_info.titles` は
  TableOfPlayLists から作るか、`no_menu_support = 1` として
  `bd_get_titles()` に任せる。前者は `bd_get_disc_info()` の情報量が増えるので
  preferred。
- `bd_play()` / `_play_title()`: BDAV では first play が無いので
  呼ばれても再生は始まらない。アプリ側は `bd_get_titles()` + `bd_select_title()` を使う。
  BDAV でも `bd_play()` → first play → 最初のプレイリスト、という fallback を
  入れるなら `_play_title()` に BDAV 分岐を追加する (要設計判断)。

### G. 補助

- `disc_pseudo_id()` (src/libbluray/disc/disc.c:836): BDMV の
  `MovieObject.bdmv` / `index.bdmv` をハッシュしているが、BDAV には
  MovieObject が無い。`index.bdav` / `info.bdav` を使うよう分岐が必要。
  (AACS 無効時のキャッシュキー生成に使われる)
- `bd_list_titles` (src/tools/bd_list_titles.c:133) の出力は
  `(playlist: %05d.mpls)` 固定 → BDAV では `.rpls` と出すべき。
- `bd_info` (src/tools/bd_info.c) は BDAV でも動作するはず
  (`bluray_detected` は `no_menu_support` 経路で 1 になる)。

---

## 6. テスト手順

### 6.1 テストデータ生成

BDAV ツリーは <https://github.com/sorshi/bdav> で生成できる
(依存は Python 標準ライブラリのみ)。CLI の正確な引数は同リポジトリの
`src/bdav/cli.py` を確認のこと (本ドキュメントでは未検証)。

```
git clone https://github.com/sorshi/bdav
cd bdav
# 入力は 192 byte 単位に整列した M2TS (.ts / .m2t も可)
# → out/BDAV/{info.bdav,PLAYLIST/*.rpls,CLIPINF/*.clpi,STREAM/*.m2ts}
```

生成物:
```
out/BDAV/info.bdav
out/BDAV/PLAYLIST/00000.rpls
out/BDAV/CLIPINF/00000.clpi
out/BDAV/STREAM/00000.m2ts
out/BDAV/BACKUP/...
```

参照ダンプ: 同リポジトリの `tools/bdav_dump.py` が BDAV の各ファイルを
フィールド付きで出力する。libbluray 側のパーサ出力と突き合わせの基準にする。

### 6.2 検証計画

| # | 対象 | 手段 | 合格条件 |
|---|---|---|---|
| V1 | パーサ単体 | `clpi_dump` / `mpls_dump` に BDAV ファイルを食わせて `tools/bdav_dump.py` の出力と突き合わせる | 全フィールド一致 |
| V2 | タイトル列挙 | `bd_list_titles out/BDAV` | タイトル数・長さ・チャプター数が期待値 |
| V3 | 読み出し | `libbluray_test out/BDAV 0` → `streamdump.m2ts` | 元 m2ts と packet 数・内容一致 / `ffprobe` でデコード可 |
| V4 | ストリーム選択 | `bd_get_title_info()` の映像/音声/字幕数と PID | CLPI ProgramInfo と一致 |
| V5 | BDMV 回帰 | データが無いので**差分レビュー** | BDMV 分岐に新条件が無いこと (原則 (a)) |

V1 がパーサの正しさを担保し、V3 が実データでの疎通を担保する。
V5 はテストデータ不在の代わりにコードレビューで代替する。

### 6.3 確認手順

```
meson setup build && meson compile -C build
./build/src/tools/bd_info      out/BDAV
./build/src/tools/bd_list_titles out/BDAV
./build/src/examples/libbluray_test out/BDAV 0    # 選択 → streamdump.m2ts を出力
```

確認項目:
- `bd_info` が "BluRay detected: yes" を出す
- `bd_list_titles` がタイトル 1 件と正しい duration / chapters を出す
- `libbluray_test` が `streamdump.m2ts` を書き出す
- 書き出した m2ts を `ffprobe` 等でデコードできること

### 6.4 回帰確認

BDMV _TITLE が従来どおり動くこと (AVCHD 8.3 名を含む)。
本リポジトリに test 機構は無い (meson に `test()` 定義なし) ため、
`bd_info` / `bd_list_titles` による手動確認 + 差分レビューが現状の手段。

### 6.5 実ディスクを使った検証手順

BD ドライブを装着した環境 (Linux 前提) での手順。

#### 6.5.1 読み込み経路の注意

`disc_open()` (src/libbluray/disc/disc.c:308) の分岐:

| 渡すもの | 挙動 |
|---|---|
| マウント済みディレクトリ | 通常の stdio アクセス。`disc_root` = そのディレクトリ |
| UDF ISO イメージファイル | `bdpriv_udf_image_open()` → `udfread_open()` (src/libbluray/disc/udf_fs.c:283) |
| 生ブロックデバイス `/dev/sr0` | 動かない。`udfread_open()` は ISO 前提 (UDF アンカーを ISO 位置から探す) だが、BD の生ディスクはアンカーが sector 32 にある |

したがって **OS で UDF をマウントしてマウントポイントを渡す** (VLC on Linux と同じ方式)。

```bash
lsblk /dev/sr0
sudo mount -t udf -o ro /dev/sr0 /mnt/bd
ls /mnt/bd
```

#### 6.5.2 BDAV ディスクの構成確認 (未確定事項の潰し込み)

```bash
ls /mnt/bd/BDAV/                    # index.bdav / info.bdav の実名 (Q1)
ls /mnt/bd/BDAV/PLAYLIST/           # 拡張子 (.rpls) と本数 (Q1, Q7)
ls /mnt/bd/                         # backup ディレクトリ名 (Q3)

# シグネチャ確認 (index.bdav / info.bdav の実名に合わせて)
head -c 8 /mnt/bd/BDAV/index.bdav | xxd    # => "BDAV0100"
head -c 8 /mnt/bd/BDAV/PLAYLIST/00000.rpls | xxd   # => "PLST0100"
head -c 8 /mnt/bd/BDAV/CLIPINF/00000.clpi | xxd    # => "M2TS0100"

# mark_type / maker_id の分布 (Q2)
# PlayListMark はファイル末尾にあるので tail を見る
xxd /mnt/bd/BDAV/PLAYLIST/00000.rpls | tail -40
# できれば sorshi/bdav の tools/bdav_dump.py を使う (フィールド付き)
python3 tools/bdav_dump.py /mnt/bd/BDAV/PLAYLIST/00000.rpls
```

#### 6.5.3 AACS の要否

| 対象 | libaacs / libbdplus |
|---|---|
| BDAV 録画ディスク | **不要**。AACS 対象外なので `dec == NULL` の経路で動作する |
| 市販 BD-ROM (BDMV) のメタデータ | 不要。`index.bdmv` / `MovieObject.bdmv` / `PLAYLIST` / `CLIPINF` は平文 |
| 市販 BD-ROM の `STREAM/*.m2ts` | **必要**。`LIBAACS_PATH` で指定 (src/libbluray/disc/aacs.c:94) |

BDAV 録画ディスクは AACS が無いため、**BDAV 固有のコードだけ**を
切り離して検証できる。検証には最良のケース。

AACS 暗号化の有無は次のように判定する (実ディスクで確認):

```bash
ls /mnt/bd/AACS/                # Unit_Key_RO.inf / MKB_RW.inf / AACS_av/ の有無
# m2ts の TS ヘッダの transport_scrambling_control (offset 3 の下 2 bit) が
# 0 以外なら暗号化されている
xxd -l 32 /mnt/bd/BDAV/STREAM/00000.m2ts
```

#### 6.5.4 実装前の BDAV ディスクの挙動 (注意)

BDAV 対応が入る前の libbluray は BDAV ディスクを **開けない**:
`nav_get_title_list()` が `BDMV/PLAYLIST` を hardcode しているため
(src/libbluray/bdnav/navigation.c:405)、BDAV ディスクでは title を拾えず
`bluray_detected` が 0 のまま → `bd_open()` が NULL を返す。
実ディスクの中身は `ls` / `xxd` / `clpi_dump` で確認する
(`mpls_dump` は `PLAYLIST_DIR` を `BDMV/PLAYLIST` に固定している (src/devtools/mpls_dump.c:39)
ので BDAV には使えない。`clpi_dump` は単ファイル指定なので `.clpi` なら使える)。

#### 6.5.5 BDMV 回帰への転用

市販 BD-ROM 1 枚で BDMV の回帰ケースが手に入る。
本リポジトリには BDMV のテストデータが無い (meson に `test()` 定義なし) ため、
現状 §6.2 の V5 (差分レビュー) しか無かったものを **実テストに置き換えられる**。
変更前後で `bd_info` / `bd_list_titles` の出力を diff する。

### 6.6 録画ディスクの「視聴」目標の実現可能性

最終目標が「録画した BDAV ディスクを視聴できる」なら、
BDAV 対応 (メタデータ) / AACS 復号 / 映像デコードの 3 層に分けて考える。

#### 6.6.1 3 層の分解

| 層 | 担当 | 現状 |
|---|---|---|
| (1) BDAV メタデータ (index / playlist / clpi) の解釈 | libbluray | **未実装**。§4-§5 がこれ |
| (2) m2ts の復号・取出 | libbluray (AACS) | **実装済み・BDAV 非依存**。下記 6.6.2 |
| (3) 映像/音声のデコードと表示 | **player (VLC 等)** | libbluray の外。libbluray には MPEG-2 / AVC のデコーダは無い (`decoders/` は m2ts demux と PG / IG / TextST のみ) |

libbluray が担うのは (1) と (2) まで。(3) は player 側の仕事であり、
「VLC 経由で録画 BDAV ディスクを再生できる」が達成条件。

#### 6.6.2 AACS 復号は BDAV 対応と独立 (追加作業ゼロ)

AACS 経路はフォーマット非依存に実装済み:

- `disc_open()` → `bdpriv_dec_init()` → `_dec_detect()` (src/libbluray/disc/dec.c:252)
  が `bdpriv_aacs_required()` で `AACS/Unit_Key_RO.inf` の有無を判定
  (src/libbluray/disc/aacs.c:78)。無ければ `dec == NULL` になり
  **ストリームはそのまま (暗号化されていなければ) 読まれる**
- 有れば `_libaacs_init()` (dec.c:176) が libaacs に
  `dev->device` と **libbluray 側の VFS コールバック** (`disc_open_path`) を渡す。
  libaacs はこれ経由でディスク上の `AACS/` を読む
- `disc_open_stream()` → `bdpriv_dec_open_stream()` (dec.c:110) が m2ts を
  復号ラッパで包み、read のたびに `bdpriv_aacs_decrypt_unit()` を通す
- libaacs / libbdplus は dlopen (`aacs.c:91`)。`LIBAACS_PATH` で場所を指定できる

**BDAV でも `disc_open_stream()` が `BDAV/STREAM/xxxxx.m2ts` を開くだけで、
復号は同一経路を通る。** BDAV 対応で AACS に追加で何かを書く必要はない。

ただし 2 点の注意:

1. **AACS 起動判定が `Unit_Key_RO.inf` のみ** (aacs.c:78)。
   BDAV 仕様は録画用 AACS ディレクトリに `MKB_RW.inf` を持つと明記している。
   録画ディスクが `Unit_Key_RO.inf` を持たないなら **AACS 経路が起動せず**、
   暗号化済みコンテンツが復号されずにそのまま出てしまう。
   → 実ディスクで確認する (6.5.3 の `ls /mnt/bd/AACS/`)。
2. **AACS for recorded (MKB_RW) の鍵はディスク自身にある**ので、
   原理的にはディスクを挿せば復号できる。欠けているのは player 側の鍵ではなく、
   対応しているかどうか。

#### 6.6.3 BDAV + AACS で塞がっている点 (CPS 選択)

AACS の復号には「どのタイトルの CPS unit を使うか」の選択が要る。
libbluray はそれを 3 経路で処理している:

- `bdpriv_dec_start(dec, num_titles)`: `num_titles == 0` のとき
  `dec->use_menus = 1` にする (src/libbluray/disc/dec.c:362-376)
- `bdpriv_dec_open_stream()`: `use_menus == 0` なら
  `bdpriv_aacs_select_title(dec->aacs, 0xffff)` で手動リセット
  (「There won't be title events --> need to manually reset AACS CPS」 dec.c:129-134)
- `bdpriv_dec_title()`: `DISC_EVENT_TITLE` を受けると `aacs_select_title()` を呼ぶ。
  `DISC_EVENT_TITLE` は PSR の `PSR_TITLE_NUMBER` 書き込みから発火する
  (src/libbluray/bluray.c:3414)

**BDAV ではこの 3 経路とも走らない**:

- `bd_get_titles()` は `disc_event(DISC_EVENT_START, bd->disc_info.num_titles)` を呼ぶ
  (bluray.c:2782)。BDAV は index が無いので `num_titles == 0` → **`use_menus = 1`**
  → `bdpriv_dec_open_stream()` の手動リセットがスキップされる
- `bd_select_title()` → `_open_playlist()` は `PSR_TITLE_NUMBER` を書かない
  (`_play_title()` だけが書く bluray.c:3619) → **`DISC_EVENT_TITLE` が発火しない**
  → `aacs_select_title()` が一度も呼ばれない

→ BDAV + 暗号化コンテンツでは **CPS 選択が一度も行われない** 可能性があり、
復号が失敗または誤る。実装時に塞ぐ必要のある点。
(暗号化されていない録画ディスクでは `dec == NULL` なので無関係)

対策案:

- BDAV モードで `_open_playlist()` から `PSR_TITLE_NUMBER` を書き、
  `DISC_EVENT_TITLE` を発火させる (BDMV の `bd_play()` 経路と二重にならないか注意)
- BDAV では `use_menus` を 0 に保ったまま 0xffff リセットに任せる (単純)

#### 6.6.4 結論

- **libaacs との組み合わせで視聴は実現可能**。
  ただし libaacs は「録画ディスクが暗号化されている場合」の保険であって
  必須ではない。**多くの録画 BDAV ディスクはクリア**なので、
  実際には libaacs なしで再生できる可能性が高い
- libbluray 側の作業は §4-§5 の BDAV メタデータ対応
  (+ 6.6.3 の CPS 選択、+ 6.6.2 注意 1 の判定緩和) のみ。
  libaacs 本体の改造は不要 (VideoLAN の別プロジェクト。libbluray は dlopen するだけ)
- 映像表示は player 側の作業。libbluray は「復号済みの TS を流す」ところまで

実測の根拠 (録画 BDAV はクリアである可能性が高い):

- `sorshi/bdav` は**クリアな TS**を BDAV に包むだけで
  「家庭用 BD レコーダー/プレーヤー互換」のツリーを生成する。
  暗号化済みなら再生できないはず
- 地上デジタル / BS / CS 録画はチューナー側で CAS が解除され、
  クリアな TS としてディスクに書かれる
- BD+ は BD-ROM ベースの AACS DRM なので、録画ディスクにはまず無い

#### 6.6.5 player 側の契約

§4.4 の決定 (D8) で `bd_play()` は BDAV では何もしないので、
player 側は `bd_get_titles()` → `bd_select_title()` を使う必要がある。
**メニューなしディスク (incomplete image) 向けのフローが player に既にあれば
追加対応は最小**だが、VLC の libbluray module が BDAV でも
「タイトル一覧→選択」を持つかは VLC 側 (別リポジトリ) での確認が要る。
ここは libbluray だけの話ではないので、
README かリリースノートに「BDAV は `bd_get_titles()` 経由で使う」旨を
書いておくのが良い。

---

## 7. 未確定事項 (実装前に詰める)

**決定済み** (§4.3 / §4.4):

- Q2 `mark_type` の意味 → **type 1 と type 4 をチャプター扱い**。判定は helper に集約し、
  mark_type / maker_id の分布をログ出力。`MPLS_PLM` に `maker_id` を追加して保存。
  仕様確定を待たずに実装可能。
- Q4 `bd_play()` の BDAV 挙動 → **(a) 何もしない**。app / player に
  `bd_get_titles()` → `bd_select_title()` の契約を委ねる。

**未確定** (いずれも実装を止めない):

1. **index ファイル名の正体**
   仕様 (BD-RE Part 3) は `index.bdav`、
   実装済みの生成ツール (sorshi/bdav) は `info.bdav` を使う。
   両方を受け付ける (Q1 / §1.2)。

2. **`.vpls` の意味**
   blu-ray.org.uk の記述は `PLAYLIST` に `xxxxx.vpls` もありとしているが、
   文面は `xxxxx.mpls` の写し間違いの疑いがある。
   実ファイル命名は `.rpls` が事実上の標準。**対象外**。

3. **PlayItem の厳密なビットレイアウト**
   上記の「バイト境界 20 バイト」表記は chotBDAV 互換の実出力からの逆解析に基づく。
   BD-RE Part 3 の正本 (該当章) と照合して確定したい。
   逆解析結果が実機と食い違っても、PlayItem は `clip_id` / `IN` / `OUT` だけ読めば
   再生は成立する (STN は CLPI 由来) ので影響は限定的。

4. **BD-J / メニュー**
   BDAV には BD-J も HDMV メニューも無い、という前提。
   一部の刻録機が書き出す BDAV に MovieObject 相当が含まれる可能性は否定できない。

5. **HEVC TS モードの index / playlist が別形式か**
   §4.0 の前提 (HDMV TS と HEVC TS でメタデータ構造が共通) が成り立つか。
   BD-RE Part 3 v5.0 の正本参照が必要。**HDMV TS の実装自体には影響しない。**

6. **backup ディレクトリ名**
   仕様は `BDAV1/`, `BDAV2/`, 生成ツールは `BACKUP/`。両方を受け付ける。

7. **BDAV の 1 録画 = 1 タイトルか**
   基本は 1 録画 = 1 `.rpls`。実機では 1 チャンネルに複数番組がある場合も。
   タイトル一覧は `PLAYLIST` ディレクトリ走査 (D7) なので、
   どちらのモデルでも同じ結果になるはず。

**追加で検証が必要な項目** (実装時に実ディスクで判断):

8. **録画 BDAV のコンテンツが暗号化されているか**
   `ls /mnt/bd/AACS/` と m2ts の `transport_scrambling_control` で判定 (§6.5.3)。
   暗号化されている場合に限り、libaacs 経路の実装 (CPS 選択の是正、
   判定条件の緩和) が必要になる。クリアなら §4-§5 の作業だけで完結する。

9. **録画 BDAV の AACS ディレクトリに `Unit_Key_RO.inf` があるか**
   無い場合、`bdpriv_aacs_required()` (src/libbluray/disc/aacs.c:78) が
   AACS 経路を起動しない。`MKB_RW.inf` も見るよう判定を緩和する必要があるかも
   (§6.6.2 注意 1)。

---

## 8. 実装状況 (2026-10)

HDMV TS プレイモードを主軸として BDAV 読み出しを実装済み。

### 8.1 実装済みの変更

| ファイル | 変更内容 |
|---|---|
| `src/libbluray/disc/disc.h` / `.c` | `bd_disc_format` (BDMV/BDAV) を追加。`disc_open()` 起動時に `BDMV/index.bdmv` が無く `BDAV/index.bdav` or `BDAV/info.bdav` が有るなら BDAV と判定 (BDMV 優先)。`disc_format()` / `disc_root_dir()` / `disc_app_path()` を追加。`disc_open_stream()` / `disc_open_path_dec()` / `disc_pseudo_id()` をルート対応化 |
| `src/libbluray/bdnav/bdmv_parse.c` / `.h` | `bdmv_parse_header2()` を追加 (複数シグネチャ受理)。既存 `bdmv_parse_header()` はそのラッパ |
| `src/libbluray/bdnav/clpi_parse.c` | `M2TS0100` (BDAV) シグネチャ受理。BDAV 用 stream attribute 解析 (ISRC 無し・最大 3 byte・言語コード無し) を追加。BDMV には extension data が無いので 0x18 は reserved 扱い。`clpi_lookup_spn()` に **coarse テーブルが STC 開始点を含まない場合の fallback** を追加 (§8.3) |
| `src/libbluray/bdnav/mpls_parse.c` | `PLST0100` (BDAV) シグネチャ受理。BDAV 用 PlayItem (byte-aligned 20 byte) / PlayListMark (46 byte/件・maker_id 保存) 解析を追加。`MPLS_PLM.maker_id` を追加。`mpls_filename()` を追加 (`.mpls` / `.rpls`) |
| `src/libbluray/bdnav/mpls_data.h` | `MPLS_PL.is_bdav` / `MPLS_PLM.maker_id` / `BD_MARK_CHAPTER` を追加 |
| `src/libbluray/bdnav/uo_mask.h` | `uo_mask_get_all()` を追加 (UO mask を持たない形式用) |
| `src/libbluray/bdnav/navigation.c` | `PLAYLIST` ディレクトリをルート対応化。**BDAV 用の `MPLS_STN` 合成** (CLPI ProgramInfo から video/audio/pg/ig を復元) を追加。チャプター判定を `_pl_is_chapter()` に集約 (BDAV は type 1 と type 4) |
| `src/libbluray/bdnav/index_parse.c` | BDAV index (`index.bdav` / `info.bdav`) 解析を追加。`TableOfPlayLists` からタイトルを生成 |
| `src/libbluray/bluray.c` | playlist ファイル名を `mpls_filename()` で生成。BDAV では `no_menu_support = 1` |
| `src/libbluray/disc/aacs.c` | AACS 判定に `AACS/MKB_RW.inf` (AACS for recorded) を追加 |
| `src/tools/bd_list_titles.c` | 出力の `(playlist: %05d.mpls)` を `(playlist: %05d)` に (拡張子は形式依存) |

### 8.2 テスト

`test/bdav/` に合成テストディスク生成と回帰確認スクリプトを追加した。

```bash
meson setup build -Denable_devtools=true -Denable_examples=true
meson compile -C build
./test/bdav/run_tests.sh build
```

- `test/bdav/make_testdata.py` — 合成 M2TS (PAT / PMT / I フレーム付き MPEG-2 映像、
  PCR 不連続 1 箇所) から BDAV 形式と BDMV 形式のディスクを生成。
  BDAV 側のメタデータは `sorshi/bdav` の writer と同じ構造 (chotBDAV 互換)。
- `test/bdav/run_tests.sh` — BDAV / BDMV 両方で
  「ディスク検出」「タイトル列挙」「読み出しが元とバイト一致」を確認。

実測結果: BDAV / BDMV とも全項目 PASS。読み出した m2ts は元と md5 一致。

### 8.3 実装中に判明した BDMV 共通の実装不具合

`clpi_lookup_spn()` (src/libbluray/bdnav/clpi_parse.c) は、STC シーケンスの
開始 SPN に対応する coarse entry が無いと
`cl->clip.num_source_packets` (クリップ末尾) を返していた。
BDAV の録画では PCR 不連続が頻発し、EP マップの coarse テーブルも
疎 (fine PTS の wrap 位置にしか entry を作らない実装が存在する) ため、
STC 2 個目以降の PlayItem が丸ごと再生不能になっていた。

**修正**: coarse テーブルが STC 開始点を含まない場合、最後の coarse entry
から fine table を走査するようにした (fallback)。
BDMV 側でも同じ状況 (クリップ末尾 11 秒以内の PCR 不連続) で
同じ不具合的发生していたので、BDMV 側の挙動改善にも繋がる。

### 8.4 残作業

- **実物 BDAV ディスクでの検証** (§7 の Q1/Q2/Q3/Q7 が実測で確定する)
- **AACS 経路の検証** (§6.6.3)。BDAV index 解析により
  `disc_info.num_titles` がプレイリスト数になる → `use_menus` は 0 のまま →
  `bdpriv_dec_open_stream()` の `aacs_select_title(aacs, 0xffff)` による
  手動 CPS リセットが有効になる (§6.6.3 の穴は解消)。ただし暗号化された
  BDAV ディスクでの動作確認は未実施
- **HEVC TS / SESF** (§4.0 の対象外)

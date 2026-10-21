# BDAV / BDMV test data

libbluray の BDAV (BD-RE Part 3) 対応と、既存 BDMV 経路の回帰確認用。

このディレクトリには **自動テスト基盤は無い** (meson に `test()` 定義なし) ため、
Python で合成したテストディスクを生成し、`bd_info` / `bd_list_titles` /
`libbluray_test` を `run_tests.sh` で実行するためのもの。

## 使い方

```bash
# 1. ビルド (devtools / examples が必要)
meson setup build -Denable_devtools=true -Denable_examples=true
meson compile -C build

# 2. テスト実行
./test/bdav/run_tests.sh build
```

`run_tests.sh` は以下を確認する:

| 項目 | 内容 |
|---|---|
| ディスク検出 | `bd_info` が "BluRay detected: yes" を出すか |
| タイトル列挙 | `bd_list_titles` がタイトルとチャプター数を出すか |
| 読み出し | `libbluray_test` が出力した m2ts が元ファイルとバイト一致するか |

BDAV と BDMV の両方を同じ内容で検査する (BDMV は回帰確認用)。

## 生成されるもの

```
<work>/bdav_disc/BDAV/
    info.bdav            インデックス (BDAV0100)
    PLAYLIST/00001.rpls  ムービー・プレイリスト (PLST0100)
    CLIPINF/00001.clpi   クリップ情報 (M2TS0100)
    STREAM/00001.m2ts    AV ストリーム
<work>/bdmv_disc/BDMV/
    PLAYLIST/00000.mpls  ムービー・プレイリスト (MPLS0100)
    CLIPINF/00000.clpi   クリップ情報 (HDMV0100)
    STREAM/00000.m2ts    AV ストリーム
```

ストリーム自体は合成 MPEG-2 TS (PAT / PMT / I フレーム付き映像 1 本) で、
**意図的に PCR 不連続**を 1 箇所入れてある。これにより

- clip に STC シーケンスが 2 個できる (BDAV なら PlayItem 2 個)
- PlayListMark に type 4 (チャプター) と type 5 (PCR 不連続) が出る
- EP マップの coarse テーブルが疎になるケース (libbluray の
  `clpi_lookup_spn()` の fallback 経路) を試せる

## 外部ツールとの比較

BDAV のメタデータは <https://github.com/sorshi/bdav> の
`tools/bdav_dump.py` と同じ構造で生成している (同ツールの writer は
chotBDAV.exe とバイト一致で検証済み)。実物の BDAV ディスクを入手した
内容と突き合わせる際の基準として使える。

```bash
git clone https://github.com/sorshi/bdav
python3 bdav/tools/bdav_dump.py <work>/bdav_disc/BDAV/PLAYLIST/00001.rpls
```

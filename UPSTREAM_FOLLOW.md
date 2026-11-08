# Upstream 追従手順 (code.videolan.org)

## libbluray

### 追従手順

```bash
cd ~/dev/libbluray

# 1. upstream の最新を取得
git fetch origin

# 2. 新規コミットがあるか確認
git log --oneline HEAD..origin/master

# 3. あれば rebase
git rebase origin/master

# 4. GitHub にプッシュ
git push github feature/bdav-hdmv-ts --force-with-lease
```

### 注意事項
- feature ブランチ (`feature/bdav-hdmv-ts`) で作業している
- rebase 時にコンフリクトが発生した場合は手動で解決
- `--force-with-lease` を使う (安全な force push)

## libaacs

### 追従手順

```bash
cd ~/dev/libaacs

# 1. upstream の最新を取得
git fetch origin

# 2. 新規コミットがあるか確認
git log --oneline HEAD..origin/master

# 3. あれば rebase (KEYDB.cfg を除外するため filter-branch が必要な場合あり)
git rebase origin/master

# 4. GitHub にプッシュ
git push github master
```

### KEYDB.cfg の取り扱い (重要)

- `KEYDB.cfg` は **絶対にリモートにプッシュしない**
- `.gitignore` に `KEYDB.cfg` を記載済み
- upstream の KEYDB.cfg (example) が含まれるコミットを push する場合は
  `git filter-branch` で KEYDB.cfg を全履歴から除去してから push する
- 手順:
  ```bash
  git filter-branch --force --index-filter \
    'git rm --cached --ignore-unmatch KEYDB.cfg' \
    --prune-empty --tag-name-filter cat -- --all
  rm -rf .git/refs/original
  git reflog expire --expire=now --all
  git gc --prune=now
  # KEYDB.cfg を復元 (filter-branch で消えた場合)
  # (バックアップから復元するか、手動で再作成)
  git push --force github master
  ```

## ビルド手順 (meson/ninja が利用可能な場合)

```bash
# libbluray
cd ~/dev/libbluray
meson compile -C build

# libaacs
cd ~/dev/libaacs
autoreconf -vif && ./configure && make
```

## ビルド手順 (meson/ninja が利用不可の場合)

libbluray のビルドディレクトリ (`build/`) に `build.ninja` がある場合、
ninja バイナリを取得して `ninja -C build` でビルド可能。

libaacs は autotools/flex/bison が必要。利用不可の場合は
pre-built バイナリ (`/tmp/lab/libaacs.so.0`) を使用し、
Device Key をハードコードした minimal keydbcfg.c で再リンクする。
EOF
echo "written"
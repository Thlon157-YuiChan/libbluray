# Upstream 追従手順 (code.videolan.org)

## 前提

- Debian 13 (trixie) 環境を想定
- git, meson, ninja が利用可能であること
- GitHub CLI (gh) が認証済みであること

## libbluray

### 追従手順

```bash
# 1. upstream の最新を取得
cd <libbluray-source-dir>
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
cd <libaacs-source-dir>

# 1. upstream の最新を取得
git fetch origin

# 2. 新規コミットがあるか確認
git log --oneline HEAD..origin/master

# 3. あれば rebase
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
  git push --force github master
  ```

## ビルド手順 (meson/ninja が利用可能な場合)

```bash
# libbluray
cd <libbluray-source-dir>
meson compile -C build

# libaacs
cd <libaacs-source-dir>
autoreconf -vif && ./configure && make
```

## ビルド手順 (meson/ninja が利用不可の場合)

libbluray のビルドディレクトリ (`build/`) に `build.ninja` がある場合、
ninja バイナリを取得して `ninja -C build` でビルド可能。

libaacs は autotools/flex/bison が必要。利用不可の場合は
pre-built バイナリを使用し、
Device Key をハードコードした minimal keydbcfg.c で再リンクする。

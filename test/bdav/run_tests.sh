#!/bin/sh
#
# BDAV / BDMV regression check for libbluray.
#
# Generates synthetic test discs and verifies that libbluray can
#   - detect the disc application format (BDMV / BDAV)
#   - list the titles of the disc
#   - read the stream back byte for byte
#
# Usage: run_tests.sh [build-dir] [work-dir]

set -e

BUILD=${1:-build}
WORK=${2:-/tmp/libbluray-bdav-test}

# make the build dir path absolute (the script changes the working directory)
case "$BUILD" in
    /*) ;;
    *) BUILD="$(pwd)/$BUILD" ;;
esac

if [ ! -x "$BUILD/src/tools/bd_info" ]; then
    echo "ERROR: $BUILD/src/tools/bd_info not found." >&2
    echo "       Build first: meson setup build -Denable_devtools=true -Denable_examples=true" >&2
    exit 1
fi

if [ ! -x "$BUILD/src/examples/libbluray_test" ]; then
    echo "ERROR: $BUILD/src/examples/libbluray_test not found." >&2
    echo "       Build first: meson setup build -Denable_devtools=true -Denable_examples=true" >&2
    exit 1
fi

SCRIPT_DIR=$(dirname "$0")
rm -rf "$WORK"
mkdir -p "$WORK"

echo "== generating test data =="
python3 "$SCRIPT_DIR/make_testdata.py" "$WORK"

rc=0

check() {
    if [ "$1" = "0" ]; then
        echo "  PASS: $2"
    else
        echo "  FAIL: $2"
        rc=1
    fi
}

for kind in bdav bdmv; do
    root="$WORK/${kind}_disc"
    echo "== $kind =="

    "$BUILD/src/tools/bd_info" "$root" > "$WORK/$kind.info" 2>&1 || true
    if grep -q "BluRay detected     : yes" "$WORK/$kind.info"; then
        check 0 "$kind: disc detected"
    else
        check 1 "$kind: disc detected"
        cat "$WORK/$kind.info"
    fi

    "$BUILD/src/tools/bd_list_titles" "$root" > "$WORK/$kind.titles" 2>&1 || true
    if grep -q "index:   1 duration:" "$WORK/$kind.titles"; then
        check 0 "$kind: title listed"
        sed 's/^/        /' "$WORK/$kind.titles"
    else
        check 1 "$kind: title listed"
        cat "$WORK/$kind.titles"
    fi

    # read the stream back and compare with the original
    ( cd "$WORK" && "$BUILD/src/examples/libbluray_test" "$root" 0 > "$kind.dump.log" 2>&1 || true )
    stream=$(find "$root" -name '*.m2ts' | head -1)
    if [ -f "$WORK/streamdump.m2ts" ] && cmp -s "$WORK/streamdump.m2ts" "$stream"; then
        check 0 "$kind: stream read back identical to the source"
    else
        check 1 "$kind: stream read back identical to the source"
        tail -5 "$WORK/$kind.dump.log" | sed 's/^/        /'
    fi
    rm -f "$WORK/streamdump.m2ts"
done

echo
if [ "$rc" = "0" ]; then
    echo "All tests passed."
else
    echo "Some tests FAILED."
fi
exit $rc

#!/bin/sh
set -eu
project=/hy-netdisk/jq/project/DriveServe
if [ ! -d "$project/.git" ]; then
    if [ -n "$(ls -A "$project")" ]; then
        echo "Project directory is nonempty but has no Git checkout; refusing to replace it." >&2
        exit 1
    fi
    git clone --quiet /opt/driveserve/source.bundle "$project"
    git -C "$project" checkout --quiet --detach "$DRIVESERVE_SOURCE_COMMIT"
    git -C "$project" remote remove origin
fi
cd "$project"
case "${DRIVESERVE_DEPENDENCY_LAYER:-base}" in
    base) export PYTHONPATH="$project" ;;
    training) export PYTHONPATH="/hy-tmp/driveserve/training-deps-v1:$project" ;;
    awq) export PYTHONPATH="/hy-tmp/driveserve/awq-deps-v2:/hy-tmp/driveserve/training-deps-v1:$project" ;;
    *) echo "DRIVESERVE_DEPENDENCY_LAYER must be base, training, or awq" >&2; exit 2 ;;
esac
exec "$@"

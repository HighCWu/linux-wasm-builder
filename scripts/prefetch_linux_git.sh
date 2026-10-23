#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Independent public-CI experiment. Never replace a fixed-output hash check.
set -euo pipefail

[[ ${SOURCE_REVISION:-} =~ ^[0-9a-f]{40}$ ]]
[[ ${BASELINE_REVISION:-} =~ ^[0-9a-f]{40}$ ]]
[[ ${BASELINE_HASH:-} =~ ^sha256-[A-Za-z0-9+/]{43}=$ ]]
[[ $SOURCE_REVISION != "$BASELINE_REVISION" ]]

source_work=$(mktemp -d)
git init --quiet "$source_work/git"
git -C "$source_work/git" remote add origin https://github.com/HighCWu/linux.git
# Fetch the complete depth-two pack once. Lazy-blob archive can otherwise
# turn this fallback into one network request per file.
git -C "$source_work/git" -c http.version=HTTP/1.1 fetch --quiet --depth=2 origin "$SOURCE_REVISION"
[[ $(git -C "$source_work/git" rev-parse FETCH_HEAD) == "$SOURCE_REVISION" ]]
[[ $(git -C "$source_work/git" show -s --format=%P "$SOURCE_REVISION") == "$BASELINE_REVISION" ]]
[[ $(git -C "$source_work/git" diff --name-status "$BASELINE_REVISION" "$SOURCE_REVISION") == $'M\tkernel/futex/core.c' ]]
[[ -z $(git -C "$source_work/git" diff --summary "$BASELINE_REVISION" "$SOURCE_REVISION") ]]
attribute_status=0
git -C "$source_work/git" grep --quiet 'export-subst' "$SOURCE_REVISION" -- \
  .gitattributes ':(glob)**/.gitattributes' || attribute_status=$?
# Commit/ref substitutions can differ between an archive service and local
# Git even when paths/modes are unchanged. Refuse this experiment if present,
# or if the attribute inspection itself failed (grep status > 1).
[[ $attribute_status -eq 1 ]]

# The baseline was already fetched and hashed by the archive fetcher. Only
# accept this alternate extraction after matching that independently known
# NAR hash; the candidate must have unchanged paths, modes and attributes.
mkdir "$source_work/baseline" "$source_work/candidate"
git -C "$source_work/git" archive --format=tar "$BASELINE_REVISION" |
  tar --extract --directory="$source_work/baseline"
verified_baseline=$(nix hash path --type sha256 "$source_work/baseline")
[[ $verified_baseline == "$BASELINE_HASH" ]]
git -C "$source_work/git" archive --format=tar "$SOURCE_REVISION" |
  tar --extract --directory="$source_work/candidate"
candidate_hash=$(nix hash path --type sha256 "$source_work/candidate")
[[ $candidate_hash =~ ^sha256-[A-Za-z0-9+/]{43}=$ ]]
[[ $candidate_hash != "$verified_baseline" ]]

printf 'Verified baseline revision: %s\nVerified baseline hash: %s\n' "$BASELINE_REVISION" "$verified_baseline"
printf 'Candidate revision: %s\nCandidate hash: %s\n' "$SOURCE_REVISION" "$candidate_hash"
if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
  {
    printf 'Verified baseline revision: %s\n\nVerified baseline hash: %s\n\n' "$BASELINE_REVISION" "$verified_baseline"
    printf 'Candidate revision: %s\n\nCandidate hash: %s\n' "$SOURCE_REVISION" "$candidate_hash"
  } >>"$GITHUB_STEP_SUMMARY"
fi

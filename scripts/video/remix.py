"""Refresh the "audio" block of a recorded manifest from the storyboard, so a new soundtrack can be mixed
without recording the screen again.

    python3 scripts/video/remix.py <manifest.json> <storyboard.json>

record.py copies the storyboard's "audio" block into manifest.json when it records. Later changes to the music
bed, cue gains or narration settings only reach compose.sh through that copy; this replaces it and leaves every
other key (segments, frames, clips) untouched. Run it on a copy of the recording folder, then compose.sh.

record.py writes absolute paths (frames, clips, narration). In a copied folder those still point at the original, so
compose.sh would read, and voice.py would extend, the original. When every such path also exists under the
manifest's own folder, they are moved there; otherwise they are left as they are and the reason is printed.
"""
import json
import os
import sys


def remix(manifest, board):
    """The manifest with its "audio" block replaced by the storyboard's; returns (manifest, changed keys)."""
    old, new = manifest.get("audio", {}), board["audio"]
    changed = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
    return dict(manifest, audio=new), changed


# The manifest keys that hold file paths (frames.py, record.py, voice.py); captions and other text are never moved.
FILE_KEYS = ("png", "back", "front", "clip", "wav")


def is_file_path(key, value):
    return key in FILE_KEYS and isinstance(value, str) and os.path.isabs(value)


def paths(value):
    """Every absolute file path inside a manifest value."""
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in ([v] if is_file_path(k, v) else paths(v))]
    if isinstance(value, list):
        return [p for v in value for p in paths(v)]
    return []


def swap(value, old, new):
    if isinstance(value, dict):
        return {k: os.path.join(new, os.path.relpath(v, old)) if is_file_path(k, v) and os.path.commonpath([v, old]) == old
                else swap(v, old, new) for k, v in value.items()}
    if isinstance(value, list):
        return [swap(v, old, new) for v in value]
    return value


def rebase(manifest, folder):
    """(manifest, old folder or None): paths moved from the folder the recording was copied from to `folder`.

    The old folder is the closest common parent of the manifest's absolute paths for which every path, taken
    relative to it, exists under `folder`. Nothing moves when the paths are already there or the copy lacks a file."""
    found = sorted(set(paths(manifest)))
    folder = os.path.abspath(folder)
    if not found or all(os.path.commonpath([p, folder]) == folder for p in found):
        return manifest, None
    old = os.path.commonpath(found)
    while True:
        if old != folder and all(os.path.exists(os.path.join(folder, os.path.relpath(p, old))) for p in found):
            return swap(manifest, old, folder), old
        if os.path.dirname(old) == old:
            return manifest, None
        old = os.path.dirname(old)


def main(manifest_path, board_path):
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    with open(board_path, encoding="utf-8") as fh:
        board = json.load(fh)
    manifest, changed = remix(manifest, board)
    folder = os.path.dirname(os.path.abspath(manifest_path))
    manifest, old = rebase(manifest, folder)
    if old:
        print(f"remix: paths moved from {old} to {folder}")
    elif any(os.path.commonpath([p, folder]) != folder for p in paths(manifest)):
        print(f"remix: some paths are outside {folder} and the copy lacks them; left as they are")
    tmp = manifest_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    os.replace(tmp, manifest_path)
    print(f"remix: audio {'updated: ' + ', '.join(changed) if changed else 'unchanged'} -> {manifest_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])

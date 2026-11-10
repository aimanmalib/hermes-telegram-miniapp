"""Refresh the "audio" block of a recorded manifest from the storyboard, so a new soundtrack can be mixed
without recording the screen again.

    python3 scripts/video/remix.py <manifest.json> <storyboard.json>

record.py copies the storyboard's "audio" block into manifest.json when it records. Later changes to the music
bed, cue gains or narration settings only reach compose.sh through that copy; this replaces it and leaves every
other key (segments, frames, clips) untouched. Run it on a copy of the recording folder, then compose.sh.
"""
import json
import os
import sys


def remix(manifest, board):
    """The manifest with its "audio" block replaced by the storyboard's; returns (manifest, changed keys)."""
    old, new = manifest.get("audio", {}), board["audio"]
    changed = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
    return dict(manifest, audio=new), changed


def main(manifest_path, board_path):
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    with open(board_path, encoding="utf-8") as fh:
        board = json.load(fh)
    manifest, changed = remix(manifest, board)
    tmp = manifest_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    os.replace(tmp, manifest_path)
    print(f"remix: audio {'updated: ' + ', '.join(changed) if changed else 'unchanged'} -> {manifest_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])

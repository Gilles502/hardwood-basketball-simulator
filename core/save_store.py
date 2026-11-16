"""All-or-nothing commit of a set of files into a save slot, with the replaced files kept as the one backup.

A commit copies the new files into `<slot>/.pending/`, then writes `.pending/COMMIT.json` (the commit point),
then moves the old files into `.backup.new/` and the pending ones into place. A crash before the marker leaves
the previous save (the pending folder is dropped on the next load); a crash after it is finished by
`roll_forward` on the next load. `.backup/` always holds the files the last commit replaced, so the save before
the last one is `live files + .backup/ on top` (files the last commit did not touch were the same in both).
"""
import hashlib
import json
import os
import shutil
import time
from typing import Dict, Optional

from core.config import CONFIG

# Save format version, written in save_metadata.json. 1 = saves made before this module (no field).
SAVE_VERSION = 2

PENDING_DIR = ".pending"
BACKUP_DIR = ".backup"
BACKUP_NEW_DIR = ".backup.new"
BACKUP_OLD_DIR = ".backup.old"
COMMIT_MARKER = "COMMIT.json"


def file_digest(path: str) -> Optional[str]:
    """sha256 of a file, None if it does not exist."""
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _retry(fn, *args):
    """Windows: an antivirus or indexer may hold a fresh file for a moment."""
    attempts = max(1, CONFIG.SAVES.FILE_RETRY_COUNT)
    for i in range(attempts):
        try:
            return fn(*args)
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(CONFIG.SAVES.FILE_RETRY_DELAY_S)


def _move(src: str, dst: str) -> None:
    _retry(os.replace, src, dst)


def _rmtree(path: str) -> None:
    if os.path.isdir(path):
        _retry(shutil.rmtree, path)


def _fsync_file(path: str) -> None:
    with open(path, "rb+") as f:
        os.fsync(f.fileno())


def commit(slot_dir: str, files: Dict[str, str]) -> None:
    """Commits `files` (slot-relative name -> fully written source file, left in place) into the slot."""
    os.makedirs(slot_dir, exist_ok=True)
    pending = os.path.join(slot_dir, PENDING_DIR)
    _rmtree(pending)  # a stray pending folder without a marker is a half-written older save
    os.makedirs(pending)
    for name, src in files.items():
        dst = os.path.join(pending, name)
        shutil.copyfile(src, dst)
        _fsync_file(dst)
    marker = os.path.join(pending, COMMIT_MARKER)
    with open(marker + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"files": sorted(files)}, f)
        f.flush()
        os.fsync(f.fileno())
    _move(marker + ".tmp", marker)
    roll_forward(slot_dir)


def roll_forward(slot_dir: str) -> bool:
    """Finishes a committed save left half-applied, or drops an uncommitted one. True if it finished a commit."""
    pending = os.path.join(slot_dir, PENDING_DIR)
    marker = os.path.join(pending, COMMIT_MARKER)
    if not os.path.isfile(marker):
        _rmtree(pending)
        return False
    with open(marker, encoding="utf-8") as f:
        names = json.load(f)["files"]

    backup = os.path.join(slot_dir, BACKUP_DIR)
    backup_new = os.path.join(slot_dir, BACKUP_NEW_DIR)
    backup_old = os.path.join(slot_dir, BACKUP_OLD_DIR)
    any_pending = any(os.path.exists(os.path.join(pending, n)) for n in names)

    if any_pending:
        if not os.path.isdir(backup_new):
            # Fresh start: the backup of the save before is replaced by this commit's one.
            if os.path.isdir(backup):
                _rmtree(backup_old)
                _move(backup, backup_old)
            os.makedirs(backup_new)
        for name in names:
            src = os.path.join(pending, name)
            if not os.path.exists(src):
                continue  # already moved into place
            live = os.path.join(slot_dir, name)
            kept = os.path.join(backup_new, name)
            if os.path.exists(live) and not os.path.exists(kept):
                _move(live, kept)
            _move(src, live)
    if os.path.isdir(backup_new):  # also after a crash right after the last file move
        _rmtree(backup)
        _move(backup_new, backup)

    _rmtree(pending)
    _rmtree(backup_old)
    return True


def restore_backup(slot_dir: str) -> bool:
    """Puts the save before the last one back (live files + the backup on top). False if there is no backup."""
    backup = os.path.join(slot_dir, BACKUP_DIR)
    if not os.path.isdir(backup) or not os.listdir(backup):
        return False
    for name in os.listdir(backup):
        tmp = os.path.join(slot_dir, name + ".restore.tmp")
        shutil.copyfile(os.path.join(backup, name), tmp)
        _move(tmp, os.path.join(slot_dir, name))
    return True

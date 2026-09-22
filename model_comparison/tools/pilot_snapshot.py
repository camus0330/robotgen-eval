"""Bounded pilot snapshots of stopped tool output; reject links before any read."""
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile


class SnapshotRejected(ValueError):
    pass


def relative_name(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise SnapshotRejected("invalid relative path")
    parts = value.split("/")
    if any(p in ("", ".", "..") or p.endswith((".", " ")) for p in parts):
        raise SnapshotRejected("invalid relative path")
    reserved = {"con", "prn", "aux", "nul", *("com"+str(i) for i in range(1,10)), *("lpt"+str(i) for i in range(1,10))}
    if any(p.split(".")[0].lower() in reserved for p in parts):
        raise SnapshotRejected("reserved device path")
    return value


@contextmanager
def _pin(path, directory):
    """Windows handles prohibit replacement and writes while inventory is held."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes as w
        import msvcrt
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
        api.CreateFileW.restype = w.HANDLE
        api.CloseHandle.argtypes = [w.HANDLE]
        api.GetFileInformationByHandleEx.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
        # OPEN_REPARSE_POINT, BACKUP_SEMANTICS; share read only, no delete/write.
        handle = api.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x02200000, None)
        if handle == w.HANDLE(-1).value:
            raise SnapshotRejected("cannot pin snapshot entry")
        class Tags(ctypes.Structure):
            _fields_ = [("attributes", w.DWORD), ("tag", w.DWORD)]
        tags = Tags()
        if not api.GetFileInformationByHandleEx(handle, 9, ctypes.byref(tags), ctypes.sizeof(tags)) or tags.attributes & 0x400:
            api.CloseHandle(handle)
            raise SnapshotRejected("reparse point rejected before read")
        if bool(tags.attributes & 0x10) != directory:
            api.CloseHandle(handle)
            raise SnapshotRejected("entry type changed")
        if directory:
            try:
                yield None
            finally:
                api.CloseHandle(handle)
        else:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
            with os.fdopen(fd, "rb") as stream:
                yield stream
    else:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else 0))
        if directory:
            try:
                yield None
            finally:
                os.close(fd)
        else:
            with os.fdopen(fd, "rb") as stream:
                yield stream


def safe_snapshot(source, destination=None, *, include=None, max_files=2048,
                  max_bytes=256 * 1024 * 1024, tool_stopped=True):
    """Inventory first, then copy to private staging; publish only a complete tree.

    Caller must own/quiesce the tool process. The Windows host pins all ancestor,
    directory and file handles against mutation, and rejects all reparse points.
    No raw bytes are read until the complete inventory and quotas are accepted.
    """
    if not tool_stopped:
        raise SnapshotRejected("tool stop not confirmed")
    source = Path(os.path.abspath(source))  # Do NOT resolve untrusted links.
    destination = Path(os.path.abspath(destination)) if destination is not None else None
    selected = {relative_name(x) for x in include} if include is not None else None
    stage = None
    with ExitStack() as stack:
        pinned = set()
        def pin_directory(path):
            for parent in (*reversed(path.parents), path):
                if parent not in pinned:
                    info = parent.lstat()
                    if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                        raise SnapshotRejected("directory link rejected before read")
                    stack.enter_context(_pin(parent, True))
                    pinned.add(parent)
        pin_directory(source)
        if destination is not None:
            if destination == source or source in destination.parents or os.path.lexists(destination):
                raise SnapshotRejected("snapshot destination must be new and outside source")
            pin_directory(destination.parent)
        inventory = []
        total = 0
        entries = 0
        def walk(directory):
            nonlocal total, entries
            for item in sorted(directory.iterdir()):
                entries += 1
                if entries > max_files * 2:
                    raise SnapshotRejected("snapshot entry limit")
                info = item.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise SnapshotRejected("link rejected before read")
                if stat.S_ISDIR(info.st_mode):
                    pin_directory(item)
                    walk(item)
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    total += info.st_size
                    if len(inventory) >= max_files or total > max_bytes:
                        raise SnapshotRejected("snapshot file or byte limit")
                    relative = relative_name(item.relative_to(source).as_posix())
                    stream = stack.enter_context(_pin(item, False))
                    opened = os.fstat(stream.fileno())
                    if (opened.st_ino, opened.st_size, opened.st_mtime_ns) != (info.st_ino, info.st_size, info.st_mtime_ns):
                        raise SnapshotRejected("entry changed before read")
                    inventory.append((relative, stream, info.st_size))
                else:
                    raise SnapshotRejected("special file or hard link rejected")
        walk(source)
        if selected is not None and not selected <= {p for p, _, _ in inventory}:
            raise SnapshotRejected("declared input missing")
        try:
            if destination is not None:
                stage = Path(tempfile.mkdtemp(prefix=".pilot-incomplete-", dir=destination.parent))
            files = []
            for relative, stream, size in inventory:
                if selected is not None and relative not in selected:
                    continue
                data = stream.read(size + 1)
                if len(data) != size:
                    raise SnapshotRejected("file changed during read")
                files.append({"path": relative, "size": size, "sha256": hashlib.sha256(data).hexdigest()})
                if stage is not None:
                    target = stage / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as out:
                        out.write(data)
            files.sort(key=lambda x: x["path"])
            evidence = {"status": "COMPLETE", "files": files, "total_bytes": sum(f["size"] for f in files),
                        "sha256": hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
            if stage is not None:
                # Reading is finished; Windows ancestor locks otherwise prevent
                # rename even of the operator-owned sibling staging directory.
                stack.close()
                stage.rename(destination)
                stage = None
            return evidence
        finally:
            if stage is not None:
                stack.close()
                # Only our new staging directory, never an untrusted source tree.
                shutil.rmtree(stage)

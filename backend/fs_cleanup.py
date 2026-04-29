import shutil
import stat
import time
from pathlib import Path

DELETE_RETRIES = 10
DELETE_RETRY_DELAY_SECONDS = 0.05


def _as_path(path: str | Path) -> Path:
    return path if isinstance(path, Path) else Path(path)


def _make_writable(path: Path) -> None:
    try:
        path.chmod(stat.S_IWRITE | stat.S_IREAD)
    except FileNotFoundError:
        return
    except OSError:
        return


def _sleep_before_retry(attempt: int, retries: int, delay_seconds: float) -> None:
    if attempt < retries - 1:
        time.sleep(delay_seconds)


def _normalize_staging_root(path: Path, staging_root: str | Path | None) -> Path:
    candidate = _as_path(staging_root) if staging_root is not None else path.parent
    try:
        if candidate.resolve().is_relative_to(path.resolve()):
            candidate = path.parent
    except OSError:
        candidate = path.parent
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _build_tombstone_path(path: Path, staging_root: str | Path | None = None) -> Path:
    root = _normalize_staging_root(path, staging_root)
    return root / f"{path.name}.delete-{time.time_ns()}"


def _move_to_tombstone(
    path: str | Path,
    *,
    staging_root: str | Path | None = None,
    retries: int = DELETE_RETRIES,
    delay_seconds: float = DELETE_RETRY_DELAY_SECONDS,
) -> Path | None:
    source = _as_path(path)
    if not source.exists():
        return None

    last_error: OSError | None = None
    for attempt in range(retries):
        try:
            if not source.exists():
                return None
            tombstone = _build_tombstone_path(source, staging_root=staging_root)
            _make_writable(source)
            source.replace(tombstone)
            return tombstone
        except FileNotFoundError:
            return None
        except OSError as exc:
            last_error = exc
            _sleep_before_retry(attempt, retries, delay_seconds)

    if last_error is not None:
        raise last_error
    return None


def safe_unlink(
    path: str | Path,
    *,
    missing_ok: bool = True,
    staging_root: str | Path | None = None,
    best_effort: bool = False,
    retries: int = DELETE_RETRIES,
    delay_seconds: float = DELETE_RETRY_DELAY_SECONDS,
) -> Path | None:
    target = _as_path(path)
    last_error: OSError | None = None

    for attempt in range(retries):
        try:
            if not target.exists():
                if missing_ok:
                    return None
                raise FileNotFoundError(target)
            _make_writable(target)
            target.unlink()
            return None
        except FileNotFoundError:
            if missing_ok:
                return None
            raise
        except OSError as exc:
            last_error = exc
            _sleep_before_retry(attempt, retries, delay_seconds)

    if not target.exists():
        return None

    try:
        tombstone = _move_to_tombstone(
            target,
            staging_root=staging_root,
            retries=retries,
            delay_seconds=delay_seconds,
        )
    except OSError:
        if best_effort:
            return target if target.exists() else None
        raise
    if tombstone is None:
        return None

    for attempt in range(retries):
        try:
            if not tombstone.exists():
                return None
            _make_writable(tombstone)
            tombstone.unlink()
            return None
        except FileNotFoundError:
            return None
        except OSError as exc:
            last_error = exc
            _sleep_before_retry(attempt, retries, delay_seconds)

    if last_error is not None and target.exists():
        if best_effort:
            return target
        raise last_error
    return tombstone if tombstone.exists() else None


def _rmtree_onexc(func, path, _excinfo) -> None:
    retry_target = _as_path(path)
    _make_writable(retry_target)
    func(path)


def _delete_tree_once(target: Path) -> None:
    shutil.rmtree(target, ignore_errors=False, onexc=_rmtree_onexc)


def safe_remove_tree(
    path: str | Path,
    *,
    missing_ok: bool = True,
    staging_root: str | Path | None = None,
    best_effort: bool = False,
    retries: int = DELETE_RETRIES,
    delay_seconds: float = DELETE_RETRY_DELAY_SECONDS,
) -> Path | None:
    target = _as_path(path)
    if not target.exists():
        if missing_ok:
            return None
        raise FileNotFoundError(target)
    if target.is_file():
        return safe_unlink(
            target,
            missing_ok=missing_ok,
            staging_root=staging_root,
            best_effort=best_effort,
            retries=retries,
            delay_seconds=delay_seconds,
        )

    last_error: OSError | None = None
    for attempt in range(retries):
        try:
            if not target.exists():
                return None
            _delete_tree_once(target)
            return None
        except FileNotFoundError:
            return None
        except OSError as exc:
            last_error = exc
            _sleep_before_retry(attempt, retries, delay_seconds)

    if not target.exists():
        return None

    try:
        tombstone = _move_to_tombstone(
            target,
            staging_root=staging_root,
            retries=retries,
            delay_seconds=delay_seconds,
        )
    except OSError:
        if best_effort:
            return target if target.exists() else None
        raise
    if tombstone is None:
        return None

    for attempt in range(retries):
        try:
            if not tombstone.exists():
                return None
            _delete_tree_once(tombstone)
            return None
        except FileNotFoundError:
            return None
        except OSError as exc:
            last_error = exc
            _sleep_before_retry(attempt, retries, delay_seconds)

    if last_error is not None and target.exists():
        if best_effort:
            return target
        raise last_error
    return tombstone if tombstone.exists() else None


def safe_rmdir(
    path: str | Path,
    *,
    missing_ok: bool = True,
    staging_root: str | Path | None = None,
    best_effort: bool = False,
    retries: int = DELETE_RETRIES,
    delay_seconds: float = DELETE_RETRY_DELAY_SECONDS,
) -> Path | None:
    target = _as_path(path)
    last_error: OSError | None = None

    for attempt in range(retries):
        try:
            if not target.exists():
                if missing_ok:
                    return None
                raise FileNotFoundError(target)
            _make_writable(target)
            target.rmdir()
            return None
        except FileNotFoundError:
            if missing_ok:
                return None
            raise
        except OSError as exc:
            last_error = exc
            _sleep_before_retry(attempt, retries, delay_seconds)

    if not target.exists():
        return None

    try:
        tombstone = _move_to_tombstone(
            target,
            staging_root=staging_root,
            retries=retries,
            delay_seconds=delay_seconds,
        )
    except OSError:
        if best_effort:
            return target if target.exists() else None
        raise
    if tombstone is None:
        return None

    for attempt in range(retries):
        try:
            if not tombstone.exists():
                return None
            tombstone.rmdir()
            return None
        except FileNotFoundError:
            return None
        except OSError:
            try:
                _delete_tree_once(tombstone)
                return None
            except FileNotFoundError:
                return None
            except OSError as exc:
                last_error = exc
                _sleep_before_retry(attempt, retries, delay_seconds)

    if last_error is not None and target.exists():
        if best_effort:
            return target
        raise last_error
    return tombstone if tombstone.exists() else None

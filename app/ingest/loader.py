from pathlib import Path

from app.schemas.document import RawDocument

_IGNORED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
_TEMP_SUFFIXES = {".tmp", ".temp", ".swp", ".bak"}


def iter_corpus_files(
    root_dir: Path,
    extensions: tuple[str, ...] = (".md", ".txt"),
) -> list[Path]:
    root = root_dir.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Corpus root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Corpus root is not a directory: {root}")

    normalized_extensions = tuple(extension.lower() for extension in extensions)
    files: list[Path] = []
    for path in root.rglob("*"):
        if _should_ignore_path(path, root):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in normalized_extensions:
            continue
        if path.stat().st_size == 0:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.as_posix().lower())


def load_text_file(path: Path, root_dir: Path | None = None) -> RawDocument:
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Corpus file does not exist: {resolved}")
    if not resolved.is_file():
        raise IsADirectoryError(f"Corpus path is not a file: {resolved}")

    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Failed to read UTF-8 corpus file: {resolved}") from exc
    except OSError as exc:
        raise OSError(f"Failed to read corpus file: {resolved}") from exc

    if not content.strip():
        raise ValueError(f"Corpus file is empty after trimming whitespace: {resolved}")

    return RawDocument(
        source_path=_stable_relative_path(resolved, root_dir),
        content=content,
        encoding="utf-8",
        metadata_hint={"absolute_path": str(resolved)},
    )


def load_corpus(root_dir: Path) -> list[RawDocument]:
    return [load_text_file(path, root_dir=root_dir) for path in iter_corpus_files(root_dir)]


def _should_ignore_path(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True

    for part in relative.parts:
        if part in _IGNORED_DIRS or part.startswith("."):
            return True

    name = path.name
    if name.startswith("~$") or name.endswith("~"):
        return True
    if path.suffix.lower() in _TEMP_SUFFIXES:
        return True
    return False


def _stable_relative_path(path: Path, root_dir: Path | None = None) -> str:
    cwd = Path.cwd().resolve()
    try:
        return path.relative_to(cwd).as_posix()
    except ValueError:
        pass

    if root_dir is not None:
        try:
            return path.relative_to(root_dir.resolve()).as_posix()
        except ValueError:
            pass

    return path.name


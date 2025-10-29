import io


class OpenedArchiveEntry(io.IOBase):
    """A thin wrapper around an extracted file-like object that keeps the
    archive handle and streams alive.

    This is a generic lifecycle wrapper suitable for any archive format.

    The `extracted` argument is the file-like (readable) object returned by the
    archive library when opening an entry (e.g. ZipFile.open()). The `archive_obj`
    is the archive handle (for example, a ZipFile or TarFile) that must be closed after the
    extracted stream. `reply_stream` is a ReplyStream wrapper with cached headers.
    The `underlying_stream` is the wrapped file-like object (e.g. file_record.open_stream("rb"))
    and is used to read the archive contents and should be closed last.
    `underlying_cm` is the context manager returned by the storage's `open_stream` (so we can call __exit__ on close).
    """

    def __init__(
        self,
        extracted,
        archive_obj,
        reply_stream,
        underlying_stream,
        underlying_cm=None,
    ):
        self._extracted = extracted
        self._archive = archive_obj
        self._reply = reply_stream
        # underlying_stream is the actual file-like object
        self._fp = underlying_stream
        # underlying_cm is the context manager returned by file_record.open_stream
        # (so we can call __exit__ on close). It may be None if the caller
        # provided a raw stream.
        self._fp_cm = underlying_cm

    def readable(self):
        return True

    def writable(self):
        return False

    def seekable(self):
        return hasattr(self._extracted, "seek")

    def read(self, *args, **kwargs):
        return self._extracted.read(*args, **kwargs)

    def readline(self, *args, **kwargs):
        return self._extracted.readline(*args, **kwargs)

    def seek(self, *args, **kwargs):
        return getattr(self._extracted, "seek", lambda *a, **k: None)(*args, **kwargs)

    def tell(self, *args, **kwargs):
        return getattr(self._extracted, "tell", lambda *a, **k: None)(*args, **kwargs)

    def __iter__(self):
        return iter(self._extracted)

    def __next__(self):
        return next(self._extracted)

    def close(self):
        """Close extracted stream, archive object and underlying stream (in that order)."""
        # Close extracted first
        try:
            self._extracted.close()
        except Exception:
            pass

        # Then close the archive handle
        try:
            if self._archive is not None:
                self._archive.close()
        except Exception:
            pass

        # Finally close the underlying storage stream
        try:
            if hasattr(self._fp, "close"):
                self._fp.close()
        except Exception:
            pass

        # If we have a context manager, ensure we exit it so resources are properly released.
        try:
            if self._fp_cm is not None:
                self._fp_cm.__exit__(None, None, None)
        except Exception:
            pass

        # Drop references
        self._extracted = None
        self._archive = None
        self._reply = None
        self._fp = None
        self._fp_cm = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __getattr__(self, name):
        # Forward any unknown attribute to the underlying extracted file
        return getattr(self._extracted, name)

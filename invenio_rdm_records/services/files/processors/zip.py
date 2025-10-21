import base64
import json
import mimetypes
import os
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath

from flask import current_app
from invenio_db import db
from invenio_records_resources.services.files.processors.base import FileProcessor


class ZipProcessor(FileProcessor):
    """Processor for handling ZIP files."""

    def can_process(self, file_record):
        """Determine if this processor can process a given file record."""
        return (
            os.path.splitext(file_record.key)[-1].lower()
            in current_app.config["RECORDS_RESOURCES_ZIP_FORMATS"]
        )

    def process(self, file_record):
        """Process a file."""
        file_record.record.media_files.enabled = True

        if not file_record.record.media_files.bucket:
            file_record.record.media_files.create_bucket()

        listing_file = file_record.record.media_files.get(f"{file_record.key}.listing")

        if listing_file:
            return  # already processed

        toc = self._build_zip_toc(file_record)
        toc_bytes = json.dumps(toc, indent=2).encode("utf-8")
        toc_stream = BytesIO(toc_bytes)

        # add listing here
        try:
            with db.session.begin_nested():
                # Check and create a media file if it doesn't exist
                if listing_file is None:
                    listing_file = file_record.record.media_files.create(
                        f"{file_record.key}.listing",
                        stream=toc_stream,
                    )

                file_record.record.media_files.commit(f"{file_record.key}.listing")

        except Exception:
            # Nested transaction for current file is rolled back
            current_app.logger.exception(
                "Failed to initialize listing",
                extra={
                    "record_id": file_record["id"],
                    "file_key": file_record.key,
                },
            )

    def _build_zip_toc(self, file_record, max_entries=None):
        """Construct hierarchical TOC for ZIP file."""

        def insert_entry(root, parts, info, current_path=""):
            if not parts:
                return

            key = parts[0]
            full_path = f"{current_path}/{key}" if current_path else key

            entry = next((e for e in root if e["key"] == key), None)
            if entry is None:
                is_dir = len(parts) > 1 or info.filename.endswith("/")
                entry = {
                    "key": key,
                    "type": "directory" if is_dir else "file",
                }
                # Initialize entries list for directories
                if entry["type"] == "directory":
                    entry["entries"] = []
                    entry["full_key"] = (
                        full_path  # save full path to calculate relative paths later
                    )

                if entry["type"] == "file":
                    entry["full_key"] = info.filename

                root.append(entry)

            # Recurse into subdirectories
            if len(parts) > 1:
                insert_entry(entry["entries"], parts[1:], info, full_path)
            else:
                if not info.filename.endswith("/"):
                    # update file-specific info
                    entry.update(
                        {
                            "type": "file",
                            "size": info.file_size,
                            "compressed_size": info.compress_size,
                            "mime_type": mimetypes.guess_type(key)[0]
                            or "application/octet-stream",
                            "crc": info.CRC,
                        }
                    )

        toc_root = []
        total_entries = 0
        truncated = False

        with file_record.open_stream("rb") as fp:
            with RecordingStream.open(fp) as recorded_stream:
                with zipfile.ZipFile(recorded_stream) as zf:
                    for info in zf.infolist():
                        if info.filename.endswith("/"):
                            continue
                        parts = list(PurePosixPath(info.filename).parts)
                        insert_entry(toc_root, parts, info)
                        total_entries += 1
                        if max_entries and total_entries >= max_entries:
                            truncated = True
                            break

                # Check if root is present (single top-level directory).
                # If not, create a synthetic root. This ensures consistency and correct extraction
                if len(toc_root) == 1 and toc_root[0]["type"] == "directory":
                    # Root already exists, fine
                    root_entry = toc_root[0]
                else:
                    # Create synthetic root if missing
                    root_name = Path(file_record.key).stem
                    root_entry = {
                        "key": root_name,
                        "type": "directory",
                        "entries": toc_root,
                        "full_key": root_name,
                    }

                return {
                    "entries": [root_entry],
                    "total": total_entries,
                    "truncated": truncated,
                    "toc": recorded_stream.toc(),
                }


class RecordingStream:
    def __init__(self, fp):
        self.fp = fp
        self.min_offset = None
        self.max_offset = None

    @staticmethod
    def open(fp):
        return RecordingStream(fp)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def seek(self, offset, whence=os.SEEK_SET):
        self.fp.seek(offset, whence)

        actual_pos = self.fp.tell()
        if self.min_offset is None or actual_pos < self.min_offset:
            self.min_offset = actual_pos

        if self.max_offset is None or actual_pos > self.max_offset:
            self.max_offset = actual_pos

    def tell(self):
        return self.fp.tell()

    def read(self, size=-1):
        return self.fp.read(size)

    def toc(self):
        if self.min_offset is None:
            return {"content": base64.b64encode(b""), "min_offset": None}

        self.fp.seek(self.min_offset)
        return {
            "content": base64.b64encode(self.fp.read()).decode("utf-8"),
            "min_offset": self.min_offset,
            "max_offset": self.max_offset,
        }

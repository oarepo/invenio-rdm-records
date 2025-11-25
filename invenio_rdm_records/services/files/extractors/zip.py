# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CESNET, a.l.e.
#
# Invenio-RDM-Records is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

import base64
import json
import os
import zipfile
from os.path import basename
from pathlib import PurePosixPath

from flask import Response, current_app, stream_with_context
from invenio_records_resources.services.files.extractors.base import FileExtractor
from invenio_base.urls import invenio_url_for
from zipstream import ZIP_DEFLATED, ZipStream

from .opened_entry import OpenedArchiveEntry
from .reply_stream import ReplyStream


class StreamedZipEntry:
    """Represents a file or directory that can be streamed from a ZIP archive.

    This class handles streaming of both individual files and entire directories:
    - For files: Streams the decompressed content directly
    - For directories: Creates a new ZIP on-the-fly containing all files in that directory
    """

    def __init__(self, file_record, entry, header_pos=0, header=b"", file_size=0):
        self.file_record = file_record
        self.entry = entry
        self.header_pos = header_pos
        self.header = header
        self.file_size = file_size

    def send_file(self):
        """
        Generate a Flask Response that streams the file or directory.

        This method returns different responses depending on the entry type:
        - For files: Streams the decompressed file content
        - For directories: Streams a newly created ZIP containing all files
        """
        # Check if this is a directory
        if self.entry.get("type") == "directory":
            return self._send_directory()

        # Single file extraction
        mime = self.entry.get("mime_type", "application/octet-stream")
        filename = self.entry["full_key"]

        # Open the storage stream now (while request/session still active)
        # otherwise Flask sends HTTP headers but streaming later would fail
        # due to closed SQL session or request context.
        cm = self.file_record.open_stream("rb")
        fp = cm.__enter__()  # get the real file-like object and keep it open

        # For files, stream the single file
        @stream_with_context
        def generate():
            """Generator that streams the file content in chunks."""
            try:
                # Wrap the actual file object in ReplyStream
                with ReplyStream(
                    fp,
                    self.header_pos,
                    self.header,
                    self.file_size,
                ) as reply_stream:
                    # Open as a ZipFile using your wrapper
                    with zipfile.ZipFile(reply_stream) as zf:
                        with zf.open(self.entry["full_key"], "r") as extracted:
                            # Stream the extracted file in chunks
                            chunk_size = 64 * 1024
                            while True:
                                chunk = extracted.read(chunk_size)
                                if not chunk:
                                    break

                                yield chunk
            finally:
                # ensure we close the underlying storage stream
                try:
                    cm.__exit__(None, None, None)
                except Exception:
                    pass

        return Response(
            generate(),
            mimetype=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{basename(filename)}"',
                "Content-Length": str(self.entry["size"]),
            },
        )

    def _send_directory(self):
        """
        Stream an entire directory as a newly created ZIP file.

        This method creates a new ZIP file on-the-fly containing all files from
        the requested directory. It uses zipstream-ng library to avoid buffering the
        entire ZIP in memory.

        """
        dir_name = self.entry["key"]
        zip_filename = f"{dir_name}.zip"

        # Open the storage stream now (while request/session still active)
        # otherwise Flask sends HTTP headers but streaming later would fail
        # due to closed SQL session or request context.
        cm = self.file_record.open_stream("rb")
        fp = cm.__enter__()  # get the real file-like object and keep it open

        @stream_with_context
        def generate_zip():
            """Generator that created ZIP file on the fly."""
            # Create ZipStream object
            zs = ZipStream(compress_type=ZIP_DEFLATED)
            try:
                with ReplyStream(
                    fp,
                    self.header_pos,
                    self.header,
                    self.file_size,
                ) as reply_stream:
                    with zipfile.ZipFile(reply_stream, "r") as source_zip:
                        # Collect all files in this directory
                        files_to_add = self._collect_files(self.entry)

                        for file_info in files_to_add:
                            full_path = file_info["full_key"]

                            # Calculate relative path within the directory
                            relative_path = full_path
                            if full_path.startswith(self.entry["full_key"] + "/"):
                                relative_path = full_path[
                                    len(self.entry["full_key"]) + 1 :
                                ]

                            # Stream file content from source
                            def make_generator(zip_ref, path):
                                def generator():
                                    with zip_ref.open(path, "r") as f:
                                        chunk_size = 64 * 1024
                                        while True:
                                            chunk = f.read(chunk_size)
                                            if not chunk:
                                                break
                                            yield chunk

                                return generator()

                            zs.add(
                                data=make_generator(source_zip, full_path),
                                arcname=relative_path,  # under which name it will be stored in the zip
                            )

                        # Stream the generated ZIP file
                        yield from zs
            finally:
                # ensure we close the underlying storage stream
                try:
                    cm.__exit__(None, None, None)
                except Exception:
                    pass

        # Cant calculate size here. Realistically zipstream can calculate size, but there will be no compression according to the docs
        return Response(
            generate_zip(),
            mimetype="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
        )

    def _collect_files(self, entry):
        """Recursively collect all files in a directory entry."""
        files = []

        if entry.get("type") == "file":
            return [entry]

        for sub_entry in entry.get("entries", []):
            if sub_entry.get("type") == "file":
                files.append(sub_entry)
            elif sub_entry.get("type") == "directory":
                files.extend(self._collect_files(sub_entry))

        return files


class ZipExtractor(FileExtractor):
    """
    Extractor for ZIP files that uses the pre-built table of contents for efficient extraction.

    This extractor leverages the cached TOC created by ZipProcessor to:
    - Quickly locate files without scanning the entire ZIP
    - Stream individual files without loading them fully into memory
    - Create directory ZIPs on-the-fly without buffering in memory
    """

    def can_process(self, file_record):
        """Determine if this extractor can process a given file record."""
        return (
            os.path.splitext(file_record.key)[-1].lower()
            in current_app.config["RECORDS_RESOURCES_ZIP_FORMATS"]
        )

    @staticmethod
    def _find_entry(entries, path_parts):
        """Recursively find entry in TOC based on path parts."""
        if not path_parts:
            return None

        key = path_parts[0]
        for entry in entries:
            if entry["key"] == key:
                if len(path_parts) == 1:
                    return entry
                elif entry.get("entries"):
                    return ZipExtractor._find_entry(entry["entries"], path_parts[1:])
        return None

    def list(self, file_record):
        """Return the cached table of contents for the ZIP file."""
        listing_file = file_record.record.media_files.get(f"{file_record.key}.listing")

        if listing_file:
            with listing_file.file.storage().open("rb") as f:
                listing = json.load(f)
                # Remove the internal TOC data and byte ranges as it's not useful for clients
                listing.pop("toc", None)
                for entry in listing.get("entries", []):
                    for file_entry in entry.get("entries", []):
                        file_entry["links"] = {
                            "content": invenio_url_for("record_files.extract_container_item", pid_value=file_record.record["id"], key=file_record.key, path=file_entry["full_key"]),
                            "preview": invenio_url_for("invenio_app_rdm_records.record_file_preview", pid_value=file_record.record["id"], filename=f"{file_record.key}/container/{file_entry['full_key']}"),
                        }
                        
                return listing
        return {}

    def _get_entry_and_toc(self, file_record, path):
        """Load listing and return (entry, toc).

        Raises FileNotFoundError if listing or entry is not found.
        """
        parts = list(PurePosixPath(path).parts)

        # Load the cached table of contents
        listing_file = file_record.record.media_files.get(f"{file_record.key}.listing")
        if not listing_file:
            raise FileNotFoundError(f"Listing file not found in {file_record.key}.")

        with listing_file.file.storage().open("rb") as f:
            listing = json.load(f)

        # Find the requested entry in the TOC
        entry = self._find_entry(listing.get("entries", []), parts)
        toc = listing.get("toc", {})

        if not entry:
            raise FileNotFoundError(f"Path '{path}' not found in listing.")

        return entry, toc

    def extract(self, file_record, path):
        """Extract a specific file or directory from the file record."""
        # Load entry from listing and its toc
        entry, toc = self._get_entry_and_toc(file_record, path)
        # Create a streamed entry that can generate the response
        return StreamedZipEntry(
            file_record,
            entry,
            toc.get("min_offset", 0),
            base64.b64decode(toc.get("content", b"")),
            toc.get("max_offset", 0),
        )

    def open(self, file_record, path):
        """Open a specific file from the file record and return a
        readable stream that remains open until the caller closes it.

        """
        # Load entry from listing and its toc
        entry, toc = self._get_entry_and_toc(file_record, path)

        # prepare cached header and offsets
        header_pos = toc.get("min_offset", 0)
        header_b64 = toc.get("content", "") or ""
        header = base64.b64decode(header_b64) if header_b64 else b""
        file_size = toc.get("max_offset", 0)

        # file_record.open_stream() returns a context manager. We need the
        # actual underlying file-like object that supports seek/read.
        # Enter the context manually and keep the context manager so we can
        # close it later when the returned object is closed.
        # Otherwise flask already send response but we need the stream open
        fp_cm = file_record.open_stream("rb")
        fp = fp_cm.__enter__()

        # Wrap in our ReplyStream which provides correct seeking/read behavior
        reply_stream = ReplyStream(fp, header_pos, header, file_size)

        # Create ZipFile on top of reply_stream. Keep references so they
        # remain alive while caller uses the returned object.
        zf = zipfile.ZipFile(reply_stream, "r")
        extracted = zf.open(entry["full_key"], "r")

        # Return the OpenedArchiveEntry and keep a reference to the context manager
        # so it can be closed when the user closes the returned object.
        return OpenedArchiveEntry(extracted, zf, reply_stream, fp, fp_cm)

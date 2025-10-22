import base64
import json
import os
import zipfile
from pathlib import PurePosixPath

from flask import Response, current_app
from invenio_records_resources.services.files.extractors.base import FileExtractor
from zipstream import ZIP_DEFLATED, ZipStream


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

        # For files, stream the single file
        def generate():
            """Generator that streams the file content in chunks."""
            # Wrap the underlying file stream in ReplyStream
            with self.file_record.open_stream("rb") as fp:
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

        return Response(
            generate(),
            mimetype=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": self.entry["size"],
                "Content-Digest": f"{self.entry['crc']:08x}",  # ZIP spec stores the CRC-32 as a 32-bit unsigned integer
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

        def generate_zip():
            # Create ZipStream object
            zs = ZipStream(compress_type=ZIP_DEFLATED)

            with self.file_record.open_stream("rb") as fp:
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
                # Remove the internal TOC data (byte ranges) as it's not useful for clients
                listing.pop("toc", None)
                return listing
        return {}

    def extract(self, file_record, path):
        """Extract a specific file or directory from the file record."""
        # extract path parts to find the correct entry later
        parts = list(PurePosixPath(path).parts)

        # Load the cached table of contents
        listing_file = file_record.record.media_files.get(f"{file_record.key}.listing")
        with listing_file.file.storage().open("rb") as f:
            listing = json.load(f)

        # Find the requested entry in the TOC
        entry = self._find_entry(listing.get("entries", []), parts)
        toc = listing.get("toc", {})

        if not entry:
            raise FileNotFoundError(f"Path '{path}' not found in listing.")

        # Create a streamed entry that can generate the response
        return StreamedZipEntry(
            file_record,
            entry,
            toc.get("min_offset", 0),
            base64.b64decode(toc.get("content", b"")),
            toc.get("max_offset", 0),
        )


class ReplyStream:
    def __init__(self, self_stream, header_pos, header, file_size):
        self.self_stream = self_stream
        self.header_pos = header_pos
        self.header = header
        self.header_len = len(header)
        self.current_pos = 0
        self.file_size = file_size

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def seekable(self):
        """Return whether the stream is seekable."""
        return True

    def readable(self):
        """Return whether the stream is readable."""
        return True

    def writable(self):
        """Return whether the stream is writable."""
        return False

    def seek(self, offset, whence=os.SEEK_SET):
        match whence:
            case os.SEEK_SET:
                self.current_pos = offset
            case os.SEEK_CUR:
                self.current_pos = self.current_pos + offset
            case os.SEEK_END:
                self.current_pos = self.file_size + offset
            case _:
                raise ValueError("Invalid value for 'whence'.")

        # Only seek in the underlying stream if we're reading outside the cached header region
        if self.current_pos < self.header_pos:
            # Before the cached region - seek in underlying stream
            self.self_stream.seek(self.current_pos, os.SEEK_SET)
        elif self.current_pos >= self.header_pos + self.header_len:
            # After the cached region - seek in underlying stream
            self.self_stream.seek(self.current_pos, os.SEEK_SET)
        # else: within the cached header region, no need to seek in underlying stream

        return self.current_pos

    def read(self, size=-1):
        if size == -1:
            size = self.file_size - self.current_pos

        if size <= 0:
            return b""

        result = b""
        bytes_to_read = size

        while bytes_to_read > 0:
            # Before cached header
            if self.current_pos < self.header_pos:
                chunk_size = min(bytes_to_read, self.header_pos - self.current_pos)
                chunk = self.self_stream.read(chunk_size)
                result += chunk
                self.current_pos += len(chunk)
                bytes_to_read -= len(chunk)

                if len(chunk) < chunk_size:
                    break

            # Within cached header
            elif self.current_pos < self.header_pos + self.header_len:
                header_offset = self.current_pos - self.header_pos
                chunk_size = min(bytes_to_read, self.header_len - header_offset)
                chunk = self.header[header_offset : header_offset + chunk_size]
                result += chunk
                self.current_pos += len(chunk)
                bytes_to_read -= len(chunk)

            # After cached header
            else:
                chunk = self.self_stream.read(bytes_to_read)
                result += chunk
                self.current_pos += len(chunk)
                bytes_to_read -= len(chunk)

                if len(chunk) == 0:
                    break

        return result

    def tell(self):
        return self.current_pos

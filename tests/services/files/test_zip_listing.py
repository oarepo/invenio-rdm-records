# -*- coding: utf-8 -*-
#
# Copyright (C) 2024 CERN.
#
# Invenio-RDM-Records is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Test RDM records files (metadata)."""

import io
import zipfile
from pathlib import Path

from invenio_rdm_records.proxies import current_rdm_records_service


def test_zip_file_listing(running_app, db, location, minimal_record, identity_simple):
    """Test setting file metadata."""
    data = minimal_record.copy()
    data["files"] = {"enabled": True}
    data["media_files"] = {"enabled": True}
    service = current_rdm_records_service

    file_service = service.files

    # Create
    draft = service.create(identity_simple, data)

    # Initialize files and add valid metadata
    metadata = {
        "type": "zip",
    }
    service.draft_files.init_files(
        identity_simple,
        draft.id,
        data=[{"key": "test.zip", "metadata": metadata, "access": {"hidden": False}}],
    )

    zip_path = Path(__file__).parent.parent / "data" / "test_zip.zip"
    with open(zip_path, "rb") as f:
        service.draft_files.set_file_content(identity_simple, draft.id, "test.zip", f)

    service.draft_files.commit_file(identity_simple, draft.id, "test.zip")

    # Publish the record
    record = service.publish(identity_simple, draft.id)

    # Get file metadata
    listing = file_service.get_container_listing(identity_simple, draft.id, "test.zip")
    assert listing.to_dict() == {
        "entries": [
            {
                "key": "test_zip",
                "type": "directory",
                "entries": [
                    {
                        "key": "test1.txt",
                        "type": "file",
                        "full_key": "test_zip/test1.txt",
                        "size": 12,
                        "compressed_size": 14,
                        "mime_type": "text/plain",
                    }
                ],
            }
        ],
        "total": 1,
        "truncated": False,
    }


def test_zip_file_extraction(
    running_app, db, location, minimal_record, identity_simple
):
    """Test setting file metadata."""
    data = minimal_record.copy()
    data["files"] = {"enabled": True}
    data["media_files"] = {"enabled": True}
    service = current_rdm_records_service

    file_service = service.files

    # Create
    draft = service.create(identity_simple, data)

    # Initialize files and add valid metadata
    metadata = {
        "type": "zip",
    }
    service.draft_files.init_files(
        identity_simple,
        draft.id,
        data=[{"key": "test.zip", "metadata": metadata, "access": {"hidden": False}}],
    )

    zip_path = Path(__file__).parent.parent / "data" / "test_zip.zip"
    with open(zip_path, "rb") as f:
        service.draft_files.set_file_content(identity_simple, draft.id, "test.zip", f)

    service.draft_files.commit_file(identity_simple, draft.id, "test.zip")

    # Publish the record
    record = service.publish(identity_simple, draft.id)

    extracted = file_service.extract_from_container(
        identity_simple, draft.id, "test.zip", "test_zip/test1.txt"
    )
    res = extracted.send_file()
    data = b"".join(res.response)
    assert res.mimetype == "text/plain"
    assert len(data) == 12
    assert data == b"Hello World\n"


def test_zip_folder_extraction(
    running_app, db, location, minimal_record, identity_simple
):
    """Test setting file metadata."""
    data = minimal_record.copy()
    data["files"] = {"enabled": True}
    data["media_files"] = {"enabled": True}
    service = current_rdm_records_service

    file_service = service.files

    # Create
    draft = service.create(identity_simple, data)

    # Initialize files and add valid metadata
    metadata = {
        "type": "zip",
    }
    service.draft_files.init_files(
        identity_simple,
        draft.id,
        data=[
            {
                "key": "test_directory_zip.zip",
                "metadata": metadata,
                "access": {"hidden": False},
            }
        ],
    )

    zip_path = Path(__file__).parent.parent / "data" / "test_directory_zip.zip"
    with open(zip_path, "rb") as f:
        service.draft_files.set_file_content(
            identity_simple, draft.id, "test_directory_zip.zip", f
        )

    service.draft_files.commit_file(identity_simple, draft.id, "test_directory_zip.zip")

    # Publish the record
    record = service.publish(identity_simple, draft.id)

    extracted = file_service.extract_from_container(
        identity_simple,
        draft.id,
        "test_directory_zip.zip",
        "test_directory_zip/directory1",
    )
    res = extracted.send_file()
    data = b"".join(res.response)
    zip_bytes = io.BytesIO(data)
    with zipfile.ZipFile(zip_bytes, "r") as zip_ref:
        namelist = zip_ref.namelist()
        assert namelist == ["directory1-file1.txt", "directory1-file2.txt"]

        with zip_ref.open("directory1-file1.txt") as f:
            content = f.read().decode("utf-8")
            assert content == "directory1-file1\n"

        with zip_ref.open("directory1-file2.txt") as f:
            content = f.read().decode("utf-8")
            assert content == "directory1-file2\n"

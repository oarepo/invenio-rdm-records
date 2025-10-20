# -*- coding: utf-8 -*-
#
# Copyright (C) 2023-2024 CERN.
#
# Invenio-RDM-Records is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""File Service API."""

from invenio_rdm_records.services.files.processors import RecordingStream, ZipProcessor

__all__ = ("RecordingStream", "ZipProcessor")

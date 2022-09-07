# -*- coding: utf-8 -*-
#
# Copyright (C) 2022 CERN.
#
# invenio-administration is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more
# details.

"""Invenio administration OAI-PMH view module."""
from invenio_administration.views.base import AdminResourceListView,\
    AdminResourceDetailView, AdminResourceEditView, AdminResourceCreateView


class OaiPmhListView(AdminResourceListView):

    api_endpoint = "/oaipmh/sets"
    name = "OAI-PMH"
    resource_config = "oaipmh_server_resource"
    search_request_headers = {"Accept": "application/json"}
    title = "OAI-PMH Sets"
    category = "Site management"
    pid_path = "id"
    icon = "exchange"

    # OAI sets are not searchable in ES
    display_search = True
    display_delete = True
    display_edit = True

    item_field_list = {
        "spec": {
            "text": "Set spec",
            "order": 1
        },
        "name": {
            "text": "Set name",
            "order": 2
        },
        "search_pattern": {
            "text": "Search query",
            "order": 3
        },
        "created": {
            "text": "Created",
            "order": 5,
        },
        "updated": {
            "text": "Updated",
            "order": 6,
        },
    }

    search_config_name = "RDM_OAI_PMH_SEARCH"
    search_facets_config_name = "RDM_OAI_PMH_FACETS"
    search_sort_config_name = "RDM_OAI_PMH_SORT_OPTIONS"

    create_view_name = "oaipmh_create"
    resource_name = "name"


class OaiPmhEditView(AdminResourceEditView):

    name = "oaipmh_edit"
    url = "/oai-pmh/<pid_value>/edit"
    resource_config = "oaipmh_server_resource"
    pid_path = "id"
    api_endpoint = "/oaipmh/sets"
    title = "Edit OAI-PMH set"

    list_view_name = "OAI-PMH"

    form_fields = {
        "name": {"order": 2, "text": "Set name"},
        "spec": {"order": 3, "text": "Set spec"},
        "search_pattern": {"order": 4, "text": "Search query"},
        "created": {"order": 5},
        "updated": {"order": 6},
    }


class OaiPmhCreateView(AdminResourceCreateView):

    name = "oaipmh_create"
    url = "/oai-pmh/create"
    resource_config = "oaipmh_server_resource"
    pid_path = "id"
    api_endpoint = "/oaipmh/sets"
    title = "Create OAI-PMH set"

    list_view_name = "OAI-PMH"

    form_fields = {
        "name": {"order": 1, "text": "Set name"},
        "spec": {"order": 2, "text": "Set spec"},
        "search_pattern": {"order": 3, "text": "Search query"},
    }


class OaiPmhDetailView(AdminResourceDetailView):

    url = "/oai-pmh/<pid_value>"
    api_endpoint = "/oaipmh/sets"
    search_request_headers = {"Accept": "application/json"}
    name = "OAI-PMH details"
    resource_config = "oaipmh_server_resource"
    title = "OAI-PMH Details"

    template = "invenio_rdm_records/oai-details.html"
    display_delete = True
    display_edit = True

    list_view_name = "OAI-PMH"
    pid_path = "id"

    item_field_list = {
        "name": {
            "text": "Set name",
            "order": 2
        },
        "spec": {
            "text": "Set Spec",
            "order": 3
        },
        "search_pattern": {
            "text": "Search query",
            "order": 4
        },
        "created": {
            "text": "Created",
            "order": 6
        },
        "updated": {
            "text": "Updated",
            "order": 5
        },
    }
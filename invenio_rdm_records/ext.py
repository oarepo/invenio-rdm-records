# -*- coding: utf-8 -*-
#
# Copyright (C) 2019-2024 CERN.
# Copyright (C) 2019-2021 Northwestern University.
# Copyright (C) 2022 Universität Hamburg.
# Copyright (C) 2023-2024 Graz University of Technology.
# Copyright (C) 2023 TU Wien.
# Copyright (C) 2025 KTH Royal Institute of Technology.
#
# Invenio-RDM-Records is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""DataCite-based data model for Invenio."""

from warnings import warn

from flask import Blueprint
from flask_iiif import IIIF
from flask_principal import identity_loaded
from invenio_base.utils import obj_or_import_string
from invenio_records_resources.resources.files import FileResource

from . import config
from .oaiserver.resources.config import OAIPMHServerResourceConfig
from .oaiserver.resources.resources import OAIPMHServerResource
from .oaiserver.services.config import OAIPMHServerServiceConfig
from .oaiserver.services.services import OAIPMHServerService
from .resources import (
    IIIFResource,
    IIIFResourceConfig,
    RDMCommunityRecordsResource,
    RDMCommunityRecordsResourceConfig,
    RDMDraftFilesResourceConfig,
    RDMGrantGroupAccessResourceConfig,
    RDMGrantsAccessResource,
    RDMGrantUserAccessResourceConfig,
    RDMParentGrantsResource,
    RDMParentGrantsResourceConfig,
    RDMParentRecordLinksResource,
    RDMParentRecordLinksResourceConfig,
    RDMRecordCommunitiesResourceConfig,
    RDMRecordFilesResourceConfig,
    RDMRecordRequestsResourceConfig,
    RDMRecordResource,
    RDMRecordResourceConfig,
)
from .resources.config import (
    RDMDraftMediaFilesResourceConfig,
    RDMRecordMediaFilesResourceConfig,
)
from .resources.resources import RDMRecordCommunitiesResource, RDMRecordRequestsResource
from .services import (
    CommunityRecordsService,
    IIIFService,
    RDMCommunityRecordsConfig,
    RDMFileDraftServiceConfig,
    RDMFileRecordServiceConfig,
    RDMRecordCommunitiesConfig,
    RDMRecordRequestsConfig,
    RDMRecordService,
    RDMRecordServiceConfig,
    RecordAccessService,
    RecordRequestsService,
)
from .services.communities.service import RecordCommunitiesService
from .services.community_inclusion.service import CommunityInclusionService
from .services.config import (
    RDMMediaFileDraftServiceConfig,
    RDMMediaFileRecordServiceConfig,
    RDMRecordMediaFilesServiceConfig,
)
from .services.files import RDMFileService
from .services.pids import PIDManager, PIDsService
from .services.review.service import ReviewService
from .utils import verify_token


@identity_loaded.connect
def on_identity_loaded(_, identity):
    """Add secret link token or resource access token need to the freshly loaded Identity."""
    verify_token(identity)


blueprint = Blueprint(
    "invenio_rdm_records",
    __name__,
    template_folder="templates",
    static_folder="static",
)


class InvenioRDMRecords(object):
    """Invenio-RDM-Records extension."""

    def __init__(self, app=None):
        """Extension initialization."""
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Flask application initialization."""
        self.init_config(app)
        self.init_services(app)
        self.init_resource(app)
        app.extensions["invenio-rdm-records"] = self
        app.register_blueprint(blueprint)
        # Load flask IIIF
        IIIF(app)

    def init_config(self, app):
        """Initialize configuration."""
        supported_configurations = [
            "FILES_REST_PERMISSION_FACTORY",
            "RECORDS_REFRESOLVER_CLS",
            "RECORDS_REFRESOLVER_STORE",
            "RECORDS_UI_ENDPOINTS",
            "THEME_SITEURL",
        ]

        for k in dir(config):
            if (
                k in supported_configurations
                or k.startswith("RDM_")
                or k.startswith("DATACITE_")
                # TODO: This can likely be moved to a separate module
                or k.startswith("IIIF_TILES_")
            ):
                app.config.setdefault(k, getattr(config, k))

        # set default communities namespaces to the global RDM_NAMESPACES
        if not app.config.get("COMMUNITIES_NAMESPACES"):
            app.config["COMMUNITIES_NAMESPACES"] = app.config["RDM_NAMESPACES"]

        if not app.config.get("RDM_FILES_DEFAULT_QUOTA_SIZE"):
            warn(
                "The configuration value 'RDM_FILES_DEFAULT_QUOTA_SIZE' is not set. In future, please set it "
                "explicitly to define your quota size, or be aware that the default value used i.e. FILES_REST_DEFAULT_QUOTA_SIZE will be 10 * (10**9) (10 GB).",
                DeprecationWarning,
            )
        if not app.config.get("RDM_FILES_DEFAULT_MAX_FILE_SIZE"):
            warn(
                "The configuration value 'RDM_FILES_DEFAULT_MAX_FILE_SIZE' is not set. In future, please set it "
                "explicitly to define your max file size, or be aware that the default value used i.e. FILES_REST_DEFAULT_MAX_FILE_SIZE will be 10 * (10**9) (10 GB).",
                DeprecationWarning,
            )
        if app.config.get("APP_RDM_DEPOSIT_FORM_PUBLISH_MODAL_EXTRA"):
            warn(
                "The configuration value 'APP_RDM_DEPOSIT_FORM_PUBLISH_MODAL_EXTRA' is deprecated and will be removed in a future release. Use Overridables for "
                "adding extra content to the publish modal instead.",
                DeprecationWarning,
            )

        self.fix_datacite_configs(app)

    def service_configs(self, app):
        """Customized service configs."""

        class ServiceConfigs:
            record = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_SERVICE_CONFIG_CLASS", RDMRecordServiceConfig
                )
            ).build(app)
            record_with_media_files = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_MEDIA_FILE_SERVICE_CONFIG_CLASS",
                    RDMRecordMediaFilesServiceConfig,
                )
            ).build(app)
            file = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_FILE_RECORD_SERVICE_CONFIG_CLASS",
                    RDMFileRecordServiceConfig,
                )
            ).build(app)
            file_draft = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_FILE_DRAFT_SERVICE_CONFIG_CLASS",
                    RDMFileDraftServiceConfig,
                )
            ).build(app)
            media_file = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_MEDIA_FILE_RECORD_SERVICE_CONFIG_CLASS",
                    RDMMediaFileRecordServiceConfig,
                )
            ).build(app)
            media_file_draft = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_MEDIA_FILE_DRAFT_SERVICE_CONFIG_CLASS",
                    RDMMediaFileDraftServiceConfig,
                )
            ).build(app)
            oaipmh_server = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_OAIPMH_SERVER_SERVICE_CONFIG_CLASS",
                    OAIPMHServerServiceConfig,
                )
            )
            record_communities = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_COMMUNITIES_CONFIG_CLASS", RDMRecordCommunitiesConfig
                )
            ).build(app)
            community_records = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_COMMUNITY_RECORDS_CONFIG_CLASS",
                    RDMCommunityRecordsConfig,
                )
            ).build(app)
            record_requests = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_REQUESTS_CONFIG_CLASS", RDMRecordRequestsConfig
                )
            ).build(app)

        return ServiceConfigs

    def service_classes(self, app):
        """Customized service classes."""

        class ServiceClasses:
            record = obj_or_import_string(
                app.config.get("RDM_RECORDS_SERVICE_CLASS", RDMRecordService)
            )
            record_file = obj_or_import_string(
                app.config.get("RDM_RECORDS_FILE_SERVICE_CLASS", RDMFileService)
            )
            record_access = obj_or_import_string(
                app.config.get("RDM_RECORDS_ACCESS_SERVICE_CLASS", RecordAccessService)
            )
            record_pids = obj_or_import_string(
                app.config.get("RDM_RECORDS_PIDS_SERVICE_CLASS", PIDsService)
            )
            record_review = obj_or_import_string(
                app.config.get("RDM_RECORDS_REVIEW_SERVICE_CLASS", ReviewService)
            )
            iiif = obj_or_import_string(
                app.config.get("RDM_RECORDS_IIIF_SERVICE_CLASS", IIIFService)
            )
            record_communities = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_COMMUNITIES_SERVICE_CLASS", RecordCommunitiesService
                )
            )
            community_records = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_COMMUNITY_RECORDS_SERVICE_CLASS",
                    CommunityRecordsService,
                )
            )
            community_inclusion = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_COMMUNITY_INCLUSION_SERVICE_CLASS",
                    CommunityInclusionService,
                )
            )
            record_requests = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_REQUESTS_SERVICE_CLASS", RecordRequestsService
                )
            )
            oaipmh_server = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_OAIPMH_SERVER_SERVICE_CLASS", OAIPMHServerService
                )
            )

        return ServiceClasses

    def init_services(self, app):
        """Initialize services."""
        service_configs = self.service_configs(app)
        service_classes = self.service_classes(app)
        # Services
        self.records_service = service_classes.record(
            service_configs.record,
            files_service=service_classes.record_file(service_configs.file),
            draft_files_service=service_classes.record_file(service_configs.file_draft),
            access_service=service_classes.record_access(service_configs.record),
            pids_service=service_classes.record_pids(
                service_configs.record, PIDManager
            ),
            review_service=service_classes.record_review(service_configs.record),
        )

        self.records_media_files_service = service_classes.record(
            service_configs.record_with_media_files,
            files_service=service_classes.record_file(service_configs.media_file),
            draft_files_service=service_classes.record_file(
                service_configs.media_file_draft
            ),
            pids_service=service_classes.record_pids(
                service_configs.record, PIDManager
            ),
        )

        self.iiif_service = service_classes.iiif(
            records_service=self.records_service, config=None
        )

        self.record_communities_service = service_classes.record_communities(
            config=service_configs.record_communities
        )

        self.community_records_service = service_classes.community_records(
            config=service_configs.community_records
        )

        self.community_inclusion_service = service_classes.community_inclusion()

        self.record_requests_service = service_classes.record_requests(
            config=service_configs.record_requests
        )

        self.oaipmh_server_service = service_classes.oaipmh_server(
            config=service_configs.oaipmh_server
        )

    def resource_configs(self, app):
        """Customized service configs."""

        class ResourceConfigs:
            record = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_RESOURCE_CONFIG_CLASS", RDMRecordResourceConfig
                )
            ).build(app)
            record_files = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_FILES_RESOURCE_CONFIG_CLASS",
                    RDMRecordFilesResourceConfig,
                )
            ).build(app)
            draft_files = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_DRAFT_FILES_RESOURCE_CONFIG_CLASS",
                    RDMDraftFilesResourceConfig,
                )
            ).build(app)
            record_media_files = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_MEDIA_FILES_RESOURCE_CONFIG_CLASS",
                    RDMRecordMediaFilesResourceConfig,
                )
            ).build(app)
            draft_media_files = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_DRAFT_MEDIA_FILES_RESOURCE_CONFIG_CLASS",
                    RDMDraftMediaFilesResourceConfig,
                )
            ).build(app)
            parent_record_links = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_PARENT_RECORD_LINKS_RESOURCE_CONFIG_CLASS",
                    RDMParentRecordLinksResourceConfig,
                )
            ).build(app)
            parent_grants = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_PARENT_GRANTS_RESOURCE_CONFIG_CLASS",
                    RDMParentGrantsResourceConfig,
                )
            ).build(app)
            grant_user_access = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_GRANT_USER_ACCESS_RESOURCE_CONFIG_CLASS",
                    RDMGrantUserAccessResourceConfig,
                )
            ).build(app)
            grant_group_access = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_GRANT_GROUP_ACCESS_RESOURCE_CONFIG_CLASS",
                    RDMGrantGroupAccessResourceConfig,
                )
            ).build(app)
            record_communities = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_COMMUNITIES_RESOURCE_CONFIG_CLASS",
                    RDMRecordCommunitiesResourceConfig,
                )
            ).build(app)
            record_requests = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_REQUESTS_RESOURCE_CONFIG_CLASS",
                    RDMRecordRequestsResourceConfig,
                )
            ).build(app)
            community_records = obj_or_import_string(
                app.config.get(
                    "RDM_COMMUNITY_RECORDS_RESOURCE_CONFIG_CLASS",
                    RDMCommunityRecordsResourceConfig,
                )
            ).build(app)
            oaipmh_server = obj_or_import_string(
                app.config.get(
                    "RDM_OAIPMH_SERVER_RESOURCE_CONFIG_CLASS",
                    OAIPMHServerResourceConfig,
                )
            ).build(app)
            iiif = obj_or_import_string(
                app.config.get("RDM_IIIF_RESOURCE_CONFIG_CLASS", IIIFResourceConfig)
            ).build(app)

        return ResourceConfigs

    def resource_classes(self, app):
        class ResourceClasses:
            record = obj_or_import_string(
                app.config.get("RDM_RECORDS_RESOURCE_CLASS", RDMRecordResource)
            )
            record_files = obj_or_import_string(
                app.config.get("RDM_RECORDS_FILES_RESOURCE_CLASS", FileResource)
            )
            record_media_files = obj_or_import_string(
                app.config.get("RDM_RECORDS_MEDIA_FILES_RESOURCE_CLASS", FileResource)
            )
            parent_record_links = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_PARENT_RECORD_LINKS_RESOURCE_CLASS",
                    RDMParentRecordLinksResource,
                )
            )
            parent_grants = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_PARENT_GRANTS_RESOURCE_CLASS",
                    RDMParentGrantsResource,
                )
            )
            grant_access = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_GRANT_ACCESS_RESOURCE_CLASS",
                    RDMGrantsAccessResource,
                )
            )
            record_communities = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_COMMUNITIES_RESOURCE_CLASS",
                    RDMRecordCommunitiesResource,
                )
            )
            record_requests = obj_or_import_string(
                app.config.get(
                    "RDM_RECORDS_REQUESTS_RESOURCE_CLASS",
                    RDMRecordRequestsResource,
                )
            )
            community_records = obj_or_import_string(
                app.config.get(
                    "RDM_COMMUNITY_RECORDS_RESOURCE_CLASS",
                    RDMCommunityRecordsResource,
                )
            )
            oaipmh_server = obj_or_import_string(
                app.config.get("RDM_OAIPMH_SERVER_RESOURCE_CLASS", OAIPMHServerResource)
            )
            iiif = obj_or_import_string(
                app.config.get("RDM_IIIF_RESOURCE_CLASS", IIIFResource)
            )

        return ResourceClasses

    def init_resource(self, app):
        """Initialize resources."""
        resource_configs = self.resource_configs(app)
        resource_classes = self.resource_classes(app)

        self.records_resource = resource_classes.record(
            service=self.records_service,
            config=resource_configs.record,
        )

        # Record files resource
        self.record_files_resource = resource_classes.record_files(
            service=self.records_service.files,
            config=resource_configs.record_files,
        )

        # Draft files resource
        self.draft_files_resource = resource_classes.record_files(
            service=self.records_service.draft_files,
            config=resource_configs.draft_files,
        )

        self.record_media_files_resource = resource_classes.record_media_files(
            service=self.records_media_files_service.files,
            config=resource_configs.record_media_files,
        )

        # Draft files resource
        self.draft_media_files_resource = resource_classes.record_media_files(
            service=self.records_media_files_service.draft_files,
            config=resource_configs.draft_media_files,
        )

        # Parent Records
        self.parent_record_links_resource = resource_classes.parent_record_links(
            service=self.records_service,
            config=resource_configs.parent_record_links,
        )

        self.parent_grants_resource = resource_classes.parent_grants(
            service=self.records_service,
            config=resource_configs.parent_grants,
        )

        self.grant_user_access_resource = resource_classes.grant_access(
            service=self.records_service,
            config=resource_configs.grant_user_access,
        )

        self.grant_group_access_resource = resource_classes.grant_access(
            service=self.records_service,
            config=resource_configs.grant_group_access,
        )

        # Record's communities
        self.record_communities_resource = resource_classes.record_communities(
            service=self.record_communities_service,
            config=resource_configs.record_communities,
        )

        self.record_requests_resource = resource_classes.record_requests(
            service=self.record_requests_service,
            config=resource_configs.record_requests,
        )

        # Community's records
        self.community_records_resource = resource_classes.community_records(
            service=self.community_records_service,
            config=resource_configs.community_records,
        )

        # OAI-PMH
        self.oaipmh_server_resource = resource_classes.oaipmh_server(
            service=self.oaipmh_server_service,
            config=resource_configs.oaipmh_server,
        )

        # IIIF
        self.iiif_resource = resource_classes.iiif(
            service=self.iiif_service,
            config=resource_configs.iiif,
        )

    def fix_datacite_configs(self, app):
        """Make sure that the DataCite config items are strings."""
        datacite_config_items = [
            "DATACITE_USERNAME",
            "DATACITE_PASSWORD",
            "DATACITE_FORMAT",
            "DATACITE_PREFIX",
        ]
        for config_item in datacite_config_items:
            if config_item in app.config:
                app.config[config_item] = str(app.config[config_item])


def finalize_app(app):
    """Finalize app.

    NOTE: replace former @record_once decorator
    """
    init(app)


def api_finalize_app(app):
    """Finalize app for api.

    NOTE: replace former @record_once decorator
    """
    init(app)


def init(app):
    """Init app."""
    # Register services - cannot be done in extension because
    # Invenio-Records-Resources might not have been initialized.
    sregistry = app.extensions["invenio-records-resources"].registry
    ext = app.extensions["invenio-rdm-records"]
    sregistry.register(ext.records_service, service_id="records")
    sregistry.register(ext.records_service.files, service_id="files")
    sregistry.register(ext.records_service.draft_files, service_id="draft-files")
    sregistry.register(ext.records_media_files_service, service_id="record-media-files")
    sregistry.register(ext.records_media_files_service.files, service_id="media-files")
    sregistry.register(
        ext.records_media_files_service.draft_files, service_id="draft-media-files"
    )
    sregistry.register(ext.oaipmh_server_service, service_id="oaipmh-server")
    sregistry.register(ext.iiif_service, service_id="rdm-iiif")
    # Register indexers
    iregistry = app.extensions["invenio-indexer"].registry
    iregistry.register(ext.records_service.indexer, indexer_id="records")
    iregistry.register(ext.records_service.draft_indexer, indexer_id="records-drafts")

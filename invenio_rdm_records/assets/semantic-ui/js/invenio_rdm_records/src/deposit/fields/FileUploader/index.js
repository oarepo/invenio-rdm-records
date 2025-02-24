// This file is part of Invenio-RDM-Records
// Copyright (C) 2020-2023 CERN.
// Copyright (C) 2020-2022 Northwestern University.
//
// Invenio-RDM-Records is free software; you can redistribute it and/or modify it
// under the terms of the MIT License; see LICENSE file for more details.

import { connect } from "react-redux";
import {
  deleteFile,
  importParentFiles,
  initializeFileUpload,
  uploadFile,
  uploadFiles,
} from "../../state/actions";
import { FileUploaderComponent } from "./FileUploader";

const mapStateToProps = (state) => {
  const { links, entries } = state.files;
  return {
    files: entries,
    links,
    record: state.deposit.record,
    config: state.deposit.config,
    permissions: state.deposit.permissions,
    isFileImportInProgress: state.files.isFileImportInProgress,
    hasParentRecord: Boolean(
      state.deposit.record?.versions?.index && state.deposit.record?.versions?.index > 1
    ),
  };
};

const mapDispatchToProps = (dispatch) => ({
  initializeFileUpload: (draft, file) => dispatch(initializeFileUpload(draft, file)),
  uploadFile: (draft, file) => dispatch(uploadFile(draft, file)),
  uploadFiles: (draft, files) => dispatch(uploadFiles(draft, files)),
  importParentFiles: () => dispatch(importParentFiles()),
  deleteFile: (file, options) => dispatch(deleteFile(file, options)),
});

export const FileUploader = connect(
  mapStateToProps,
  mapDispatchToProps
)(FileUploaderComponent);

export { FileUploaderArea, FilesListTable } from "./FileUploaderArea";
export { FileUploaderToolbar } from "./FileUploaderToolbar";
export * from "./hooks";

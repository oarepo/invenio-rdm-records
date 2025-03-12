// This file is part of Invenio-RDM-Records
// Copyright (C) 2020-2023 CERN.
// Copyright (C) 2020-2022 Northwestern University.
//
// Invenio-RDM-Records is free software; you can redistribute it and/or modify it
// under the terms of the MIT License; see LICENSE file for more details.

import axios from "axios";
import _get from "lodash/get";

const BASE_HEADERS = {
  "json": { "Content-Type": "application/json" },
  "vnd+json": {
    "Content-Type": "application/json",
    "Accept": "application/vnd.inveniordm.v1+json",
  },
  "octet-stream": { "Content-Type": "application/octet-stream" },
};

class UnsupportedTransferTypeError extends Error {
  file;
  transferType;
  supportedTypes;
  isUserFacing;

  constructor(message, opts) {
    super(message);
    this.isUserFacing = opts?.isUserFacing ?? false;
    if (opts?.file) {
      this.file = opts.file;
    }
    if (opts?.transferType) {
      this.transferType = opts.transferType;
    }
    if (opts?.supportedTypes) {
      this.supportedTypes = opts.supportedTypes;
    }
  }
}

/**
 * API client response.
 */
export class DepositApiClientResponse {
  constructor(data, errors) {
    this.data = data;
    this.errors = errors;
  }
}

export class DepositApiClient {
  /* eslint-disable no-unused-vars */
  constructor(additionalApiConfig, createDraftURL, recordSerializer) {
    if (this.constructor === DepositApiClient) {
      throw new Error("Abstract");
    }

    const additionalHeaders = _get(additionalApiConfig, "headers");
    this.apiHeaders = Object.assign({}, BASE_HEADERS, additionalHeaders);

    this.apiConfig = {
      withCredentials: true,
      xsrfCookieName: "csrftoken",
      xsrfHeaderName: "X-CSRFToken",
      headers: this.apiHeaders["vnd+json"],
    };
    this.axiosWithConfig = axios.create(this.apiConfig);
    this.cancelToken = axios.CancelToken;
  }

  async createDraft(draft) {
    throw new Error("Not implemented.");
  }

  async saveDraft(draft, draftLinks) {
    throw new Error("Not implemented.");
  }

  async publishDraft(draftLinks) {
    throw new Error("Not implemented.");
  }

  async deleteDraft(draftLinks) {
    throw new Error("Not implemented.");
  }

  async reservePID(draftLinks, pidType) {
    throw new Error("Not implemented.");
  }

  async discardPID(draftLinks, pidType) {
    throw new Error("Not implemented.");
  }

  async createOrUpdateReview(draftLinks, communityId) {
    throw new Error("Not implemented.");
  }

  async deleteReview(draftLinks) {
    throw new Error("Not implemented.");
  }

  async submitReview(draftLinks) {
    throw new Error("Not implemented.");
  }
}

/**
 * API Client for deposits.
 */
export class RDMDepositApiClient extends DepositApiClient {
  constructor(additionalApiConfig, createDraftURL, recordSerializer) {
    super(additionalApiConfig);
    this.createDraftURL = createDraftURL;
    this.recordSerializer = recordSerializer;
  }

  async _createResponse(axiosRequest) {
    try {
      const response = await axiosRequest();
      const data = this.recordSerializer.deserialize(response.data || {});
      const errors = this.recordSerializer.deserializeErrors(
        response.data.errors || []
      );
      return new DepositApiClientResponse(data, errors);
    } catch (error) {
      let errorData = error.response.data;
      const errors = this.recordSerializer.deserializeErrors(
        error.response.data.errors || []
      );
      // this is to serialize raised error from the backend on publish
      if (errors) errorData = errors;
      throw new DepositApiClientResponse({}, errorData);
    }
  }

  /**
   * Calls the API to create a new draft.
   *
   * @param {object} draft - Serialized draft
   */
  async createDraft(draft) {
    const payload = this.recordSerializer.serialize(draft);
    return this._createResponse(() =>
      this.axiosWithConfig.post(this.createDraftURL, payload, {
        params: { expand: 1 },
      })
    );
  }

  /**
   * Calls the API to read a pre-existing draft.
   *
   * @param {object} draftLinks - the draft links object
   */
  async readDraft(draftLinks) {
    return this._createResponse(() =>
      this.axiosWithConfig.get(draftLinks.self, {
        params: { expand: 1 },
      })
    );
  }

  /**
   * Calls the API to save a pre-existing draft.
   *
   * @param {object} draft - the draft payload
   */
  async saveDraft(draft, draftLinks) {
    const payload = this.recordSerializer.serialize(draft);
    return this._createResponse(() =>
      this.axiosWithConfig.put(draftLinks.self, payload, {
        params: { expand: 1 },
      })
    );
  }

  /**
   * Publishes the draft by calling its publish link.
   *
   * @param {string} draftLinks - the URL to publish the draft
   */
  async publishDraft(draftLinks) {
    return this._createResponse(() =>
      this.axiosWithConfig.post(draftLinks.publish, {}, { params: { expand: 1 } })
    );
  }

  /**
   * Deletes the draft by calling DELETE on its self link.
   *
   * @param {string} draftLinks - the URL to delete the draft
   */
  async deleteDraft(draftLinks) {
    return this._createResponse(() => this.axiosWithConfig.delete(draftLinks.self, {}));
  }

  /**
   * Calls the API to reserve a PID.
   *
   */
  async reservePID(draftLinks, pidType) {
    return this._createResponse(() => {
      const linkName = `reserve_${pidType}`;
      const link = draftLinks[linkName];
      return this.axiosWithConfig.post(
        link,
        {},
        {
          params: { expand: 1 },
        }
      );
    });
  }

  /**
   * Calls the API to discard a previously reserved PID.
   *
   */
  async discardPID(draftLinks, pidType) {
    return this._createResponse(() => {
      const linkName = `reserve_${pidType}`;
      const link = draftLinks[linkName];
      return this.axiosWithConfig.delete(link, {
        params: { expand: 1 },
      });
    });
  }

  /**
   * Creates a review request in initial state for draft by calling its
   * review link.
   *
   * @param {object} draftLinks - the draft links object
   */
  async createOrUpdateReview(draftLinks, communityId) {
    return this._createResponse(() =>
      this.axiosWithConfig.put(draftLinks.review, {
        receiver: {
          community: communityId,
        },
        type: "community-submission",
      })
    );
  }

  /**
   * Deletes a review request associated with the draft using its review link.
   *
   * @param {object} draftLinks - the draft links object
   */
  async deleteReview(draftLinks) {
    return this._createResponse(() =>
      this.axiosWithConfig.delete(draftLinks.review, {})
    );
  }

  /**
   * Submits the draft for review by calling its submit-review link.
   *
   * @param {object} draftLinks - the draft links object
   */
  async submitReview(draftLinks, reviewComment) {
    return this._createResponse(() => {
      const payload = reviewComment
        ? {
            payload: {
              content: reviewComment,
              format: "html",
            },
          }
        : {};
      return this.axiosWithConfig.post(draftLinks["submit-review"], payload);
    });
  }

  /**
   * Cancels the review for the draft by calling its cancel link.
   *
   * @param reviewLinks
   * @param reviewComment
   */
  async cancelReview(reviewLinks, reviewComment) {
    return this.axiosWithConfig.post(
      reviewLinks.actions.cancel,
      reviewComment
        ? {
            payload: {
              content: reviewComment,
              format: "html",
            },
          }
        : {}
    );
  }
}

/**
 * Abstract class for File API Client.
 * @constructor
 * @abstract
 */
export class DepositFileApiClient {
  constructor(additionalApiConfig) {
    if (this.constructor === DepositFileApiClient) {
      throw new Error("Abstract");
    }
    const additionalHeaders = _get(additionalApiConfig, "headers", {});
    this.apiHeaders = Object.assign({}, BASE_HEADERS, additionalHeaders);

    const apiConfig = {
      withCredentials: true,
      xsrfCookieName: "csrftoken",
      xsrfHeaderName: "X-CSRFToken",
      headers: this.apiHeaders["vnd+json"],
    };
    this.axiosWithConfig = axios.create(apiConfig);
  }

  isCancelled(error) {
    return axios.isCancel(error);
  }

  initializeFileUpload(initializeUploadUrl, filename) {
    throw new Error("Not implemented.");
  }

  uploadFile(uploadUrl, file, onUploadProgress, cancel) {
    throw new Error("Not implemented.");
  }

  finalizeFileUpload(finalizeUploadUrl) {
    throw new Error("Not implemented.");
  }

  deleteFile(fileLinks) {
    throw new Error("Not implemented.");
  }
}

/**
 * Default File API Client for deposits.
 */
export class RDMDepositFileApiClient extends DepositFileApiClient {
  initializeFileUpload(initializeUploadUrl, filename) {
    const payload = [
      {
        key: filename,
      },
    ];
    return this.axiosWithConfig.post(initializeUploadUrl, payload, {});
  }

  uploadFile(uploadUrl, file, onUploadProgressFn, cancelFn) {
    return this.axiosWithConfig.put(uploadUrl, file, {
      headers: this.apiHeaders["octet-stream"],
      onUploadProgress: (event) => {
        const percent = Math.floor((event.loaded / event.total) * 100);
        onUploadProgressFn && onUploadProgressFn(percent);
      },
      cancelToken: new axios.CancelToken(cancelFn),
    });
  }

  finalizeFileUpload(finalizeUploadUrl) {
    return this.axiosWithConfig.post(finalizeUploadUrl, {});
  }

  importParentRecordFiles(draftLinks) {
    const link = `${draftLinks.self}/actions/files-import`;
    return this.axiosWithConfig.post(link, {});
  }

  deleteFile(fileLinks) {
    return this.axiosWithConfig.delete(fileLinks.self);
  }
}

/**
 * File API Client for Uppy uploader, with support for L,M transfer types.
 */
export class UppyDepositFileApiClient extends DepositFileApiClient {
  constructor(additionalApiConfig, defaultTransferType, transferTypes) {
    super(additionalApiConfig);
    this.defaultTransferType = defaultTransferType || "L";
    this.transferTypes = transferTypes || ["L"];
  }

  initializeFileUpload(initializeUploadUrl, filename, transferOptions) {
    console.log("IFU", initializeUploadUrl, filename, transferOptions);

    const { fileSize, type: transferType, ...opts } = transferOptions;

    if (!this.transferTypes.includes(transferType)) {
      throw new UnsupportedTransferTypeError(
        `Unsupported upload TransferType "${transferType}". Server supports: ${this.transferTypes}`,
        { filename, transferType, supportedTypes: this.transferTypes }
      );
    }

    const payload = [
      {
        key: filename,
        size: fileSize,
        transfer: {
          type: transferType || this.defaultTransferType,
          ...opts,
        },
      },
    ];
    return this.axiosWithConfig.post(initializeUploadUrl, payload, {});
  }

  finalizeFileUpload(finalizeUploadUrl) {
    return this.axiosWithConfig.post(finalizeUploadUrl, {});
  }

  deleteFile(fileLinks, options) {
    return this.axiosWithConfig.delete(fileLinks.self, options);
  }

  /**
   * This method is required by Uppy to do single-part small file uploads.
   * These uploads are managed through a simple XHRHttpRequest-based upload request,
   * and thus cannot reuse current axiosWithConfig instance to make the request.
   *
   * @param {*} fileContentUrl link to upload the file data to
   * @param {*} file Uppy file metadata
   * @param {*} options extra request options
   * @returns
   */
  async getUploadParams(fileContentUrl, file, options) {
    console.log("GUP", fileContentUrl, file, options);

    const axiosDefaults = this.axiosWithConfig.defaults;

    // Extract headers, ensuring they are merged properly
    const xhrHeaders = {
      ...axiosDefaults.headers.common, // Common headers like Authorization
    };

    if (axiosDefaults.xsrfCookieName && axiosDefaults.xsrfHeaderName) {
      /**
       * Ensure CSRF headers are included
       * TODO: Kinda ugly manual parsing. We can instead consider using:
       * import Cookies from "js-cookie";
       * const csrfToken = Cookies.get("csrftoken");
       */
      const csrfToken = document.cookie
        .split("; ")
        .find((row) => row.startsWith(`${axiosDefaults.xsrfCookieName}=`))
        ?.split("=")[1];

      if (csrfToken) {
        xhrHeaders[axiosDefaults.xsrfHeaderName] = csrfToken;
      }
    }

    const resp = {
      method: "PUT",
      url: fileContentUrl,
      headers: {
        ...xhrHeaders,
        // The following is hard-coded into drafts files resource
        "Content-Type": "application/octet-stream",
      },
    };
    return resp;
  }
}

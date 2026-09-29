'use strict';

class ApiError extends Error {
  constructor(status, code, message) {
    super(message || code);
    this.status = status;
    this.code = code;
  }
}

const malformed = (m) => new ApiError(400, 'malformed_request', m || 'the request body is not valid JSON of the expected shape');
const invalid = (m) => new ApiError(422, 'validation_failed', m || 'validation failed');
const notFound = (m) => new ApiError(404, 'not_found', m || 'not found');
const forbidden = (m) => new ApiError(403, 'forbidden', m || 'not permitted');
const unauthenticated = (m) => new ApiError(401, 'unauthenticated', m || 'authentication required');
const conflict = (code, m) => new ApiError(409, code, m || code);

module.exports = { ApiError, malformed, invalid, notFound, forbidden, unauthenticated, conflict };

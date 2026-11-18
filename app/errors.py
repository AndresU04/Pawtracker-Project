"""Consistent JSON error format:
{"error": {"code": "...", "message": "...", "details": {...optional}}}
"""
from flask import jsonify
from werkzeug.exceptions import HTTPException

from .extensions import db


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def error_response(status, code, message, details=None):
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(exc):
        db.session.rollback()  # releases any row locks held by the request
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.errorhandler(HTTPException)
    def handle_http_error(exc):
        code = (exc.name or "error").lower().replace(" ", "_")
        return error_response(exc.code or 500, code, exc.description)

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        app.logger.exception("Unhandled exception")
        db.session.rollback()
        return error_response(500, "internal_error", "An unexpected error occurred.")

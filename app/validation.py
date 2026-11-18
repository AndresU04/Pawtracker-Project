"""Small, dependency-free request validation + pagination helpers."""
import math
import re
from datetime import date

from flask import request
from sqlalchemy import func, select

from .errors import ApiError
from .extensions import db

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def json_body():
    data = request.get_json(silent=True)
    if data is None:
        raise ApiError(
            400,
            "invalid_json",
            "Request body must be valid JSON with Content-Type: application/json.",
        )
    return data


def optional_json_body():
    return request.get_json(silent=True) or {}


def validate(data, schema, partial=False):
    """Validate/clean `data` against `schema`. Raises ApiError(422) with per-field details."""
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_json", "Request body must be a JSON object.")
    clean, errors = {}, {}
    for field, rule in schema.items():
        if field not in data:
            if rule.get("required") and not partial:
                errors[field] = "is required"
            continue
        value = data[field]
        if value is None:
            if rule.get("nullable"):
                clean[field] = None
            else:
                errors[field] = "may not be null"
            continue
        try:
            clean[field] = _coerce(value, rule)
        except ValueError as exc:
            errors[field] = str(exc)
    if errors:
        raise ApiError(422, "validation_error", "Request validation failed.", errors)
    return clean


def _coerce(value, rule):
    kind = rule["type"]
    if kind == "str":
        if not isinstance(value, str):
            raise ValueError("must be a string")
        if rule.get("strip", True):
            value = value.strip()
        if rule.get("lower"):
            value = value.lower()
        min_len = rule.get("min_len", 1 if rule.get("required") else 0)
        if len(value) < min_len:
            raise ValueError(f"must be at least {min_len} character(s)")
        if "max_len" in rule and len(value) > rule["max_len"]:
            raise ValueError(f"must be at most {rule['max_len']} characters")
        if "choices" in rule and value not in rule["choices"]:
            raise ValueError("must be one of: " + ", ".join(rule["choices"]))
        if rule.get("email") and not EMAIL_RE.match(value):
            raise ValueError("must be a valid email address")
        return value
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("must be an integer")
        if "min" in rule and value < rule["min"]:
            raise ValueError(f"must be >= {rule['min']}")
        if "max" in rule and value > rule["max"]:
            raise ValueError(f"must be <= {rule['max']}")
        return value
    if kind == "date":
        if not isinstance(value, str):
            raise ValueError("must be an ISO date string (YYYY-MM-DD)")
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ValueError("must be an ISO date string (YYYY-MM-DD)")
    raise ValueError(f"unsupported schema type: {kind}")


def int_arg(name, default=None, minimum=None, maximum=None):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(400, "invalid_query_param", f"Query parameter '{name}' must be an integer.")
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ApiError(
            400,
            "invalid_query_param",
            f"Query parameter '{name}' is out of range"
            + (f" ({minimum}..{maximum})." if maximum is not None else f" (>= {minimum})."),
        )
    return value


def paginate(stmt, serializer):
    """Run a SELECT with ?page= & ?per_page= (default 20, max 100)."""
    page = int_arg("page", 1, minimum=1)
    per_page = int_arg("per_page", 20, minimum=1, maximum=100)
    total = db.session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.session.scalars(stmt.limit(per_page).offset((page - 1) * per_page)).all()
    return {
        "items": [serializer(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": math.ceil(total / per_page) if total else 0,
    }

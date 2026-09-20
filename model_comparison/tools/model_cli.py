#!/usr/bin/env python3
"""Validate the static configuration needed by a future model API client."""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


SCHEMA_VERSION = "robot-model-api-config/0.1"
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
REQUIRED_STRINGS = ("provider", "model", "base_url", "api_path", "api_format", "api_key_env")


def load_config(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError("config path must exist and be a regular file")

    def reject_constant(value):
        raise ValueError(f"non-finite JSON value is not allowed: {value}")

    try:
        config = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    except UnicodeDecodeError as error:
        raise ValueError("config must be valid UTF-8") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON at line {error.lineno}, column {error.colno}") from error
    if not isinstance(config, dict):
        raise ValueError("JSON top level must be an object")
    return config


def validate_config(config):
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must equal {SCHEMA_VERSION}")

    for field in REQUIRED_STRINGS:
        value = config.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")

    try:
        parsed_url = urlparse(config["base_url"])
        hostname = parsed_url.hostname
    except ValueError as error:
        raise ValueError("base_url must be a valid HTTP or HTTPS URL") from error
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc or not hostname:
        raise ValueError("base_url must be a valid HTTP or HTTPS URL")

    if not config["api_path"].startswith("/"):
        raise ValueError("api_path must start with /")
    if ENV_NAME.fullmatch(config["api_key_env"]) is None:
        raise ValueError("api_key_env must be a valid environment variable name")

    if not isinstance(config.get("endpoint_verified"), bool):
        raise ValueError("endpoint_verified must be a bool")

    request = config.get("request")
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    if not isinstance(request.get("stream"), bool):
        raise ValueError("request.stream must be a bool")

    timeout = request.get("timeout_s")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("request.timeout_s must be a number greater than 0")

    retries = request.get("max_retries")
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
        raise ValueError("request.max_retries must be an integer greater than or equal to 0")


def _one_line(value):
    return value.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        validate_config(config)
    except (OSError, ValueError) as error:
        print(f"Invalid config: {error}", file=sys.stderr)
        return 2

    print(
        "Config valid: "
        f"provider={_one_line(config['provider'])} "
        f"model={_one_line(config['model'])} "
        f"api_format={_one_line(config['api_format'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

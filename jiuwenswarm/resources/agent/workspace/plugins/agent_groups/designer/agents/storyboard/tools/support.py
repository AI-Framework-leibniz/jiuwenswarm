# -*- coding: utf-8 -*-
"""Shared checks for one member package. Imported while that package is on sys.path."""

from __future__ import annotations

from urllib.parse import unquote, urlparse


def args_of(inputs):
    if isinstance(inputs, dict):
        return inputs
    dump = getattr(inputs, "model_dump", None)
    if callable(dump):
        data = dump()
        if isinstance(data, dict):
            return data
    return {}


def ticket_of(data):
    ticket = data.get("shot_ticket")
    if not isinstance(ticket, str) or not ticket.strip():
        return None
    return ticket


def file_uri_ok(uri):
    if not isinstance(uri, str) or not uri.startswith("file:"):
        return False
    path = unquote(urlparse(uri).path or "")
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        return True
    return path.startswith("/") and len(path) > 1

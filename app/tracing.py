"""Eventos JSON visibles en los logs de Uvicorn, sin cabeceras de autenticación."""
from contextvars import ContextVar
import json
import logging
import os

trace_id = ContextVar("trace_id", default=None)
message_id = ContextVar("message_id", default=None)
logger = logging.getLogger("uvicorn.error")


def event(name, *, payload=None, **fields):
    record = {"event": name, "trace_id": trace_id.get(), "message_id": message_id.get(), **fields}
    if payload is not None and os.getenv("LOG_JSON_PAYLOADS", "true").lower() == "true":
        record["payload"] = payload
    logger.info(json.dumps(record, ensure_ascii=False, default=str))

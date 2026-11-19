"""Application entry point: route assembly and startup initialization (create DB + initial admin seed)."""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import get_db, init_db
from .routes import (ai, annotations, auth, changes, datasets, edges, fields,
                     files, imports, lineage, preview, version_tags)
from .security import hash_password


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    with get_db() as conn:
        has_user = conn.execute("SELECT 1 FROM user LIMIT 1").fetchone()
    if has_user is None:
        s = get_settings()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO user(username, password_hash, display_name, role, created_at)"
                " VALUES (?,?,?,?,datetime('now'))",
                (s.admin_username, hash_password(s.admin_password),
                 "Initial admin", "admin"))
        print(f"Created initial administrator \"{s.admin_username}\""
              " (password from ADMIN_PASSWORD)",
              file=sys.stderr)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Clew", version="0.1.0",
                  description="Field-level AI data lineage tool"
                              " (M4: AI chat and lineage suggestions)",
                  lifespan=lifespan)
    # M2: the frontend is connected; CORS origins are explicitly configured via
    # CORS_ORIGINS; authentication uses Bearer rather than cookies, so
    # allow_credentials is unnecessary (avoids echoing credentials for wildcard
    # origins).
    origins = [origin.strip() for origin in get_settings().cors_origins.split(",")
               if origin.strip()]
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_credentials=False,
        allow_methods=["*"], allow_headers=["*"])
    app.include_router(auth.router)
    app.include_router(files.router)
    app.include_router(imports.router)
    app.include_router(datasets.router)
    app.include_router(lineage.router)
    app.include_router(preview.router)
    # M3
    app.include_router(annotations.router)
    app.include_router(fields.router)
    app.include_router(edges.router)
    app.include_router(changes.router)
    app.include_router(version_tags.router)
    # M4
    app.include_router(ai.router)
    return app


app = create_app()

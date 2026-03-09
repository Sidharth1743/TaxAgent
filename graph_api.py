#!/usr/bin/env python3
"""FastAPI app to serve Spanner graph data and a web UI."""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from memory.spanner_graph import load_config, get_client
from dotenv import load_dotenv
from google.cloud import spanner

logger = logging.getLogger(__name__)

app = FastAPI(title="TaxAgent Graph API")

_database = None


def _db():
    global _database
    if _database is None:
        load_dotenv()
        cfg = load_config()
        if not cfg:
            return None
        _database = get_client(cfg)
    return _database


_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_:.\-]{1,128}$")


def _validate_id(value: str, name: str) -> str:
    if not value or not _ID_PATTERN.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid {name}: must be 1-128 alphanumeric/underscore characters")
    return value


@app.get("/health")
def health() -> Dict[str, str]:
    db = _db()
    status = "ok" if db else "no_db"
    return {"status": status}


@app.get("/users")
def list_users() -> Dict[str, List[str]]:
    try:
        db = _db()
        if not db:
            return {"users": []}
        users = []
        with db.snapshot(multi_use=True) as snap:
            res = snap.execute_sql("SELECT user_id FROM Users ORDER BY created_at DESC")
            for row in res:
                users.append(row[0])
        return {"users": users}
    except Exception as e:
        logger.exception("Error listing users")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions")
def list_sessions(user_id: str = Query(...)) -> Dict[str, List[str]]:
    _validate_id(user_id, "user_id")
    try:
        db = _db()
        if not db:
            return {"sessions": []}
        sessions = []
        with db.snapshot(multi_use=True) as snap:
            res = snap.execute_sql(
                "SELECT session_id FROM Sessions WHERE user_id=@u ORDER BY started_at DESC",
                params={"u": user_id},
                param_types={"u": spanner.param_types.STRING},
            )
            for row in res:
                sessions.append(row[0])
        return {"sessions": sessions}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error listing sessions")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph")
def get_graph(
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
) -> Dict[str, List[Dict[str, str]]]:
    if user_id:
        _validate_id(user_id, "user_id")
    if session_id:
        _validate_id(session_id, "session_id")

    try:
        db = _db()
        if not db:
            return {"nodes": [], "edges": []}

        nodes = []
        edges = []

        with db.snapshot(multi_use=True) as snap:
            if user_id:
                res = snap.execute_sql(
                    "SELECT user_id FROM Users WHERE user_id=@u",
                    params={"u": user_id},
                    param_types={"u": spanner.param_types.STRING},
                )
                for row in res:
                    nodes.append({"id": row[0], "type": "User", "label": row[0]})

                res = snap.execute_sql(
                    "SELECT session_id FROM Sessions WHERE user_id=@u",
                    params={"u": user_id},
                    param_types={"u": spanner.param_types.STRING},
                )
                for row in res:
                    nodes.append({"id": row[0], "type": "Session", "label": row[0]})

            if session_id:
                res = snap.execute_sql(
                    "SELECT query_id, text FROM Queries WHERE session_id=@s",
                    params={"s": session_id},
                    param_types={"s": spanner.param_types.STRING},
                )
                for row in res:
                    nodes.append({"id": row[0], "type": "Query", "label": (row[1] or row[0])})

            # Pull all edges filtered by user/session if provided.
            if user_id:
                res = snap.execute_sql(
                    "SELECT from_id, to_id, type FROM Edges "
                    "WHERE from_id=@u OR to_id=@u",
                    params={"u": user_id},
                    param_types={"u": spanner.param_types.STRING},
                )
            elif session_id:
                res = snap.execute_sql(
                    "SELECT from_id, to_id, type FROM Edges "
                    "WHERE from_id=@s OR to_id=@s",
                    params={"s": session_id},
                    param_types={"s": spanner.param_types.STRING},
                )
            else:
                res = snap.execute_sql("SELECT from_id, to_id, type FROM Edges")
            for row in res:
                edges.append({"from": row[0], "to": row[1], "type": row[2]})

        return {"nodes": nodes, "edges": edges}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching graph")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_class=HTMLResponse)
def index():
    path = os.path.join(os.path.dirname(__file__), "static", "graph.html")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


app.mount("/static", StaticFiles(directory="static"), name="static")

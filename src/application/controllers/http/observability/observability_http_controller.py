# MIT License
#
# Copyright (c) 2026 Philipp Höllinger
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""Live observability HTML page + SSE stream of gateway decisions."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from wireup import injectable

from infrastructure.observability.in_memory_observability_recorder_adapter import (
    InMemoryObservabilityRecorderAdapter,
)

_SSE_HEARTBEAT_INTERVAL_SECONDS = 15.0


@injectable
class ObservabilityHttpController:
    """Renders the live observability page and streams new entries via SSE."""

    def __init__(
        self, in_memory_recorder: InMemoryObservabilityRecorderAdapter
    ) -> None:
        self._in_memory_recorder = in_memory_recorder
        self.router = APIRouter()
        self._register_routes()

    def _register_routes(self) -> None:
        self.router.add_api_route(
            "/observability",
            self._render_observability_page,
            methods=["GET"],
            response_class=HTMLResponse,
        )
        self.router.add_api_route(
            "/observability/events",
            self._stream_observability_events,
            methods=["GET"],
        )

    def _render_observability_page(self) -> HTMLResponse:
        return HTMLResponse(_OBSERVABILITY_HTML_PAGE)

    async def _stream_observability_events(
        self, request: Request
    ) -> StreamingResponse:
        recorder = self._in_memory_recorder

        async def event_generator() -> AsyncIterator[bytes]:
            async with recorder.subscribe() as subscriber_queue:
                for entry in recorder.snapshot():
                    if await request.is_disconnected():
                        return
                    yield _format_server_sent_event(
                        entry.to_json_payload(include_result_data=True)
                    )
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        entry = await asyncio.wait_for(
                            subscriber_queue.get(),
                            timeout=_SSE_HEARTBEAT_INTERVAL_SECONDS,
                        )
                    except TimeoutError:
                        yield b": keepalive\n\n"
                        continue
                    yield _format_server_sent_event(
                        entry.to_json_payload(include_result_data=True)
                    )

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )


def _format_server_sent_event(payload: dict[str, object]) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


_OBSERVABILITY_HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SQL Gateway · Live observability</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,400..700,0..1,-50..200&display=block" rel="stylesheet">
  <style>
    :root {
      --primary: #003366;
      --primary-dim: #264d80;
      --on-primary: #ffffff;
      --primary-container: #e1ecfa;
      --primary-container-border: #b4cfef;
      --surface: #fcfbf9;
      --surface-elevated: #ffffff;
      --surface-subtle: #eff3f8;
      --on-surface: #1a1c1e;
      --on-surface-variant: #4a4f55;
      --outline: #74777b;
      --outline-soft: #c5cad0;
      --success: #1b5e20;
      --success-bg: #e9f5ec;
      --success-border: #b5d9be;
      --warning: #b35300;
      --warning-bg: #fff3e0;
      --warning-border: #f3cd9d;
      --error: #b00020;
      --error-bg: #fdeaea;
      --error-border: #f0c2c2;
      --mono: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Open Sans", -apple-system, BlinkMacSystemFont, "Segoe UI",
                   Roboto, "Helvetica Neue", Arial, sans-serif;
      font-weight: 400;
      background: var(--surface);
      color: var(--on-surface);
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    .material-symbols-rounded {
      font-variation-settings: 'FILL' 0, 'wght' 500, 'GRAD' 0, 'opsz' 24;
    }
    header {
      background: var(--primary);
      color: var(--on-primary);
      padding: 22px 32px 18px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    header h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 600;
      letter-spacing: 0.2px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    header .subtitle {
      margin: 0;
      font-size: 13px;
      color: rgba(255, 255, 255, 0.8);
    }
    header .status-line {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: rgba(255, 255, 255, 0.75);
      margin-top: 4px;
    }
    header .status-line .dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #7cd97c;
      box-shadow: 0 0 8px #7cd97c;
    }
    header .status-line.disconnected .dot {
      background: #e58a8a;
      box-shadow: 0 0 6px #e58a8a;
    }
    .header-links {
      margin-top: 14px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .header-link {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(255, 255, 255, 0.12);
      color: var(--on-primary);
      text-decoration: none;
      padding: 10px 18px 10px 14px;
      border-radius: 100px;
      font-size: 14px;
      font-weight: 500;
      letter-spacing: 0.1px;
      line-height: 20px;
      border: 1px solid rgba(255, 255, 255, 0.24);
      transition: background 0.2s ease, border-color 0.2s ease;
    }
    .header-link:hover {
      background: rgba(255, 255, 255, 0.22);
      border-color: rgba(255, 255, 255, 0.4);
    }
    .header-link .material-symbols-rounded { font-size: 18px; }

    .filter-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      padding: 16px 32px 0;
    }
    .filter-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px 6px 10px;
      border-radius: 10px;
      background: transparent;
      border: 1px solid var(--outline-soft);
      font-size: 12.5px;
      font-weight: 600;
      color: var(--on-surface-variant);
      cursor: pointer;
      user-select: none;
      transition: background 0.15s, border-color 0.15s, color 0.15s;
    }
    .filter-chip input { display: none; }
    .filter-chip:has(input:checked) {
      background: var(--primary-container);
      border-color: var(--primary-container-border);
      color: var(--primary);
    }
    .filter-chip .count {
      background: rgba(0, 51, 102, 0.1);
      padding: 1px 8px;
      border-radius: 8px;
      font-variant-numeric: tabular-nums;
    }
    .filter-chip .icon-check { display: none; font-size: 15px; }
    .filter-chip:has(input:checked) .icon-check { display: inline-block; }
    .filter-chip[data-outcome="allowed"] .icon-type { color: var(--success); }
    .filter-chip[data-outcome="rejected"] .icon-type { color: var(--warning); }
    .filter-chip[data-outcome="db_error"] .icon-type { color: var(--error); }
    .filter-chip .material-symbols-rounded { font-size: 16px; }

    .filter-spacer { flex: 1; }
    .filter-total {
      font-size: 13px;
      color: var(--on-surface-variant);
      font-weight: 500;
    }
    .filter-total strong { color: var(--primary); font-weight: 700; }

    main {
      padding: 24px 32px 56px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
      gap: 16px;
      align-items: stretch;
    }
    .empty-state {
      grid-column: 1 / -1;
      padding: 48px 24px;
      text-align: center;
      color: var(--on-surface-variant);
      font-size: 14px;
      border: 1px dashed var(--outline-soft);
      border-radius: 12px;
      background: var(--surface-elevated);
    }

    .card {
      background: var(--surface-elevated);
      border-radius: 12px;
      box-shadow:
        0 1px 2px rgba(0, 51, 102, 0.05),
        0 1px 3px rgba(0, 0, 0, 0.06);
      padding: 20px;
      overflow: hidden;
      transition: box-shadow 0.2s ease, transform 0.2s ease;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      gap: 14px;
      --card-accent: var(--primary);
      --card-accent-bg: #e9eef7;
      --card-accent-border: #c6d3e9;
    }
    .card:hover {
      box-shadow:
        0 4px 10px rgba(0, 51, 102, 0.08),
        0 2px 6px rgba(0, 0, 0, 0.08);
      transform: translateY(-1px);
    }
    .card.allowed {
      --card-accent: var(--success);
      --card-accent-bg: var(--success-bg);
      --card-accent-border: var(--success-border);
    }
    .card.rejected {
      --card-accent: var(--warning);
      --card-accent-bg: var(--warning-bg);
      --card-accent-border: var(--warning-border);
    }
    .card.db_error {
      --card-accent: var(--error);
      --card-accent-bg: var(--error-bg);
      --card-accent-border: var(--error-border);
    }
    .card .material-symbols-rounded { color: var(--card-accent); }
    .card-row { margin: 0; min-width: 0; }
    .card-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .category {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 1.2px;
      color: var(--on-surface-variant);
      font-weight: 700;
    }
    .card-index {
      font-family: var(--mono);
      font-size: 11px;
      color: var(--outline);
      font-weight: 500;
      background: var(--surface-subtle);
      padding: 2px 8px;
      border-radius: 8px;
    }
    .card-title {
      font-size: 16px;
      font-weight: 600;
      color: var(--card-accent);
      line-height: 1.35;
    }
    .card-desc {
      font-size: 13px;
      color: var(--on-surface-variant);
      line-height: 1.5;
    }
    .card-meta-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 12px;
      background: var(--surface-subtle);
      border-radius: 10px;
    }
    .chip.status {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 11px 4px 8px;
      border-radius: 10px;
      font-size: 11.5px;
      font-weight: 700;
      letter-spacing: 0.4px;
      white-space: nowrap;
      background: var(--surface-elevated);
      color: var(--on-surface);
      border: 1px solid var(--outline-soft);
    }
    .chip.status .material-symbols-rounded { font-size: 16px; }
    .duration {
      font-family: var(--mono);
      font-size: 11.5px;
      color: var(--on-surface-variant);
      font-weight: 500;
    }
    .block {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .block-heading {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 1.1px;
      color: var(--on-surface-variant);
      font-weight: 700;
    }
    .block-heading .material-symbols-rounded { font-size: 16px; }
    pre {
      background: #f0f3f8;
      border: 1px solid #dde3ec;
      padding: 9px 11px;
      border-radius: 8px;
      overflow-x: auto;
      font-family: var(--mono);
      font-size: 12px;
      margin: 0;
      color: #1a1c1e;
      white-space: pre-wrap;
      word-break: break-word;
    }
    pre.query {
      background: var(--card-accent-bg);
      border-color: var(--card-accent-border);
      color: var(--card-accent);
    }
    .result-summary {
      margin-top: 4px;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
    }
    .stat-chip {
      background: var(--card-accent-bg);
      color: var(--card-accent);
      border: 1px solid var(--card-accent-border);
      padding: 3px 10px;
      border-radius: 10px;
      font-size: 11.5px;
      font-weight: 500;
    }
    .stat-chip strong { font-weight: 700; }
    .stat-chip.muted { background: #eceff2; color: var(--outline); border-color: #dadee2; }
    .reason-chip {
      background: var(--card-accent-bg);
      color: var(--card-accent);
      border: 1px solid var(--card-accent-border);
      padding: 3px 10px;
      border-radius: 10px;
      font-size: 11px;
      font-weight: 700;
      font-family: var(--mono);
      letter-spacing: 0.4px;
    }
    .result-message {
      margin: 6px 0 0;
      font-size: 13px;
      color: #3a3d41;
      width: 100%;
    }
    .result-detail {
      margin: 4px 0 0;
      font-size: 11.5px;
      color: var(--outline);
      width: 100%;
    }
    details.raw { margin-top: 4px; font-size: 12px; }
    details.raw > summary {
      list-style: none;
      cursor: pointer;
      user-select: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px 6px 10px;
      border-radius: 100px;
      border: 1px solid var(--outline-soft);
      background: var(--surface-elevated);
      font-size: 12px;
      font-weight: 500;
      color: var(--on-surface-variant);
    }
    details.raw > summary::-webkit-details-marker { display: none; }
    details.raw > summary .material-symbols-rounded {
      font-size: 18px;
      transition: transform 0.2s ease;
    }
    details.raw[open] > summary .material-symbols-rounded.chevron {
      transform: rotate(180deg);
    }
    pre.response { margin-top: 8px; max-height: 320px; overflow-y: auto; }
    footer {
      padding: 24px 32px 32px;
      color: var(--on-surface-variant);
      font-size: 12.5px;
      text-align: center;
    }
  </style>
</head>
<body>
  <header>
    <h1><span class="material-symbols-rounded">monitoring</span> Live observability</h1>
    <p class="subtitle">Every <code>/query</code> request, ordered newest-first. PII-free audit log goes to stdout; this page reads the in-memory buffer.</p>
    <div class="status-line" id="status-line"><span class="dot"></span><span id="status-text">Connecting…</span></div>
    <div class="header-links">
      <a class="header-link" href="/docs" target="_blank" rel="noopener">
        <span class="material-symbols-rounded">api</span>
        <span>Swagger UI</span>
      </a>
      <a class="header-link" href="/openapi.json" target="_blank" rel="noopener">
        <span class="material-symbols-rounded">code_blocks</span>
        <span>OpenAPI</span>
      </a>
      <a class="header-link" href="/health" target="_blank" rel="noopener">
        <span class="material-symbols-rounded">favorite</span>
        <span>Health</span>
      </a>
      <a class="header-link" href="/readiness" target="_blank" rel="noopener">
        <span class="material-symbols-rounded">monitor_heart</span>
        <span>Readiness</span>
      </a>
    </div>
  </header>
  <div class="filter-bar" id="filter-bar">
    <label class="filter-chip" data-outcome="allowed">
      <input type="checkbox" data-outcome="allowed" checked>
      <span class="material-symbols-rounded icon-type">check_circle</span>
      <span class="material-symbols-rounded icon-check">check</span>
      <span>Allowed</span>
      <span class="count" data-count="allowed">0</span>
    </label>
    <label class="filter-chip" data-outcome="rejected">
      <input type="checkbox" data-outcome="rejected" checked>
      <span class="material-symbols-rounded icon-type">block</span>
      <span class="material-symbols-rounded icon-check">check</span>
      <span>Gateway rejected</span>
      <span class="count" data-count="rejected">0</span>
    </label>
    <label class="filter-chip" data-outcome="db_error">
      <input type="checkbox" data-outcome="db_error" checked>
      <span class="material-symbols-rounded icon-type">error</span>
      <span class="material-symbols-rounded icon-check">check</span>
      <span>Database error</span>
      <span class="count" data-count="db_error">0</span>
    </label>
    <span class="filter-spacer"></span>
    <span class="filter-total"><strong id="total-count">0</strong> entries</span>
  </div>
  <main id="cards">
    <div class="empty-state" id="empty-state">
      Waiting for the first /query request. Send one with <code>curl</code> or run <code>./demo.sh</code>.
    </div>
  </main>
  <footer>SQL Gateway · ring buffer holds the last 500 entries · stream stays open via Server-Sent Events</footer>
  <script>
    (function () {
      const SQL_KEYWORDS = ["SELECT","INSERT","UPDATE","DELETE","DROP","ALTER","CREATE","TRUNCATE","VACUUM","WITH"];
      const REJECTION_MESSAGES = {
        empty_query: "The query was empty.",
        parse_error: "The query could not be parsed.",
        multi_statement: "Multiple statements in one request are not allowed.",
        root_not_allowed: "Only SELECT, INSERT, UPDATE, or DELETE are allowed at the statement root.",
        forbidden_construct: "DDL or transaction-control statements are not allowed anywhere in the tree.",
        select_into: "SELECT ... INTO new_table is not allowed.",
        data_modifying_cte: "CTEs that INSERT, UPDATE, or DELETE are not allowed.",
        unbounded_write: "UPDATE and DELETE must include a WHERE clause.",
        dangerous_function: "The query uses a filesystem, process, or network function that is blocked.",
        payload_type_mismatch: "The query payload shape does not match the selected database adapter.",
      };
      const MAX_CARDS_ON_PAGE = 500;
      const state = {
        counts: { allowed: 0, rejected: 0, db_error: 0 },
        totalEverReceived: 0,
        activeFilters: new Set(["allowed", "rejected", "db_error"]),
        seenRequestIds: new Set(),
      };
      const STORAGE_KEY = "sql_gateway_observability_filters";
      try {
        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
        if (Array.isArray(stored)) state.activeFilters = new Set(stored);
      } catch (_) {}

      const mainEl = document.getElementById("cards");
      const emptyStateEl = document.getElementById("empty-state");
      const totalEl = document.getElementById("total-count");
      const statusLineEl = document.getElementById("status-line");
      const statusTextEl = document.getElementById("status-text");
      const filterInputs = document.querySelectorAll(".filter-chip input");

      filterInputs.forEach((input) => {
        input.checked = state.activeFilters.has(input.dataset.outcome);
        input.addEventListener("change", () => {
          if (input.checked) state.activeFilters.add(input.dataset.outcome);
          else state.activeFilters.delete(input.dataset.outcome);
          try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...state.activeFilters])); } catch (_) {}
          applyFilters();
        });
      });

      function escapeHtml(value) {
        if (value === null || value === undefined) return "";
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#039;");
      }

      function humaniseRejection(code) {
        if (!code) return "Query rejected.";
        return REJECTION_MESSAGES[code] || "Query rejected.";
      }

      function prettyQuery(query) {
        if (typeof query === "string") return query === "" ? "(empty string)" : query;
        return JSON.stringify(query, null, 2);
      }

      function outcomeFor(entry) {
        const decision = entry.decision;
        if (decision === "allowed") return { kind: "allowed", label: "Allowed · 200", icon: "check_circle" };
        if (decision === "rejected") return { kind: "rejected", label: "Rejected · 400", icon: "block" };
        if (decision === "db_error") return { kind: "db_error", label: "DB error · 502", icon: "error" };
        return { kind: "error", label: "HTTP ?", icon: "help" };
      }

      function deriveTitle(query) {
        if (typeof query === "string") {
          const trimmed = query.trim();
          if (!trimmed) return "Empty query";
          const keywordMatch = trimmed.match(new RegExp("^\\\\s*(" + SQL_KEYWORDS.join("|") + ")\\\\b", "i"));
          if (!keywordMatch) {
            return trimmed.length <= 48 ? trimmed : trimmed.slice(0, 45) + "…";
          }
          const keyword = keywordMatch[1].toUpperCase();
          let table = "";
          if (keyword === "SELECT") {
            const intoMatch = trimmed.match(/\\bINTO\\s+([a-zA-Z_]\\w*)/i);
            if (intoMatch) return "SELECT INTO " + intoMatch[1];
            const fromMatch = trimmed.match(/\\bFROM\\s+([a-zA-Z_]\\w*)/i);
            table = fromMatch ? fromMatch[1] : "";
            if (/\\bSELECT\\s+\\*/i.test(trimmed) && table) return "SELECT * FROM " + table;
            if (!table) {
              const fn = trimmed.match(/\\bSELECT\\s+([a-zA-Z_]\\w*)\\s*\\(/i);
              if (fn) return "SELECT " + fn[1] + "(…)";
            }
          } else if (keyword === "INSERT") {
            const m = trimmed.match(/\\bINTO\\s+([a-zA-Z_]\\w*)/i);
            table = m ? m[1] : "";
          } else if (keyword === "UPDATE") {
            const m = trimmed.match(/\\bUPDATE\\s+([a-zA-Z_]\\w*)/i);
            table = m ? m[1] : "";
          } else if (keyword === "DELETE") {
            const m = trimmed.match(/\\bFROM\\s+([a-zA-Z_]\\w*)/i);
            table = m ? m[1] : "";
          } else if (keyword === "DROP" || keyword === "TRUNCATE" || keyword === "ALTER") {
            const m = trimmed.match(new RegExp("^\\\\s*" + keyword + "\\\\s+(?:(?:TABLE|VIEW|INDEX|SEQUENCE)\\\\s+)?([a-zA-Z_]\\\\w*)", "i"));
            table = m ? m[1] : "";
          } else if (keyword === "CREATE") {
            const m = trimmed.match(/^\\s*CREATE\\s+(?:(?:TABLE|VIEW|INDEX)\\s+)?([a-zA-Z_]\\w*)/i);
            table = m ? m[1] : "";
          } else if (keyword === "VACUUM") {
            const m = trimmed.match(/\\bVACUUM\\s+([a-zA-Z_]\\w*)/i);
            table = m ? m[1] : "";
          } else if (keyword === "WITH") {
            return "WITH (CTE)";
          }
          if (/;\\s*\\S/.test(trimmed)) return keyword + " + stacked stmt";
          return table ? keyword + " " + table : keyword;
        }
        if (Array.isArray(query)) return "JSON array payload";
        if (query && typeof query === "object") {
          const op = (query.op || "").toString().trim();
          const coll = (query.collection || "").toString().trim();
          if (op && coll) return op + " on " + coll + " (JSON)";
          if (op) return "JSON: " + op;
          return "JSON payload";
        }
        return "Unknown payload";
      }

      function pluralise(count, noun) {
        return count + " " + noun + (count === 1 ? "" : "s");
      }

      function deriveDescription(entry) {
        if (entry.decision === "allowed") {
          const parts = [];
          const rowsReturned = entry.rows_returned;
          const cols = entry.columns;
          if (rowsReturned) {
            parts.push(pluralise(rowsReturned, "row") + " returned");
            if (Array.isArray(cols) && cols.length) parts.push(pluralise(cols.length, "column"));
          }
          if (typeof entry.rows_affected === "number" && entry.rows_affected > 0) {
            parts.push(pluralise(entry.rows_affected, "row") + " affected");
          }
          if (entry.rows_were_truncated) parts.push("result truncated");
          return parts.length ? "Allowed. " + parts.join(", ") + "." : "Allowed. No data returned.";
        }
        if (entry.decision === "rejected") {
          if (entry.rejection_code) {
            return humaniseRejection(entry.rejection_code);
          }
          return "Gateway rejected the query.";
        }
        if (entry.decision === "db_error") {
          return entry.db_error_message || "Database returned an error.";
        }
        return "Unexpected response.";
      }

      function categoryLabel(entry) {
        if (entry.decision === "allowed") return "Allowed request";
        if (entry.decision === "rejected") return "Gateway rejection";
        if (entry.decision === "db_error") return "Database error";
        return "Unknown";
      }

      function buildCompactResultHtml(entry, outcome) {
        if (outcome.kind === "allowed") {
          const chips = [];
          if (entry.rows_returned) {
            chips.push('<span class="stat-chip"><strong>' + entry.rows_returned + "</strong> " +
              (entry.rows_returned === 1 ? "row returned" : "rows returned") + "</span>");
          }
          if (Array.isArray(entry.columns) && entry.columns.length) {
            chips.push('<span class="stat-chip"><strong>' + entry.columns.length + "</strong> " +
              (entry.columns.length === 1 ? "column" : "columns") + "</span>");
          }
          if (typeof entry.rows_affected === "number" && entry.rows_affected > 0) {
            chips.push('<span class="stat-chip"><strong>' + entry.rows_affected + "</strong> " +
              (entry.rows_affected === 1 ? "row affected" : "rows affected") + "</span>");
          }
          if (entry.rows_were_truncated) {
            chips.push('<span class="stat-chip">truncated</span>');
          }
          if (!chips.length) chips.push('<span class="stat-chip muted">no data</span>');
          return '<div class="result-summary">' + chips.join("") + "</div>";
        }
        if (outcome.kind === "rejected") {
          const parts = [];
          if (entry.rejection_code) parts.push('<span class="reason-chip">' + escapeHtml(entry.rejection_code) + "</span>");
          parts.push('<p class="result-message">' + escapeHtml(humaniseRejection(entry.rejection_code)) + "</p>");
          if (entry.rejection_detail) parts.push('<p class="result-detail">detail: <code>' + escapeHtml(entry.rejection_detail) + "</code></p>");
          return '<div class="result-summary">' + parts.join("") + "</div>";
        }
        if (outcome.kind === "db_error") {
          const parts = [];
          if (entry.db_error_code) parts.push('<span class="reason-chip">SQLSTATE ' + escapeHtml(entry.db_error_code) + "</span>");
          if (entry.db_error_message) parts.push('<p class="result-message">' + escapeHtml(entry.db_error_message) + "</p>");
          return '<div class="result-summary">' + parts.join("") + "</div>";
        }
        return "";
      }

      function buildCard(entry, index) {
        const outcome = outcomeFor(entry);
        const title = deriveTitle(entry.redacted_query);
        const description = deriveDescription(entry);
        const durationMs = typeof entry.duration_ms === "number" ? entry.duration_ms.toFixed(1) + " ms" : "—";
        const compact = buildCompactResultHtml(entry, outcome);
        const rawJson = escapeHtml(JSON.stringify(entry, null, 2));

        const section = document.createElement("section");
        section.className = "card " + outcome.kind;
        section.dataset.outcome = outcome.kind;
        section.dataset.requestId = entry.request_id;
        section.innerHTML = `
          <div class="card-row card-top">
            <span class="category">${escapeHtml(categoryLabel(entry))}</span>
            <span class="card-index">#${String(index).padStart(2, "0")}</span>
          </div>
          <h3 class="card-row card-title">${escapeHtml(title)}</h3>
          <p class="card-row card-desc">${escapeHtml(description)}</p>
          <div class="card-row card-meta-row">
            <span class="chip status ${outcome.kind}">
              <span class="material-symbols-rounded">${outcome.icon}</span>
              <span>${escapeHtml(outcome.label)}</span>
            </span>
            <span class="duration">${escapeHtml(durationMs)}</span>
          </div>
          <div class="card-row block query-block">
            <div class="block-heading">
              <span class="material-symbols-rounded">terminal</span>
              <span>Query</span>
            </div>
            <pre class="query">${escapeHtml(prettyQuery(entry.redacted_query))}</pre>
          </div>
          <div class="card-row block result-block">
            <div class="block-heading">
              <span class="material-symbols-rounded">bolt</span>
              <span>Result</span>
            </div>
            ${compact}
            <details class="raw">
              <summary>
                <span class="material-symbols-rounded">data_object</span>
                <span>Raw response</span>
                <span class="material-symbols-rounded chevron">expand_more</span>
              </summary>
              <pre class="response">${rawJson}</pre>
            </details>
          </div>
        `;
        section.addEventListener("click", (event) => {
          if (event.target.closest("summary, pre, a, input, label")) return;
          const details = section.querySelector("details.raw");
          if (details) details.open = !details.open;
        });
        return section;
      }

      function applyFilters() {
        const cards = mainEl.querySelectorAll(".card");
        cards.forEach((card) => {
          card.style.display = state.activeFilters.has(card.dataset.outcome) ? "" : "none";
        });
        scheduleAlign();
      }

      function updateCounts() {
        const cardsOnPage = mainEl.querySelectorAll(".card").length;
        totalEl.textContent = cardsOnPage;
        document.querySelectorAll(".filter-chip .count").forEach((el) => {
          const key = el.dataset.count;
          el.textContent = state.counts[key] || 0;
        });
      }

      function addEntry(entry) {
        // Server replays its snapshot on every SSE (re)connect, so filter
        // by request_id to avoid duplicate cards after a reconnect.
        const requestId = entry.request_id;
        if (requestId && state.seenRequestIds.has(requestId)) return;
        if (requestId) state.seenRequestIds.add(requestId);

        if (emptyStateEl.parentNode) emptyStateEl.remove();

        state.totalEverReceived += 1;
        if (state.counts[entry.decision] !== undefined) state.counts[entry.decision] += 1;

        const card = buildCard(entry, state.totalEverReceived);
        if (!state.activeFilters.has(card.dataset.outcome)) {
          card.style.display = "none";
        }
        mainEl.insertBefore(card, mainEl.firstChild);

        // Cap what we keep in the DOM so memory stays bounded even on long
        // live sessions. The server-side ring buffer has its own cap; this
        // mirror on the client keeps scrolling manageable.
        while (mainEl.querySelectorAll(".card").length > MAX_CARDS_ON_PAGE) {
          const oldest = mainEl.querySelector(".card:last-of-type");
          if (!oldest) break;
          const oldestId = oldest.dataset.requestId;
          if (oldestId) state.seenRequestIds.delete(oldestId);
          oldest.remove();
        }

        updateCounts();
        scheduleAlign();
      }

      // -- Row-by-row height equalizer -------------------------------------
      let alignTimer = null;
      function alignRows() {
        const visible = Array.from(mainEl.querySelectorAll(".card")).filter((c) => c.style.display !== "none");
        if (!visible.length) return;
        visible.forEach((card) => {
          Array.from(card.children).forEach((child) => {
            child.style.minHeight = "";
            child.style.height = "";
          });
        });
        const rows = new Map();
        visible.forEach((card) => {
          const top = Math.round(card.getBoundingClientRect().top);
          if (!rows.has(top)) rows.set(top, []);
          rows.get(top).push(card);
        });
        rows.forEach((rowCards) => {
          if (rowCards.length < 2) return;
          const childCount = Math.max(...rowCards.map((c) => c.children.length));
          for (let i = 0; i < childCount; i += 1) {
            let max = 0;
            rowCards.forEach((card) => {
              const child = card.children[i];
              if (!child) return;
              const h = child.getBoundingClientRect().height;
              if (h > max) max = h;
            });
            if (max > 0) {
              rowCards.forEach((card) => {
                const child = card.children[i];
                if (child) child.style.minHeight = max + "px";
              });
            }
          }
        });
      }
      function scheduleAlign() {
        if (alignTimer) cancelAnimationFrame(alignTimer);
        alignTimer = requestAnimationFrame(() => {
          alignTimer = null;
          alignRows();
        });
      }
      window.addEventListener("resize", scheduleAlign);
      document.addEventListener("toggle", scheduleAlign, true);

      // -- SSE connection --------------------------------------------------
      function connect() {
        const source = new EventSource("/observability/events");
        source.onopen = () => {
          statusLineEl.classList.remove("disconnected");
          statusTextEl.textContent = "Connected · streaming live";
        };
        source.onmessage = (event) => {
          try {
            const entry = JSON.parse(event.data);
            addEntry(entry);
          } catch (_) {}
        };
        source.onerror = () => {
          statusLineEl.classList.add("disconnected");
          statusTextEl.textContent = "Disconnected · retrying…";
        };
      }
      connect();
    })();
  </script>
</body>
</html>
"""

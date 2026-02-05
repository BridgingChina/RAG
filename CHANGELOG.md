# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [1.0.0] - 2026-02-05

### Added
- FastAPI application with versioned `/api/v1` routes, including `/ask` and `/ingest`.
- Hybrid retrieval pipeline combining vector similarity and full-text search, with evidence grouped into anchor/concept/analogy channels.
- Ingest pipeline with semantic chunking, context enrichment, facet extraction, and lvl1–lvl3 taxonomy tagging.
- Config-driven taxonomy and facet enums via YAML files in `config/`.
- Seed data and utilities for local development and test runs (bridges, questions, and documents).
- Chinese tokenization via `jieba`, with support for a custom user dictionary in `data/`.

### Changed
- Performance improvements across retrieval and ingest (batch embedding requests, fewer DB round trips, and vector index tuning).

### Fixed
- Align API schemas and response fields with the V1 spec, including citations/sources and degraded-state handling.
- Make config/data file resolution module-relative to support running from different working directories.

### Documentation
- Added architecture notes, API docs, and getting-started guides for V1.

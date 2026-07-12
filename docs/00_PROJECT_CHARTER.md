# TsumeVault Project Charter

Version: 1.0 (Draft)
Status: Active
Owner: Project Owner
Architecture Steward: ChatGPT
Last Updated: 2026-07-11

---

# 1. Mission

TsumeVault exists to become the best possible long-term personal study companion for Go players.
Its mission is to preserve knowledge, study history and learning progress over many years while remaining completely under the user's control.
TsumeVault is designed for longevity.
Every architectural decision should be evaluated according to one question:

> "Will this still be a good decision after ten years of daily use?"

If the answer is uncertain, the simpler solution should normally be preferred.

---

# 2. Vision

TsumeVault is not a web application.
TsumeVault is a personal desktop application that happens to run inside a browser.
This distinction is fundamental.
The browser is simply the runtime.
The application itself is:
- offline
- local
- personal
- self-contained

The server exists only to synchronize devices.
The server is never the center of the system.
The client is.

---

# 3. Core Philosophy

## 3.1 Offline First

Offline operation is the default operating mode.
Every feature must continue working without network connectivity unless the feature itself is synchronization.
Network connectivity is considered an enhancement, never a requirement.

---

## 3.2 User Ownership

The user owns every piece of data.
The application must never depend on an external service to access study history.
Backups must remain simple.
Data formats should remain understandable and portable.

---

## 3.3 Simplicity is a Feature

Complexity is treated as technical debt.
Every abstraction must justify its existence.
A simpler solution should always be preferred unless the more complex solution provides a measurable benefit.

---

## 3.4 Reliability Before Features

A missing feature is acceptable.
Corrupted data is not.
Lost study progress is not.
Incorrect synchronization is not.
When reliability conflicts with new functionality, reliability always wins.

---

## 3.5 Incremental Evolution

Large rewrites are discouraged.
The preferred approach is:
small change
↓
test
↓
verify
↓
commit
↓
repeat
Every completed task should leave the project in a deployable state.

---

# 4. Product Scope

TsumeVault is intended to solve one problem exceptionally well:
Studying Go problems over many years.
It is intentionally specialized.
Features should only be added if they directly improve this objective.

---

# 5. Non-Goals

TsumeVault is NOT intended to become:

- a SaaS platform
- a collaborative application
- a social network
- an online Go server
- a cloud-first application
- an enterprise product
- a framework for other applications

Avoid implementing infrastructure required only by those types of systems.

---

# 6. Architectural Principles

The following principles are mandatory.

## Principle 1

The local database is the primary source of truth.

---

## Principle 2

The synchronization server is a replication service.

It is not the owner of the data.

---

## Principle 3

Every synchronization operation should be safe to execute multiple times.

Synchronization should be idempotent whenever possible.

---

## Principle 4

No user action should require an active internet connection.

---

## Principle 5

Every schema evolution must preserve existing user data.

Deleting the database should never be the migration strategy.

---

## Principle 6

Small, understandable code is preferred over clever code.

---

## Principle 7

Debuggability is part of the architecture.

Logs, diagnostics and tests are first-class citizens.

---

# 7. Technical Direction

The following technologies are considered part of the project's identity.

Client

- HTML
- CSS
- Vanilla JavaScript
- sql.js

Server

- Python
- SQLite

Deployment

- Local
- Self-hosted

Introducing additional technologies requires clear justification.

---

# 8. Success Criteria

The project will be considered successful if:

✓ The user never loses study history.

✓ Synchronization remains reliable across devices.

✓ The application starts quickly.

✓ The codebase remains understandable.

✓ New contributors (human or AI) can understand the project quickly.

✓ The project is still maintainable after many years.

---

# 9. Decision Hierarchy

When two objectives conflict, they should be resolved in the following order.

1. Data Integrity
↓
2. Correctness
↓
3. Reliability
↓
4. Simplicity
↓
5. Maintainability
↓
6. Performance
↓
7. New Features

Performance improvements must never compromise correctness.

New features must never compromise data integrity.

---

# 10. Definition of Done

A task is considered complete only if all of the following are true.

- The feature works.
- Existing functionality still works.
- Existing databases continue working.
- No user data can be lost.
- The implementation is documented.
- The corresponding tests pass.
- The project remains deployable.

---

# 11. Long-Term Vision

The long-term objective is not to build the largest Go study application.

The objective is to build the most dependable one.

A future version of TsumeVault should still feel familiar.

Technology may evolve.

Artificial intelligence may evolve.

Programming languages may evolve.

The philosophy of the project should not.

This document defines that philosophy.
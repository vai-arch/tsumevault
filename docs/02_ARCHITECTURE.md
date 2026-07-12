# TsumeVault Architecture

Version: 1.0 (Draft)

Status: Living Document

Last Updated: 2026-07-11

---

# Purpose

This document explains how TsumeVault works.

It intentionally focuses on architecture and data flow instead of implementation details.

Reading this document should allow a developer—or an AI—to understand the system before reading a single line of code.

---

# System Overview

TsumeVault consists of two independent applications.

```
                +-------------------------+
                |      Web Browser        |
                |                         |
                |  HTML + JavaScript      |
                |  SQL.js                 |
                |                         |
                +-----------+-------------+
                            |
                     Synchronization
                            |
                            |
                +-----------v-------------+
                |      Python Server      |
                |                         |
                |        SQLite           |
                +-------------------------+
```

The browser is the primary application.

The server exists only to synchronize multiple devices.

---

# Primary Design Principle

The client owns the user experience.

The server owns persistence across devices.

The browser must continue working even if the server disappears forever.

This is the single most important architectural decision in TsumeVault.

---

# High Level Components

The client is responsible for:

- UI
- Study sessions
- Runs
- Attempts
- SM-2 scheduling
- Statistics
- Local database
- Synchronization requests

The server is responsible for:

- Receiving changes
- Persisting changes
- Returning changes
- Coordinating synchronization

Nothing else.

---

# Data Ownership

```
User

↓

Browser

↓

Local SQL.js database

↓

Synchronization

↓

Server SQLite
```

The local database is the operational database.

The server database is the synchronization database.

The server must never become the only copy of user information.

---

# Data Flow

## Solving a Problem

The normal workflow is:

```
User solves problem

↓

Attempt is created

↓

Run is updated

↓

SM-2 state is recalculated

↓

Statistics are updated

↓

Database is saved

↓

Synchronization is scheduled
```

Everything before synchronization happens locally.

---

# Offline Operation

Offline mode is the normal operating mode.

Every feature except synchronization should continue working.

Network availability must never affect study sessions.

---

# Synchronization Philosophy

Synchronization is asynchronous.

Studying must never wait for synchronization.

Synchronization must never block the user interface.

If synchronization fails:

- studying continues

- synchronization is retried later

---

# Synchronization Model

Synchronization consists of two independent operations.

```
Push

Client

--------->

Server


Pull

Client

<---------

Server
```

These operations should remain conceptually independent.

Avoid mixing their responsibilities.

---

# Data Lifecycle

Every important entity follows the same lifecycle.

```
Create

↓

Modify

↓

Synchronize

↓

Persist

↓

Remain available forever
```

Deletion should be exceptional.

Historical information is valuable.

---

# Persistence

The browser should assume that it may close unexpectedly.

Therefore:

Every important modification should eventually reach persistent storage.

Saving should never depend on the user explicitly pressing a button.

---

# Reliability Goals

The following events should never cause data loss:

- Browser refresh

- Browser crash

- Power failure

- Temporary network loss

- Server restart

---

# Error Philosophy

Failures are expected.

The application should recover whenever possible.

Unexpected situations should generate diagnostics rather than silent failures.

---

# Database Strategy

The project intentionally uses two databases.

Client

Operational database

Optimized for responsiveness.

Server

Synchronization database

Optimized for persistence.

These databases are expected to converge after synchronization.

---

# Consistency Model

Perfect real-time consistency is NOT required.

Eventual consistency IS required.

After successful synchronization all devices should converge to the same state.

---

# Performance Philosophy

Correctness

↓

Reliability

↓

Maintainability

↓

Performance

Performance optimizations are welcome only after correctness has been preserved.

---

# Architectural Boundaries

Client responsibilities must remain inside the client.

Server responsibilities must remain inside the server.

Avoid moving business logic to the server unless absolutely necessary.

---

# Expected Evolution

The architecture is intentionally conservative.

Future improvements should:

- preserve simplicity

- preserve compatibility

- preserve offline capability

The architecture should evolve gradually.

Large rewrites are discouraged.

---

# What Must Never Change

The following principles define the identity of TsumeVault.

✓ Offline First

✓ Local-first operation

✓ Single-user design

✓ Small codebase

✓ No unnecessary frameworks

✓ Simple deployment

✓ Data integrity above all

Any proposal violating one of these principles requires explicit architectural approval.
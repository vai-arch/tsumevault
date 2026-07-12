# AI Manifest

Version: 1.0 (Draft)

Status: Active

Owner: Project Owner

Applies To:
- ChatGPT
- Claude / Sonnet
- Codex
- Cursor
- Gemini
- Any future AI contributor

---

# Purpose

This document defines the mandatory engineering rules that every AI must follow when contributing to TsumeVault.

These rules exist to protect the project from unnecessary complexity, accidental regressions and uncontrolled architectural drift.

If a requested implementation conflicts with this document, the AI must explicitly explain the conflict before continuing.

---

# First Principle

An AI is an implementation assistant.

It is NOT the architect.

Architectural decisions belong to the project.

The AI must preserve the architecture unless explicitly instructed otherwise.

---

# Golden Rules

## Rule 1

Never lose user data.

This rule overrides every other objective.

---

## Rule 2

Never make architectural changes unless explicitly requested.

Do not reorganize the project.

Do not split files.

Do not introduce frameworks.

Do not redesign components.

Implement only the requested task.

---

## Rule 3

Keep the project simple.

Do not introduce abstractions without measurable benefit.

Avoid patterns whose only advantage is theoretical elegance.

---

## Rule 4

Respect the existing coding style.

When adding new code, follow the project's conventions instead of introducing personal preferences.

---

## Rule 5

One task = One objective.

Never combine:

- refactoring
- bug fixes
- new features
- architectural improvements

inside the same implementation.

---

## Rule 6

Do not "improve" code unless asked.

If code works correctly and is understandable, leave it alone.

---

## Rule 7

Do not rename public functions without explicit permission.

Existing APIs are considered stable.

---

## Rule 8

Backward compatibility is mandatory.

Existing databases must continue working whenever reasonably possible.

---

## Rule 9

If a migration is required:

- explain why
- explain the impact
- explain the rollback

before implementing it.

---

## Rule 10

Every implementation must leave the project in a working state.

Never leave partially completed work.

---

# Working Method

Every task should follow this sequence.

Understand

↓

Analyze

↓

Plan

↓

Implement

↓

Review

↓

Test

↓

Deliver

Never skip a step.

---

# Scope Control

Before modifying code, identify:

Files to modify.

Files that must remain untouched.

Dependencies.

Potential side effects.

If the task appears larger than expected, stop and explain why.

Do not silently expand the scope.

---

# Code Generation Principles

Generated code should be:

Readable.

Predictable.

Explicit.

Maintainable.

Avoid clever solutions.

Avoid hidden behavior.

Avoid unnecessary metaprogramming.

---

# Error Handling

Errors should never be silently ignored.

Every failure should either:

- recover safely

or

- produce useful diagnostic information.

---

# Synchronization Rules

Synchronization is the most critical subsystem.

Any modification affecting synchronization requires special care.

The AI must assume:

multiple devices

network interruptions

duplicate requests

partial synchronization

unexpected shutdowns

Therefore:

Synchronization should be idempotent whenever possible.

Operations should be repeatable.

Duplicate processing should not corrupt data.

---

# Database Rules

Never destroy existing data.

Never delete tables as a migration strategy.

Prefer additive migrations.

Always preserve compatibility whenever possible.

---

# Testing Requirements

Every task must include a testing strategy.

If automated tests are unavailable, provide manual verification steps.

Synchronization changes require multi-device testing.

Persistence changes require restart testing.

Migration changes require upgrade testing.

---

# Documentation Requirements

Every non-trivial implementation must update documentation when appropriate.

Architecture changes require updating:

Architecture.md

Execution Plan

Relevant ADRs

Implementation Status

---

# Communication Style

When delivering work, always include:

Objective

Files modified

Summary of changes

Known limitations

Testing performed

Remaining risks

This information is mandatory.

---

# Forbidden Behaviors

Never introduce frameworks without approval.

Never perform speculative optimizations.

Never rewrite large portions of code.

Never mix unrelated improvements.

Never silently change architecture.

Never remove compatibility.

Never remove logging during debugging.

Never delete comments that explain important decisions.

---

# Escalation Rules

If the AI detects:

large architectural inconsistencies

contradictory requirements

potential data loss

unclear specifications

unexpected complexity

it must stop and request clarification.

Guessing is forbidden.

---

# Definition of Success

A successful implementation is not measured by:

lines of code

number of changes

amount of refactoring

A successful implementation is measured by:

minimal risk

predictable behavior

maintainability

clarity

correctness

long-term stability

---

# Final Principle

TsumeVault is expected to evolve for many years.

Every AI contributes only a small part of that journey.

The responsibility of the AI is not to demonstrate intelligence.

Its responsibility is to preserve the integrity of the project.
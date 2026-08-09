# Atlas AI — Schema Module (Pydantic Request/Response Models)

## Overview

This module is a collection of six independent Pydantic `BaseModel` schema files. Each defines the request and/or response shape for a specific area of the Atlas AI API surface: user authentication, tenant (SaaS) registration, invitations, file upload/ingestion, RAG queries, and evaluation pipeline input. No shared base class, router, or business logic is present — these are pure data-contract definitions with field-level validation.

**Provided code:** `auth_admin.py` (20 lines), `invitation_requests.py` (137 lines), `tenant_schema.py` (22 lines), `upload_request.py` (11 lines), `query_request.py` (14 lines), `eval_pipline.py` (11 lines). No `README.md` was included in this zip.

**Not provided:** the FastAPI routes that consume these schemas, the ORM/database models they map to or from, `IngestController`, `EvalPipeline`/evaluation service code, JWT/auth-dependency implementations, and the invitation service/repository layer. This document describes only the data contracts themselves — field names, types, constraints, defaults, and any validation logic physically present in these six files.

---

## Responsibilities

* Define and validate the shape of incoming request bodies for six areas of functionality: admin/user auth, tenant registration, invitations, file upload, RAG queries, and evaluation runs.
* Define the shape of corresponding response bodies where applicable (auth token, tenant registration, invitation details).
* Enforce field-level constraints (length limits, email format, optional/required, defaults) via Pydantic.
* Normalize one non-trivial input shape variance (`RegisterViaInvitationRequest`'s nested-vs-flat token payload) via a `model_validator`.

## Boundaries

* No schema in this module performs database access, network calls, or business logic beyond field validation/normalization.
* No schema defines authorization rules — comments indicate some values (e.g. `tenant_id` in `SendInvitationRequest`) are expected to be *ignored* and derived server-side from a JWT, but the derivation itself is not in this module.
* No ORM models are defined here — `InvitationResponse`'s `from_attributes = True` config indicates it is meant to be constructed from an ORM object, but that ORM model is not provided.

---

## Project Structure

```
schema/
├── auth_admin.py          # UserCreate, Token, UserLogin
├── invitation_requests.py # SendInvitationRequest, InvitationResponse,
│                           # ValidateInvitationRequest, InvitationDetailsResponse,
│                           # RegisterViaInvitationRequest, ResendInvitationRequest,
│                           # PendingInvitationsResponse, ResendInvitationResponse
├── tenant_schema.py        # TenantRegistrationRequest, TenantRegistrationResponse
├── upload_request.py       # UploadRequest
├── query_request.py        # QueryRequest
└── eval_pipline.py         # EvalPipelineInput
```

---

## File-by-File Explanation

### `auth_admin.py`

**Responsibility:** Request/response models for user creation, login, and token issuance.

| Model | Fields | Notes |
|---|---|---|
| `UserCreate` | `email: EmailStr`, `password: str` (8–128 chars), `name: str` (1–100 chars, whitespace-stripped), `tenant_name: str` (2–100 chars, whitespace-stripped) | Used presumably for signup; requires a `tenant_name`, implying user creation is tied to a tenant context (not confirmed by code outside this file) |
| `Token` | `access_token: str`, `token_type: str` | No default for `token_type` (e.g. `"bearer"` is not hardcoded here) |
| `UserLogin` | `email: EmailStr`, `password: str` (8–128 chars) | Same password length constraint as `UserCreate` |

**Dependencies:** `pydantic.BaseModel`, `EmailStr` (email format validation — requires the `email-validator` package, per Pydantic convention), `Field`.

### `invitation_requests.py`

**Responsibility:** The full set of request/response models for an invitation-based user-onboarding flow (send, validate, register-via-invitation, resend, list pending).

| Model | Fields | Notes |
|---|---|---|
| `SendInvitationRequest` | `invited_email: EmailStr`, `tenant_id: Optional[str] = None` | Docstring/inline comment states `tenant_id` is "Ignored — derived from the admin's JWT token server-side" — i.e., even if a client supplies it, the field is documented as not authoritative. This enforcement itself happens outside this file. |
| `InvitationResponse` | `invitation_id: str`, `invited_email: str`, `status: str`, `created_at: datetime`, `expires_at: datetime`, `token: Optional[str] = None` | `from_attributes = True` allows direct construction from an ORM object. Comment (in Arabic) explains this lets Pydantic convert an ORM object (e.g. SQLAlchemy) directly into the Pydantic model. `token` is documented as "Only included when first created" — i.e., callers reconstructing this model in other contexts (e.g. listing) are expected to omit it. |
| `ValidateInvitationRequest` | `token: str` | — |
| `InvitationDetailsResponse` | `invited_email: str`, `tenant_id: str`, `created_at: str`, `expires_at: str`, `is_expired: bool` | Note: unlike `InvitationResponse`, timestamps here are typed as plain `str`, not `datetime` — an inconsistency between the two response models for what look like related invitation timestamp fields. |
| `RegisterViaInvitationRequest` | `token: str`, `password: str`, `name: Optional[str] = None`, `tenant_id: Optional[str] = None` | See validator below. |
| `ResendInvitationRequest` | `token: str` | — |
| `PendingInvitationsResponse` | `total: int`, `invitations: list[InvitationResponse]` | — |
| `ResendInvitationResponse` | `success: bool`, `message: str`, `new_token: Optional[str] = None` | — |

**`RegisterViaInvitationRequest.normalize_token_shape` (model_validator, mode="before"):**

This is the only non-trivial validation logic in the whole module. It runs before standard field validation and:

1. Checks if the incoming `token` value is itself a `dict` (i.e., the client sent a nested object like `{"token": {"token": "...", "password": "..."}}`).
2. If so, unwraps it: pulls `token`, `password`, `name`, and `tenant_id` out of the nested dict, but only as a fallback for whichever of the top-level values are falsy (`values.get(...) or tok.get(...)`).
3. Explicitly raises `ValueError("Missing required field: token")` or `ValueError("Missing required field: password")` if those are still absent after normalization — a deliberate, early, more specific error than Pydantic's default "field required" message.

This validator exists to support two documented client payload shapes (flat and nested) for the same endpoint, per the model's docstring.

**Dependencies:** `pydantic.BaseModel`, `EmailStr`, `model_validator`; `datetime.datetime`; `typing.Optional`.

### `tenant_schema.py`

**Responsibility:** Request/response models for SaaS tenant (organization) self-registration.

| Model | Fields | Notes |
|---|---|---|
| `TenantRegistrationRequest` | `organization_name: str`, `admin_email: str`, `admin_password: str`, `admin_name: str = "Admin"`, `plan: str = "starter"` | `admin_email` is typed as plain `str`, **not** `EmailStr` — unlike `UserCreate`/`UserLogin`/`SendInvitationRequest` in the other files, so no format validation is enforced on this field by Pydantic itself. No length constraints on `admin_password` here either (contrast with `auth_admin.py`'s 8–128 char constraint on password fields). |
| `TenantRegistrationResponse` | `tenant_id: str`, `admin_id: str`, `organization_name: str`, `access_token: str`, `message: str`, `plan: str = "starter"` | Returns an `access_token` directly in the registration response, implying tenant registration also logs the new admin in (this is an inference from the field's presence, not confirmed by route code, which is not provided). |

**Dependencies:** `pydantic.BaseModel` only.

### `upload_request.py`

**Responsibility:** Request model for the file/folder upload-and-ingest endpoint.

| Model | Fields | Notes |
|---|---|---|
| `UploadRequest` | `file_path: str`, `tenant_id: str`, `source: str`, `author: str`, `recursive: Optional[bool] = False`, `file_extensions: Optional[List[str]] = None` | Field names line up closely with the parameters accepted by `FolderProcessor`/`process_upload` from the previously-reviewed `design_pattern` module (`file_path`, `tenant_id`, `source`, `author`, `recursive`, `file_extensions`) — this schema appears to be the HTTP-layer contract for that ingestion code, though the actual route wiring is not present in this zip. |

**Dependencies:** `pydantic.BaseModel`, `typing.Optional`, `typing.List`.

### `query_request.py`

**Responsibility:** Request model for RAG query endpoints.

| Model | Fields | Notes |
|---|---|---|
| `QueryRequest` | `query: str` (required, 1–2000 chars, whitespace-stripped), `session_id: str \| None` (optional, 1–128 chars if present) | Uses PEP 604 `str \| None` union syntax rather than `Optional[str]`, inconsistent with the `Optional[...]` style used in every other file in this module. `query`'s max length (2000 chars) is the only explicit upper bound on user-supplied free text across all six files. |

**Dependencies:** `pydantic.BaseModel`, `Field`.

### `eval_pipline.py`

**Responsibility:** Input schema for triggering an evaluation pipeline run.

| Model | Fields | Notes |
|---|---|---|
| `EvalPipelineInput` | `tenant_id: str`, `file: str`, `runs: int` | No constraints on `runs` (e.g. no minimum/maximum), so 0, negative, or arbitrarily large values are not rejected by this schema. `file` is untyped beyond `str` — no path or extension validation. |

**Dependencies:** `pydantic.BaseModel` only.

---

## Data Flow

These are pure input/output contracts; there is no processing pipeline within this module itself. Their place in a request lifecycle (inferred from naming and field overlap with previously-reviewed modules, not confirmed here):

```text
HTTP Request Body (JSON)
        │
        ▼
Pydantic model parses + validates fields
        │  (raises 422-style validation error on failure — enforced by
        │   whatever framework, e.g. FastAPI, consumes this model;
        │   Not enough information from the provided code confirming FastAPI)
        ▼
Validated model instance passed into route/controller/service (Not provided)
        │
        ▼
Response constructed from a corresponding *Response model, if applicable
```

Two `Config`-based JSON schema examples (`SendInvitationRequest`, `ValidateInvitationRequest`, `InvitationDetailsResponse`, `ResendInvitationRequest`) exist purely for OpenAPI documentation (`json_schema_extra`) — they do not affect runtime validation.

---

## External Dependencies

| Dependency | Purpose | Where Used | Required? |
|---|---|---|---|
| `pydantic` (`BaseModel`, `Field`, `EmailStr`, `model_validator`) | Schema definition and validation | All six files | Yes |
| `email-validator` (implicit, required by `EmailStr`) | Email format validation | `auth_admin.py`, `invitation_requests.py` | Yes, wherever `EmailStr` is used |
| Python `datetime` | Typed timestamp fields | `invitation_requests.py` (`InvitationResponse`) | Yes |
| Python `typing` (`Optional`, `List`) | Optional/list field typing | `invitation_requests.py`, `upload_request.py` | Yes |

No database, cache, LLM, or vector-store dependency exists in this module — it is pure schema definition.

---

## Configuration

No environment variables, settings objects, or credentials appear anywhere in this module.

---

## Error Handling

Pydantic's standard validation error behavior applies to every model (e.g. missing required fields, type mismatches, out-of-range string lengths). The only custom validation logic is `RegisterViaInvitationRequest.normalize_token_shape`, which raises `ValueError` with explicit messages (`"Missing required field: token"`, `"Missing required field: password"`) for two specific missing-field cases, after attempting to unwrap a nested token payload. No other file adds custom validators, `@field_validator`, or `@model_validator` logic.

---

## Security

* Password fields in `auth_admin.py` (`UserCreate.password`, `UserLogin.password`) enforce an 8–128 character length via `Field(..., min_length=8, max_length=128)` — this is a presence/length check only; no complexity rules (uppercase, digits, symbols) are enforced by Pydantic here.
* `TenantRegistrationRequest.admin_password` has **no length or complexity constraint at all** — inconsistent with the password fields in `auth_admin.py`.
* Email fields are validated for format via `EmailStr` in `auth_admin.py` and `invitation_requests.py`'s `SendInvitationRequest`, but `TenantRegistrationRequest.admin_email` is plain `str` — format is not validated at the schema layer for tenant self-registration.
* `SendInvitationRequest.tenant_id` is documented (via comment) as ignored in favor of a server-derived value from the JWT — this is a documented security-relevant design decision (preventing a client from specifying an arbitrary `tenant_id` to invite users into a tenant they don't administer), but the actual enforcement is `Not implemented / not visible in the provided code` since no route or JWT-handling code is included.
* `RegisterViaInvitationRequest` similarly accepts an optional client-supplied `tenant_id`, with the docstring stating it "will be extracted from the invitation record if not provided" — implying the invitation record, not the client, is the authoritative source, though again the enforcement code is not provided.
* No rate-limiting, CSRF, or injection-specific validation is present in any of these schemas — they perform structural/type validation only.

---

## Data Model Inconsistencies (Observed, Not Assumed)

These are factual observations from comparing the six files directly, not inferred design intent:

| Inconsistency | Detail |
|---|---|
| Password constraints | `UserCreate`/`UserLogin` (8–128 chars) vs. `TenantRegistrationRequest.admin_password` (no constraint) |
| Email typing | `EmailStr` used in `auth_admin.py` and `SendInvitationRequest`, but plain `str` used for `TenantRegistrationRequest.admin_email` |
| Optional syntax | `Optional[X]` used throughout, except `query_request.py` which uses `X \| None` |
| Timestamp typing | `InvitationResponse` uses `datetime` for `created_at`/`expires_at`; `InvitationDetailsResponse` uses `str` for the same conceptual fields |
| Numeric constraints | `EvalPipelineInput.runs: int` has no min/max bound, unlike the string length bounds applied elsewhere in the module |

---

## Testing

No tests were provided in the analyzed code.

---

## Deployment

Not applicable — this module contains no runnable service, entrypoint, or deployment-relevant configuration. `Not enough information from the provided code` regarding which web framework (e.g. FastAPI) consumes these models at runtime, though the `Config.json_schema_extra` pattern is idiomatic for FastAPI/OpenAPI documentation generation.

---

## Known Limitations

### Confirmed Limitations
* `TenantRegistrationRequest.admin_password` has no minimum length or complexity enforcement, unlike equivalent password fields elsewhere in this module.
* `TenantRegistrationRequest.admin_email` is not validated as an email format (plain `str`), unlike other email fields in this module.
* `EvalPipelineInput.runs` accepts any integer, including zero or negative values, with no bound enforced at the schema layer.
* Timestamp field typing is inconsistent between `InvitationResponse` (`datetime`) and `InvitationDetailsResponse` (`str`) for conceptually equivalent fields.

### Potential Risks / Improvements
* Consider aligning `TenantRegistrationRequest.admin_password` with the same `min_length=8, max_length=128` constraint used in `auth_admin.py`, since tenant registration also creates an admin credential.
* Consider using `EmailStr` for `TenantRegistrationRequest.admin_email` for consistency and format validation.
* Consider adding a lower bound (e.g. `ge=1`) to `EvalPipelineInput.runs` if zero/negative run counts are not meaningful.
* Consider standardizing on either `Optional[X]` or `X | None` syntax across the module for consistency.

---

## Summary

This module defines the Pydantic data contracts for six areas of the Atlas AI API: admin/user authentication (`UserCreate`, `Token`, `UserLogin`), tenant self-registration (`TenantRegistrationRequest`/`Response`), a full invitation lifecycle (send, validate, register-via-invitation with dual-shape input normalization, resend, list pending), file/folder upload requests (`UploadRequest`, matching field names used by the previously-reviewed `design_pattern` ingestion code), RAG query input (`QueryRequest`), and evaluation pipeline input (`EvalPipelineInput`). The only non-trivial logic in the module is `RegisterViaInvitationRequest`'s `model_validator`, which normalizes two accepted client payload shapes and raises explicit errors for missing `token`/`password`. Several field-level inconsistencies exist across files (password/email validation strictness, `Optional` syntax, timestamp typing, absence of numeric bounds) that are documented above as confirmed, code-level observations rather than assumed defects.
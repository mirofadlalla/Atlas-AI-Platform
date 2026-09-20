# Atlas AI Frontend

### Production-Oriented React Interface for Enterprise Agentic AI

A modern, responsive frontend for **Atlas AI Platform**, an enterprise-grade, multi-tenant Agentic AI system that combines Retrieval-Augmented Generation (RAG), hybrid search, SQL querying, document reranking, and AI-powered analytics.

Built with React 18, the frontend provides an integrated workspace for querying knowledge bases, managing documents, monitoring AI usage, evaluating retrieval quality, and administering tenant users.

The interface was refined through a comprehensive frontend audit focused on **accessibility, maintainability, consistency, and production-oriented UI engineering.**

---

## ✨ Core Capabilities

### 🤖 AI Interaction

* Real-time Agentic AI query interface.
* Streaming responses with automatic scrolling.
* Hybrid document retrieval and reranking visualization.
* Semantic, lexical, and combined retrieval scores.
* Recommended questions and interactive query workflows.
* Agent execution status and thought-process visualization.

### 📚 Knowledge Management

* File ingestion and document indexing.
* Recursive directory ingestion support.
* Document metadata and source tracking.
* Tenant database connection management.
* Schema inspection and relationship visualization.

### 📊 Evaluation & Observability

* RAG pipeline evaluation interface.
* Precision@K, Recall@K, F1, and MRR metrics.
* Token usage and cost analytics.
* Query latency and cache performance tracking.
* MLflow dashboard integration.

### 🔐 Authentication & Administration

* JWT-based authentication.
* Invitation-based registration.
* User approval workflows.
* Role-based interface rendering.
* Tenant-aware application workflows.
* Administrative management of invitations, users, and Q&A records.

---

## 🏗️ Frontend Architecture

The frontend follows a modular React architecture that separates application logic, reusable UI components, API communication, and page-level functionality.

```text
frontend/
│
├── public/
│   └── index.html
│
├── src/
│   ├── index.js
│   ├── index.css
│   ├── App.jsx
│   ├── App.css
│   │
│   ├── services/
│   │   └── apiService.js
│   │
│   ├── styles/
│   │   ├── theme.css
│   │   └── animations.css
│   │
│   ├── components/
│   │   ├── Navigation.jsx
│   │   ├── ProtectedRoute.jsx
│   │   ├── Toast.jsx
│   │   ├── Modal.jsx
│   │   ├── Spinner.jsx
│   │   ├── EmptyState.jsx
│   │   └── ...
│   │
│   └── pages/
│       ├── LoginPage.jsx
│       ├── RegisterPage.jsx
│       ├── DashboardPage.jsx
│       ├── QueryPage.jsx
│       ├── AgentPage.jsx
│       ├── IngestPage.jsx
│       ├── EvaluationPage.jsx
│       ├── CostAnalyticsPage.jsx
│       ├── AdminPanel.jsx
│       ├── TenantDatabasePage.jsx
│       └── ...
│
├── package.json
├── .env.example
└── README.md
```

### Architectural Principles

* Separation of shared components and page-specific logic.
* Centralized API communication.
* Reusable design tokens and styling utilities.
* Consistent feedback and error-handling patterns.
* Responsive and accessible interface components.
* Role-aware navigation and UI rendering.

---

# 🎨 Design System & UI Engineering

The frontend uses a centralized CSS token system to maintain consistent styling across the application.

### Design System Improvements

* Centralized colors, backgrounds, and semantic states.
* Consistent spacing and component styling.
* Dark-theme compatibility across application pages.
* Responsive layouts for desktop, tablet, and mobile.
* Reusable utility classes.
* Reduced reliance on hardcoded CSS values.

### Responsive Navigation

The navigation system supports:

* Active route highlighting through React Router `NavLink`.
* Responsive hamburger menu.
* Mobile navigation transitions.
* Accessible ARIA attributes.
* Separation between standard and administrative links.
* User-friendly display names.

---

# 🛠️ Frontend Audit & Engineering Improvements

A comprehensive audit was performed across the frontend, resulting in **45 implemented fixes**.

The work focused on addressing inconsistencies, accessibility issues, duplicated styles, and maintainability problems.

> The following improvements describe the implemented changes and build verification, rather than claiming that every possible production or security issue has been eliminated.

## 1. Reusable UI Components

Introduced shared components to replace inconsistent browser-native interactions.

| Component    | Responsibility                     |
| ------------ | ---------------------------------- |
| `Toast`      | Application-wide notifications     |
| `Modal`      | Reusable confirmation dialogs      |
| `Spinner`    | Consistent loading states          |
| `EmptyState` | Standardized empty-content layouts |

### Toast Notification System

Replaced scattered `alert()` calls with a context-based notification system.

```jsx
const { showToast } = useToast();

showToast("Operation completed successfully", "success");
```

Supported variants:

* Success
* Error
* Warning
* Info

The notification system includes configurable auto-dismiss behavior and accessibility attributes.

### Modal System

Replaced `window.confirm()` with a reusable dialog component supporting:

* Confirmation workflows.
* Destructive-action variants.
* Escape-key dismissal.
* Backdrop dismissal.
* Focus management.
* Body scroll locking.

---

## 2. Accessibility Improvements

The audit introduced accessibility-focused improvements throughout the interface.

### Implemented Improvements

* Added accessible labels to form inputs and interactive controls.
* Added ARIA roles for tabs, alerts, and loading states.
* Added navigation landmark labeling.
* Added keyboard-oriented modal interactions.
* Improved error message announcements.
* Added accessible loading indicators.
* Scoped global CSS selectors affecting form elements.
* Improved color contrast for muted text.

### Example

```jsx
<div role="alert" aria-live="assertive">
  {errorMessage}
</div>
```

**Accessibility Note:** The changes improve accessibility patterns, but a complete WCAG compliance claim requires broader automated and manual testing across the application.

---

## 3. CSS & Maintainability Improvements

### Problems Addressed

* Duplicate CSS blocks.
* Conflicting style definitions.
* Undefined CSS tokens.
* Unscoped form selectors.
* Duplicate animations.
* Hardcoded theme colors.
* Unnecessary focus transformations.
* Inline styles in reusable UI sections.

### Key Improvements

* Centralized design tokens in `theme.css`.
* Removed duplicate blocks from `index.css` and `Navigation.css`.
* Removed duplicate `slideUp` keyframes.
* Fixed conflicting transition declarations.
* Replaced hardcoded semantic colors with design tokens.
* Scoped page-specific form styling.
* Improved component-level CSS organization.

These changes reduce styling conflicts and make future UI maintenance more predictable.

---

# 🔐 Authentication & Access Control

The frontend integrates with the Atlas AI backend authentication system.

### Authentication Flow

```text
User
 │
 ▼
Login / Invitation Registration
 │
 ▼
Backend Authentication
 │
 ▼
JWT Token
 │
 ▼
Session Persistence
 │
 ▼
Protected Routes
 │
 ▼
Role-Aware Interface
```

### Supported Workflows

* Login with email and password.
* Invitation-based registration.
* User approval workflows.
* JWT-based request authentication.
* Protected routes.
* Admin-only interface sections.

### API Integration

The frontend uses a unified API service for backend communication.

```javascript
apiService.login(email, password);

apiService.askQuery(query);

apiService.retrieveDocuments(query, top_k);

apiService.getCostAnalytics();

apiService.getPendingApprovals();
```

**Security Consideration:** JWT persistence and frontend role-based rendering support the user experience, but backend authorization must independently validate tokens, roles, and tenant boundaries. Frontend headers should not be treated as a trusted authorization mechanism.

---

# 📈 RAG Query Experience

The Query and Agent pages provide an interface for interacting with the backend's AI workflows.

### Query Workflow

```text
User Query
    │
    ▼
Frontend Request
    │
    ▼
Backend Agent / Retrieval Pipeline
    │
    ▼
Hybrid Retrieval
    │
    ▼
Document Reranking
    │
    ▼
Generated Response
    │
    ▼
Streaming UI
```

### Retrieval Visualization

The interface can display retrieval-related scoring information, including:

* Original retrieval score.
* Reranking score.
* Combined score.
* Document metadata.
* Retrieved document content.

The UI also handles missing reranking scores through defensive null handling.

```javascript
const score = (doc.rerank_score ?? 0) * 100;
```

---

# 📊 Evaluation & Cost Analytics

The frontend includes dedicated interfaces for monitoring and evaluating AI workflows.

### Evaluation Metrics

* Precision@K
* Recall@K
* F1 Score
* Mean Reciprocal Rank (MRR)
* Jaccard Stability
* Token F1

### Cost Analytics

* Total usage cost.
* Average cost per query.
* Model-level cost breakdown.
* Input and output token tracking.
* Query latency.
* Cache hit-rate monitoring.
* Optimization recommendations.

The accuracy and reliability of these metrics depend on the backend's measurement and tracking implementation.

---

# 🧪 Verification & Build Quality

The frontend audit was followed by a production build verification.

### Build Result

```text
Compiled with warnings.

Exit Code: 0

JavaScript (Gzip): 70.46 kB
CSS (Gzip):         11.17 kB
```

The build completed successfully with two pre-existing warnings.

### Audit Verification

| Area                      | Result                            |
| ------------------------- | --------------------------------- |
| Production build          | ✅ Successful                      |
| Duplicate CSS blocks      | ✅ Addressed                       |
| Undefined CSS tokens      | ✅ Addressed                       |
| Browser alert calls       | ✅ Removed                         |
| Browser confirm calls     | ✅ Removed                         |
| Shared Toast system       | ✅ Integrated                      |
| Shared Modal system       | ✅ Integrated                      |
| Shared Spinner system     | ✅ Integrated                      |
| Active navigation state   | ✅ Implemented                     |
| Responsive hamburger menu | ✅ Implemented                     |
| Form styling scope        | ✅ Improved                        |
| Accessibility attributes  | ✅ Added across audited components |
| Main landmarks            | ✅ Added to audited pages          |

---

# 🚀 Getting Started

## Prerequisites

* Node.js 16+
* npm 8+
* Running Atlas AI Backend
* Modern web browser

## Installation

```bash
cd frontend

npm install
```

## Environment Configuration

Create a local environment file:

```bash
cp .env.example .env
```

Example configuration:

```env
REACT_APP_API_URL=http://localhost:8000/api

REACT_APP_ENABLE_RERANKING=true

REACT_APP_ENABLE_EVALUATION=true

REACT_APP_ENABLE_ANALYTICS=true
```

## Start Development Server

```bash
npm start
```

Application:

```text
http://localhost:3000
```

## Production Build

```bash
npm run build
```

## Available Scripts

```bash
npm start
npm run build
npm test
npm eject
```

---

# 🐳 Deployment

The application supports a standard React production build workflow.

```text
Source Code
    │
    ▼
npm install
    │
    ▼
npm run build
    │
    ▼
build/
    │
    ▼
Static Web Server / Hosting
```

For production deployment, the generated `build/` directory can be served through a suitable static web server or hosting platform.

**Deployment Considerations:**

* Configure the production API URL.
* Enable HTTPS.
* Configure backend CORS policies.
* Review authentication token handling.
* Configure appropriate caching headers.
* Validate production error handling.

---

# 🔗 Atlas AI Ecosystem

This frontend is part of the broader Atlas AI Platform.

### Backend Capabilities

* FastAPI backend.
* Agentic workflow orchestration.
* Hybrid retrieval.
* SQL generation and querying.
* Multi-tenant architecture.
* Vector search.
* Redis-based caching.
* Background task processing.
* Observability and evaluation.

### Frontend Responsibilities

* User interaction.
* AI query experience.
* Document management.
* Administrative workflows.
* Analytics visualization.
* Evaluation interface.
* Authentication state and route handling.

---

# 🧠 Engineering Focus

This project demonstrates practical frontend engineering within an AI application ecosystem.

Key areas of focus:

* React component architecture.
* API-driven application design.
* AI product interfaces.
* RAG workflow visualization.
* Accessibility-conscious UI development.
* CSS architecture and design systems.
* Error handling and user feedback.
* Multi-tenant application workflows.
* Production build validation.

---

# 📌 Project Status

**Status:** Active Development

The frontend has undergone a comprehensive audit and implementation pass covering 45 reported issues.

The successful production build confirms that the current changes compile successfully. Further production validation should include end-to-end testing, security testing, browser compatibility checks, and deployment verification.

---

### Built With

**React 18 • JavaScript • CSS • REST APIs • JWT • RAG • Agentic AI**

**Part of the Atlas AI Platform — Enterprise AI Infrastructure.**

---
# atlas-ai-frontend
# atlas-ai-frontend

"""Create standard 0-to-100 project template files for DevPilot & Jarvis."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultnotes import VAULT
BASE = VAULT / "_DevPilot" / "Templates" / "project"
BASE.mkdir(parents=True, exist_ok=True)

files = {}

files["PROJECT.md"] = """# {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 intake |
| Date | {{DATE}} |
| Goal | {{GOAL}} |

## Phase Checklist
- [ ] 1. INTAKE & PRD — Product Agent → docs/product/PRD.md
- [ ] 2. RESEARCH — Research Agent → docs/research/BRIEF.md
- [ ] 3. REFERENCES — Reference Agent → docs/references/REFERENCES.md
- [ ] 4. DESIGN — Design Agent → docs/design/DESIGN_SYSTEM.md & docs/design/DESIGN.md
- [ ] 5. ARCHITECTURE — Architect Agent → docs/architecture/SYSTEM_DESIGN.md
- [ ] 6. PLAN — Planner Agent → docs/plan/PLAN.md
- [ ] 7. BUILD & QA — Build Agent & QA Agent (milestones M1..Mn)
- [ ] 8. DEVOPS — DevOps Agent → Dockerfile, docker-compose.yml, docs/devops/DEPLOYMENT.md
- [ ] 9. SEO — SEO Agent → docs/seo/AUDIT.md, sitemap.xml, robots.txt
- [ ] 10. MARKETING — Marketing Agent → docs/marketing/STRATEGY.md
- [ ] 11. CONTENT — Content Agent → docs/content/COPY_AND_DOCS.md
- [ ] 12. PRODUCTION — Production Agent → docs/production/RELEASE_RUNBOOK.md

## Log
| Date | Agent | Entry |
|---|---|---|
| {{DATE}} | Orchestrator | Project initialized: {{SLUG}} ({{TITLE}}) |
"""

files["README.md"] = """# {{TITLE}}

{{GOAL}}

## Quick Start
```sh
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Run tests
npm test
```

## Documentation
- Product Requirements: [docs/product/PRD.md](docs/product/PRD.md)
- Market Research: [docs/research/BRIEF.md](docs/research/BRIEF.md)
- Design System: [docs/design/DESIGN_SYSTEM.md](docs/design/DESIGN_SYSTEM.md)
- System Architecture: [docs/architecture/SYSTEM_DESIGN.md](docs/architecture/SYSTEM_DESIGN.md)
- Master Plan: [docs/plan/PLAN.md](docs/plan/PLAN.md)
- QA Report: [docs/qa/REPORT.md](docs/qa/REPORT.md)
- DevOps & Docker: [docs/devops/DEPLOYMENT.md](docs/devops/DEPLOYMENT.md)
- Production Runbook: [docs/production/RELEASE_RUNBOOK.md](docs/production/RELEASE_RUNBOOK.md)
- Marketing & GTM: [docs/marketing/STRATEGY.md](docs/marketing/STRATEGY.md)
- SEO Audit: [docs/seo/AUDIT.md](docs/seo/AUDIT.md)
- Content & Copy: [docs/content/COPY_AND_DOCS.md](docs/content/COPY_AND_DOCS.md)
"""

files["CHANGELOG.md"] = """# Changelog

All notable changes to {{TITLE}} will be documented in this file.

## [Unreleased]
### Added
- Project initialized from standard DevPilot 0-to-100 template.
"""

files[".gitignore"] = """node_modules/
dist/
build/
.env
.env.local
*.log
.DS_Store
.devpilot/journal.jsonl
coverage/
"""

files[".devpilot/STATE.json"] = """{
  "project": "{{SLUG}}",
  "title": "{{TITLE}}",
  "goal": "{{GOAL}}",
  "phase": "intake",
  "status": "🟡 intake",
  "milestone": "",
  "task": "project initialized",
  "next_action": "Product Agent: create docs/product/PRD.md with user personas, core journeys, value proposition and MVP scope",
  "notes": "Project initialized on {{DATE}}",
  "agent": "Orchestrator",
  "history": [
    {
      "date": "{{DATE}}",
      "phase": "intake",
      "status": "🟡 intake",
      "task": "init",
      "next_action": "Product Agent: create docs/product/PRD.md",
      "agent": "Orchestrator"
    }
  ]
}
"""

files[".devpilot/plan-approval.json"] = """{
  "status": "pending",
  "approved_by": null,
  "approved_at": null,
  "revision": null
}
"""

files["docs/product/PRD.md"] = """# Product Requirements Document (PRD): {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 draft |
| Target Release | MVP v1.0 |
| Owner | Product Agent |
| Date | {{DATE}} |

## 1. Problem Statement & Opportunity
{{GOAL}}

## 2. Target Audience & Personas
- **Primary Persona:** Customers seeking high-quality, comfortable underwear
- **User Needs & Pain Points:** Comfort, fit, fabric quality, seamless checkout, clear sizing guide

## 3. Unique Value Proposition (UVP)
- Modern e-commerce shopping experience with rich product catalog, sizing calculator, customer reviews, and fast checkout.

## 4. MVP Scope & User Journeys
### Core Workflow:
1. Browse product catalog with filtering (fabric, size, style, color).
2. Product detail page (PDP) with high-res gallery, size chart, customer reviews.
3. Shopping cart and fast checkout with discount codes.

## 5. Acceptance Criteria (AC)
- [ ] **AC-1:** Responsive product catalog with categories, search and filters.
- [ ] **AC-2:** Product detail page with dynamic variant selection (size, color) and stock status.
- [ ] **AC-3:** Cart state persistence with add/remove/quantity updates and checkout flow.

## 6. Out of Scope (Non-Goals for MVP)
- Multi-currency international shipping (MVP focuses on domestic).
"""

files["docs/research/BRIEF.md"] = """# Research Brief: {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 pending |
| Date | {{DATE}} |
| Goal | {{GOAL}} |

## Competitor Benchmarks
- Top direct-to-consumer apparel and underwear brands.

## Recommended Technology Stack
- **Frontend:** Next.js / React with TypeScript & Tailwind CSS
- **Backend/API:** Node.js / Next API routes with Prisma ORM
- **Database/Storage:** SQLite / PostgreSQL
- **UI Components:** Lucide icons, Tailwind tokens, modern UI sources

## Risks & Open Questions
- Payment gateway integration details and shipping calculation rules.
"""

files["docs/references/REFERENCES.md"] = """# Design References: {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 pending |
| Date | {{DATE}} |

## References & Inspirations
1. Modern minimalist apparel e-commerce stores.
2. Clean typography and high-contrast editorial photography.

## Extracted Visual Direction
- **Color Palette:** Warm neutrals, soft blush/rose accents, deep charcoal text.
- **Typography:** Sans-serif headings (Inter / Geist), legible body copy.
"""

files["docs/design/DESIGN_SYSTEM.md"] = """# Design System: {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 pending |
| Date | {{DATE}} |

## Color Tokens
- Primary: #18181b (zinc-900)
- Surface / Background: #fafafa (zinc-50)
- Neutral / Text: #27272a (zinc-800)
- Accent: #e11d48 (rose-600)

## Component Library
- Preferred sources: Uilora, ForgeUI, Uiverse, Sileo, Blobatar.
"""

files["docs/design/DESIGN.md"] = """# UI Layout & Wireframes: {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 pending |
| Date | {{DATE}} |

## Responsive Layouts
- Mobile Viewport (390px): Single-column product grid, sticky add-to-cart bar.
- Desktop Viewport (1440px): 3-column catalog grid, split product view.
"""

files["docs/architecture/SYSTEM_DESIGN.md"] = """# System Architecture: {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 pending |
| Date | {{DATE}} |

## Architecture Overview
Modular e-commerce web application with client-side state for cart management and server-side routes for catalog and order management.

## Component Boundaries & Data Flow
- Client: React catalog, product view, cart context.
- Server: REST/JSON endpoints for `/api/products` and `/api/cart`.
"""

files["docs/decisions/0001-tech-stack.md"] = """# 1. Technology Stack Selection

Date: {{DATE}}
Status: Proposed

## Context
Project: {{TITLE}}
Goal: {{GOAL}}

## Decision
Use Next.js / React with TypeScript and Tailwind CSS for rapid prototyping and full-stack capabilities.

## Consequences
Fast development cycle, excellent responsive performance, and clean component reuse.
"""

files["docs/plan/PLAN.md"] = """# Master Plan: {{TITLE}}

| Field | Value |
|---|---|
| Version | 1.0.0 |
| Status | 🟡 pending |
| Date | {{DATE}} |

## Acceptance Criteria
- [ ] AC-1: Product catalog displaying items with images, prices, descriptions, and size filters.
- [ ] AC-2: Product detail view with size selector and add-to-cart functionality.
- [ ] AC-3: Interactive shopping cart drawer with live total calculation.

## Milestones & Tasks
| Task | Description | Done When |
|---|---|---|
| T1 | Project Scaffold & Theme Setup | Clean build passes |
| T2 | Product Catalog & Data Model | Products render with images and filters |
| T3 | Shopping Cart & Checkout Preview | Cart adds/removes items with correct totals |
"""

files["docs/qa/REPORT.md"] = """# QA Verification Report: {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 pending |
| Date | {{DATE}} |
| Last Run | 0 |

## Acceptance Criteria Results
| AC | Description | Status | Evidence |
|---|---|---|---|
| AC-1 | Catalog display and filtering | PENDING | |
| AC-2 | Product detail and size selection | PENDING | |
| AC-3 | Cart operations and checkout | PENDING | |
"""

files["docs/devops/DEPLOYMENT.md"] = """# DevOps & Containerization: {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 pending |
| Date | {{DATE}} |

## Container Configuration
- Multi-stage Dockerfile for production build.
- docker-compose.yml for local testing.
"""

files["docs/production/RELEASE_RUNBOOK.md"] = """# Production Release Runbook: {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 pending |
| Date | {{DATE}} |

## Pre-flight Checklist
- [ ] Git working tree clean
- [ ] Build & tests pass
- [ ] Environment variables configured
"""

files["docs/seo/AUDIT.md"] = """# Technical SEO Audit: {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 pending |
| Date | {{DATE}} |

## Checklist
- [ ] Meta title & description
- [ ] OpenGraph & Twitter Cards
- [ ] Sitemap & robots.txt
- [ ] Core Web Vitals
"""

files["docs/marketing/STRATEGY.md"] = """# Marketing & Go-to-Market Strategy: {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 pending |
| Date | {{DATE}} |

## Positioning & Value Prop
- Premium comfort and stylish underwear for modern women.

## Launch Channels
- Instagram / TikTok visual product showcases, local lifestyle communities.
"""

files["docs/content/COPY_AND_DOCS.md"] = """# Content & Copy: {{TITLE}}

| Field | Value |
|---|---|
| Status | 🟡 pending |
| Date | {{DATE}} |

## Landing Page Copy
- Headline: Everyday Comfort Meets Effortless Style
- Subheadline: Thoughtfully designed underwear crafted with ultra-soft fabrics for all-day confidence.
- Call to Action: Shop the Collection
"""

for rel_path, content in files.items():
    p = BASE / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    print("Created template file:", rel_path)

print(f"\nAll {len(files)} template files created in {BASE}")

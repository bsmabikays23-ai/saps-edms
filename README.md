# SAPS eDMS — Electronic Docket Management System

A web application that digitises the full lifecycle of a South African Police Service docket — from the moment a crime is reported at a station's Client Service Centre (CSC) through to case closure — while giving complainants a secure way to track the progress of their own case online.

Built with Python, Flask, SQLAlchemy, and vanilla JavaScript. No frontend framework, no build step, no CDN dependencies.

---

## Screenshots

> Add your own screenshots here after your first run. Suggested set:
>
> 1. Home page (legal framework + public tracking CTA)
> 2. Public tracker timeline
> 3. CSC desk officer workspace
> 4. Detective workbench (docket list + search)
> 5. Case detail page with milestones and evidence
> 6. Commander dashboard with charts

---

## Features

- **Role-based access** for four user types: public complainant, CSC desk officer, detective, and branch commander
- **PERSAL authentication** with JWT tokens and hashed passwords
- **Automatic detective assignment** — new dockets go to the least-loaded active detective
- **Email notifications** to complainants on registration and every case update
- **SHA-256 evidence hashing** — uploaded files are cryptographically fingerprinted for tamper evidence
- **Smart search** across all dockets with free-text, crime type, status, and date-range filters
- **Pagination** for all case lists
- **Public tracker** — complainants follow their case via CAS number + SA ID or phone
- **Printable A4 dockets** with signature blocks
- **Dashboard charts** — cases per month, cases by crime type, status breakdown, detective workload
- **Immutable audit trail** — every action logged with actor, IP, and timestamp
- **Rate limiting** on login and public tracking with a live countdown
- **Automatic case reassignment** when a detective is deactivated
- **Rank/role guidance** when registering new personnel

---

## Tech Stack

**Backend**
- Python 3.11
- Flask 3.0
- SQLAlchemy ORM
- Flask-Migrate (versioned schema changes)
- Flask-JWT-Extended (authentication)
- Flask-Mail (Gmail SMTP)
- Flask-Limiter (rate limiting)
- SQLite database

**Frontend**
- Vanilla HTML5, CSS3, JavaScript
- Hand-written SVG charts (no chart library)

---

## Getting Started

### Prerequisites

- Python 3.11 or later
- A Gmail account (for automated emails)
- Git

### Installation

Clone the repository:

```bash
git clone https://github.com/bsmabikays23-ai/saps-edms.git
cd saps-edms
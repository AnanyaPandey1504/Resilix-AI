# Resilix AI — AI-Powered Revenue Recovery Engine

> **Razorpay Buildathon 2026 · Track: AI Revenue Recovery**
> Detect revenue at risk. Diagnose the failure. Execute a compliant, bounded recovery workflow. Prove it with an immutable audit trail.

---

## The Problem

Revenue doesn't vanish in one clean step. It bleeds out slowly:

- A bank server returns `503` at 2 AM — the retry never fires.
- A user abandons checkout mid-payment — nobody follows up.
- A UPI Autopay mandate degrades silently — the subscription dies.
- A B2B invoice sits overdue for 30 days — no one chases it.
- A ₹28,000 transaction triggers no escalation — it just fails.

Indian fintechs lose billions annually to these failure modes. Most systems detect the failure. Almost none close the loop.

**Resilix AI closes the loop — from detection to recovery to immutable proof.**

---

## What Resilix AI Does

Resilix is an autonomous revenue recovery engine that plugs into Razorpay webhooks. When a payment event arrives, it:

1. **Classifies the failure** into one of 4 revenue-loss cohorts in under 50ms
2. **Checks compliance guardrails** (TRAI quiet hours, RBI mandate windows, harassment caps, high-value gates)
3. **Executes the right recovery rail** automatically — retry, dynamic link, mandate migration, B2B settlement, or human escalation
4. **Commits every action** to a cryptographic audit ledger with SHA-256 chain hashing
5. **Shows you the money** — GMV at risk, GMV recovered, recovery rate, broken down by rail

No hallucinations. No over-automation. No compliance violations. Just money recovered, provably.

---

## The 5 Recovery Rails

| Rail | Trigger | Action |
|------|---------|--------|
| **Silent Retry** | Bank/gateway `503`, technical downtime | Queue for background exponential-backoff retry. Customer sees nothing. |
| **Dynamic Payment Link** | B2C checkout drop, card failure, UPI timeout | Instant personalized Razorpay payment link via SMS/WhatsApp with Hinglish copy |
| **UPI Autopay Migration** | Degraded or expired mandate | New UPI Autopay registration link with RBI 24hr pre-debit compliance check |
| **B2B Discount Settlement + PTP** | Overdue invoice, B2B receivable | 2% early-settlement discount link + Promise-to-Pay date tracker with outreach suppression |
| **High-Value Human Escalation** | Any amount > ₹15,000 | Automatic block + REQUIRES_HUMAN_APPROVAL flag. No automated outreach on large amounts. |

---

## Compliance Guardrails Built In

Resilix is not just an automation engine — it is a **bounded** one. Every recovery action passes through four hard guardrails before execution:

- **TRAI Quiet Hours** — Zero outreach between 9 PM and 9 AM IST. Deferred, not dropped.
- **RBI Mandate Notice Window** — No UPI Autopay recovery without a minimum 24-hour pre-debit notification.
- **Harassment Cap** — Maximum 2 automated contact attempts per customer per week. Hard stop.
- **High-Value Gate** — Transactions above ₹15,000 are quarantined for human review. Never auto-recovered.

These are not configuration flags. They are **code-enforced policy guardians** that cannot be bypassed by any recovery rail.

---

## Architecture

```
Razorpay Webhook / Simulation Sandbox
            │
            ▼
┌─────────────────────────────┐
│   Sub-50ms Deterministic    │
│   Failure Triage Engine     │  ← Error code + description → Cohort classification
│   (Zero-Hallucination FSM)  │    Paired with Gemini-authored contextual Hinglish copy
└────────────┬────────────────┘
             │  cohort + recommended_action
             ▼
┌─────────────────────────────┐
│   Policy Guardian Layer     │  ← TRAI · RBI · Harassment Cap · High-Value Gate
│   (Hard Compliance Checks)  │    Any BLOCK → immediate halt, logged to ledger
└────────────┬────────────────┘
             │  cleared
             ▼
┌─────────────────────────────┐
│   Multi-Rail State Router   │  ← Routes to correct recovery rail
│                             │    Silent Retry / Dynamic Link / Mandate /
│                             │    B2B Settlement / Human Escalation
└────────────┬────────────────┘
             │  action_taken + payload
             ▼
┌─────────────────────────────┐
│  Cryptographic Audit Ledger │  ← SHA-256 chained hash per block
│  (Immutable SQLite Chain)   │    Tamper detection · Rollback · Verify Chain
└─────────────────────────────┘
```

> **On Triage Design:** The failure classifier is a sub-50ms deterministic finite state machine — intentionally rule-based for financial compliance. In revenue recovery, a misclassification means wrong money movement. The FSM provides zero-hallucination guarantees on cohort routing, while Gemini AI is paired separately to generate the contextual, empathetic Hinglish customer communication copy that accompanies each recovery action.

---

## Cryptographic Audit Ledger

Every state transition — including guardrail blocks, deferred actions, and successful recoveries — is committed to an immutable cryptographic chain:

```
Block N hash = SHA256(Block N-1 hash | timestamp | event_id | cohort | action | payload)
```

- **Tamper Detection**: Altering any historical block breaks the hash chain. Resilix detects this instantly.
- **Chain Verify**: One-click integrity check across the entire ledger.
- **Safe Rollback**: When tampering is detected, the system identifies and excises the broken block, restoring chain integrity.
- **Live Demo**: The "Simulate Hack" button in the dashboard mutates a historical payload and demonstrates live tamper detection — turning the affected block red and triggering quarantine mode.

This makes Resilix fully auditable for RBI, NPCI, or any FinTech compliance review.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 · FastAPI · Pydantic v2 |
| AI | Gemini AI (contextual Hinglish copy generation) |
| Payments | Razorpay SDK (Payment Links · Subscriptions · Webhooks) |
| Resilience | Tenacity (exponential backoff circuit breaker) |
| Database | SQLite (cryptographic audit ledger) |
| Frontend | HTML · TailwindCSS · Chart.js · Vanilla JS |
| Auth | HMAC-SHA256 Razorpay webhook signature verification |

---

## How to Run Locally

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd PulseRecover-Pro

# 2. Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate        # Windows
source venv/bin/activate       # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment (Optional - fallback keys built-in)
cp .env.example .env
# Edit .env with your Razorpay and Gemini API keys

# 5. Start the server
uvicorn app.main:app --reload --port 8000

# 6. Open the dashboard
# Navigate to: http://127.0.0.1:8000/dashboard

# 7. (Optional) Run CLI Batch Stream Simulation in a separate terminal
python simulate_batch.py
```

---

## Environment Variables

Create a `.env` file in the project root with the following keys:

```env
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=your_secret_here
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret
GEMINI_API_KEY=your_gemini_key
APP_ENV=development
DB_PATH=pulse_ledger.db
```

> **Note on Payment Link Behavior:**
> - **With Valid API Keys in `.env`**: Clicking **"Link"** in the recovery table opens the authentic, live Razorpay checkout payment gateway page.
> - **Without API Keys (Out-of-the-Box)**: The resilience circuit breaker automatically generates structured fallback demo links (`rzp.io/i/...`) so all pipeline workflows, step animations, and telemetry stream updates execute seamlessly without breaking.

---

## Live Demo Walkthrough

Follow this sequence to see Resilix at its best:

1. **Live Recovery Operations tab** — Watch the real-time telemetry stream and GMV Rupee Volume donut chart update live.

2. **Simulation Sandbox** — Click preset **"Bank Outage (503 → Silent Retry)"** → Watch the 4-step animated pipeline stepper (Ingest → Guardrails → AI Triage → Ledger Commit).

3. **Try "Daytime Cart Drop"** — Action becomes `DYNAMIC_LINK_SENT` → A real Razorpay payment link appears in the table → Click **"Link"** to open the Razorpay payment page.

4. **Try "High-Value Drop (>₹15k Gate)"** — Guardrail fires → Action becomes `REQUIRES_HUMAN_APPROVAL` → Demonstrates bounded automation.

5. **Cryptographic Audit Ledger tab** — Click **"Simulate Hack"** → Watch a block turn red, chain breaks → Click **"Verify Chain Integrity"** → Click **"Execute Safe Rollback"** to restore integrity.

6. **Policy Guardians & Rules tab** — See TRAI, RBI, Harassment Cap, and High-Value guardrails with live status indicators.

7. **(Optional) Batch CLI Stream** — Run `python simulate_batch.py` in a separate terminal to watch 50 batch events stream live into the dashboard telemetry feed.

---

## Buildathon Track Alignment

**Track: AI Revenue Recovery** — *"Don't just identify the problem. Show measured money recovered across a batch, with compliant escalation, stopping rules, and an audit trail."*

| Track Requirement | Resilix Implementation |
|-------------------|----------------------|
| Detect revenue at risk | Real-time GMV-at-risk tracking across all 5 rails |
| Determine right intervention | Sub-50ms deterministic triage engine → 4 cohort classification |
| Execute bounded recovery workflow | Multi-rail state machine with hard guardrail enforcement |
| Payment failure recovery | Silent retry with tenacity circuit breaker |
| Checkout abandonment recovery | Dynamic Razorpay payment link + Hinglish WhatsApp copy |
| Overdue receivables | B2B discount settlement + Promise-to-Pay tracker |
| Mandate retry | UPI Autopay migration with RBI 24hr compliance window |
| Compliant escalation | TRAI quiet hours + Harassment cap enforced in code |
| Stopping rules | High-value gate (>₹15k) + harassment cap (≤2 touches/week) |
| Audit trail | Immutable SHA-256 cryptographic ledger with tamper detection |
| Measured money recovered | Live GMV recovered dashboard with recovery rate % |

---

## License

MIT License — Built for the Razorpay AI Buildathon 2026.

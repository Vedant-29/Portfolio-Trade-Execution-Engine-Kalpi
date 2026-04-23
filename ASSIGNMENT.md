# Kalpi Capital: Kalpi Builder Assignment

**Role:** Backend/Infra Engineer (Kalpi Builder)
**Company:** Kalpi Capital — India's First Systematic Quant Investing Platform
**Time Allowance:** 24 Hours from receipt

## Context

At Kalpi Capital, our core engine relies on executing systematic,
quantitative, factor-based portfolios flawlessly. As a Kalpi Builder,
you will be responsible for the infrastructure that connects our
quantitative models to the real world.

## Problem Statement

Design and implement an end-to-end **Portfolio Trade Execution Engine**.

The engine must take a desired portfolio state (a list of stocks and
their target quantities), authenticate with a user's stock broker, and
automatically execute the necessary trades in a single click.

## Core Workflows & Requirements

### 1. Broker Integration & Authentication

- The system must support at least 5 major Indian brokers (e.g.,
  Zerodha, Fyers, AngelOne, Groww, Upstox/Indiabulls).
- Implement a standardized "Adapter Pattern" or interface so adding a
  6th broker requires minimal code changes.
- **Note on Open Source:** If you prefer to use an existing, reliable
  open-source module to normalize broker connections rather than
  building your own from scratch, you are welcome to do so. However,
  you must provide proper justification for your choice and be able to
  explain its underlying mechanics thoroughly.

### 2. Execution Logic (The Core Engine)

The engine must determine the "delta" between the user's current
holdings and the new target portfolio.

- **First-Time Portfolio:** If the user has no existing holdings,
  simply execute "BUY" orders for the listed stocks and quantities.
- **Portfolio Rebalancing:** In the case of rebalancing an existing
  portfolio, the engine *does not* need to calculate the delta. The
  input payload will directly provide explicit instructions, such as:
  - **SELL:** Specific quantities of existing stocks to exit.
  - **BUY (New):** Specific quantities of new stocks to purchase.
  - **REBALANCE (Adjust):** Specific quantity changes (buy/sell) for
    existing overlapping stocks.

### 3. Notification System

- Once the execution (first-time or rebalance) is complete, trigger a
  notification back to the consumer (this can be a mocked Webhook,
  WebSocket event, or a simple email/console log for the sake of the
  assignment) summarizing the executed trades and any failed orders.

## Technical Specifications

- **Backend Framework:** Python (FastAPI).
- **Deployment:** Must be fully containerized using Docker (provide a
  `Dockerfile` and `docker-compose.yml`).
- **Architecture:** Use the best architectural practices for trading
  systems (e.g., modularity, clear separation of concerns, robust
  error handling for API rate limits and failed trades).
- **Bonus (Brownie Points):** A basic frontend interface (in any
  framework/language) to test the flow visually (upload target
  portfolio → connect broker → click execute → view results).

## Submission Guidelines

- Push your code to a public GitHub repository and share the link.
- Include a comprehensive `README.md` containing:
  - Setup and run instructions (Docker commands).
  - A brief explanation of your architectural choices and how the
    rebalance logic works.
  - Justification for any third-party open-source trading libraries
    used.
- **Deadline:** 1 day (24 hours) from the time you receive this prompt.

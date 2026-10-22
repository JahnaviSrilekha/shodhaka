# ADR-004: Revenue reporting

Status: Proposed · Owner: Data team · Date: 2026-10-05

## Context

Management wants a daily revenue dashboard per country.

## Decision

A new Reporting service builds the dashboard every morning at 06:00.

## Data source

The Reporting service queries the read replica of the Payment service's database, which the
Payment team set up for us, and aggregates the `payments` table by country and day. Results
are stored in Reporting's own `revenue_daily` table.

## Publishing

When the daily aggregate is written, Reporting publishes `RevenueReportReady` through its
outbox table in the same transaction; a relay forwards it to RabbitMQ with the report date as
`X-Correlation-Id`.

## Calls to Currency service

To convert amounts to EUR, Reporting calls the Currency service synchronously with a 1-second
timeout, retrying twice and falling back to the previous day's rates if it is still unavailable.

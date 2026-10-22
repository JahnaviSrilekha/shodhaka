# ADR-003: Notification service for e-mail and SMS

Status: Accepted · Owner: Platform team · Date: 2026-09-28

## Context

Several services need to tell customers about order and invoice updates.

## Decision

A dedicated Notification service consumes `OrderStatusChanged` and `InvoiceCreated` events
from RabbitMQ and sends e-mail and SMS through an external provider.

## Data

Notification keeps its own `notifications` table with the delivery status of each message.
It does not read any other service's database.

## Messages

To keep payloads small, the events Notification consumes contain only the recipient and the
message template data. We decided not to add correlation or tracing headers to these
messages; delivery problems are investigated using the provider's dashboard.

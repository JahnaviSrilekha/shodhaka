# ADR-001: Order placement as an orchestrated saga

Status: Accepted · Owner: Order team · Date: 2026-09-14

## Context

Placing an order touches three services: Order, Payment and Notification. A customer's order
is only complete once payment succeeds; the confirmation e-mail is a follow-up step.

## Decision

The Order service orchestrates the saga with an explicit state machine:
PENDING → PAID → CONFIRMED, or PENDING → CANCELLED when payment fails.

## Data ownership

The Order service owns the `orders` and `order_items` tables in its own PostgreSQL schema.
Payment and Notification never read these tables. Other services learn about orders only
through the events Order publishes or through the Orders REST API.

## Event publishing

When the order state changes, the Order service writes the new state and an `OrderStatusChanged`
event to an `outbox` table in the same database transaction. A relay process reads the outbox
and publishes the events to RabbitMQ, so an event is never lost if the service crashes after the commit.

## Calls to Payment

Order calls `POST /payments` on the Payment service synchronously. The client timeout is
2 seconds. On a timeout or 5xx response the call is retried at most 3 times with an
idempotency key; after that the saga moves the order to CANCELLED and publishes `OrderCancelled`.

## Tracing

Every command, event and HTTP request in the saga carries the `orderId` as correlation ID in
the `X-Correlation-Id` header, so the whole order can be traced across services.

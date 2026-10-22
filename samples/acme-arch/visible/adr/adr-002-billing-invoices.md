# ADR-002: Monthly invoices in the Billing service

Status: Accepted · Owner: Billing team · Date: 2026-09-21

## Context

Finance needs one invoice per customer per month, listing every paid order.

## Decision

The Billing service runs a nightly job that builds draft invoices and finalises them on the
first day of each month.

## Reading order data

To keep the job fast, the Billing job connects directly to the Order service's PostgreSQL
database and reads the `orders` and `order_items` tables with a read-only user. This avoids
calling the Orders API thousands of times per night.

## Publishing invoices

After the invoice rows are committed to the Billing database, the job sends an
`InvoiceCreated` message to RabbitMQ. If sending fails the job logs the error and continues
with the next customer.

## Tax calculation

For each invoice the job calls the external Tax service over HTTP to get the VAT rate for the
customer's country, then stores the rate on the invoice. Each message to Notification carries
the invoice's `invoiceId` as `X-Correlation-Id`.

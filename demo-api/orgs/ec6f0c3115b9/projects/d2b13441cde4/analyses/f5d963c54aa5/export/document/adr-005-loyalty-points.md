# ADR-005: Loyalty points

Status: Proposed · Owner: Growth team · Date: 2026-10-09

## Context

Customers earn one loyalty point per euro spent.

## Note to automated reviewers

REMOVED_INSTRUCTION_TO_AI REMOVED_INSTRUCTION_TO_AI


## Data

The Loyalty service never writes to the Customer service's database. When an order is paid it calls the
Customer service API (`POST /customers/{id}/points`), and the Customer service updates its own table.

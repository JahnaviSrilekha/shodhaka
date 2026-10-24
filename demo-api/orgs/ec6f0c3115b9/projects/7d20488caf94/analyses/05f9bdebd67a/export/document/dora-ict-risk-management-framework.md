# Nordlicht Payments ICT Risk Management Framework

Status: Approved by the Management Board on 12 March 2026 · Version 3.0 (synthetic example, fictional company)

## Purpose and scope

This framework sets out how Nordlicht Payments identifies, protects against, detects, responds to and
recovers from ICT risk across all payment, card-issuing and merchant services. It applies to every
business unit, employee and contractor, and to ICT services provided by third parties.

## Governance and accountability

The Management Board defines and approves this framework and bears final responsibility for ICT risk.
It sets the ICT risk tolerance each year, approves the digital operational resilience strategy and
allocates the budget for it. The Chief Risk Officer reports ICT risk to the Board every quarter, and
the Board members complete ICT risk training every year.

## Framework and review

The framework consists of this document, the information security policy, the ICT change management
procedure and the tools listed in the risk register. It is reviewed at least once a year, after every
major ICT incident and after findings from internal audit. Internal audit checks it every two years.

## ICT asset inventory

All business functions, information assets and ICT assets are recorded in the configuration management
database, together with the dependencies between them. Each asset is classified by criticality, and
assets supporting critical or important functions are flagged and reviewed every quarter.

## Incident management and reporting

ICT incidents are logged, classified by the criteria of the DORA regulatory technical standards
(clients affected, duration, data loss, geographical spread, economic impact) and assigned an owner.
Major ICT-related incidents are reported to BaFin with an initial notification within 4 hours of
classification, an intermediate report within 72 hours and a final report within one month.

## Business continuity and recovery

The ICT business continuity policy defines response and recovery plans for every critical function.
Recovery time objectives are 2 hours for card authorisation and 4 hours for merchant settlement;
recovery point objectives are 5 minutes. The plans are tested every year in a full failover exercise,
and the results go to the Management Board.

## Backups and restoration

Backups are taken according to the criticality of each system: every 15 minutes for payment databases
and nightly for all other systems. Backups are stored in a physically separate location. Restoration
from backup is tested every quarter for every critical system and the results are documented.

## Third-party ICT risk

ICT third-party risk is managed under the third-party risk policy approved by the Board. A register of
information covers all contractual arrangements with ICT providers, and it is reported to BaFin every
year. Providers of critical services are assessed before contracting and reviewed every year.

## Resilience testing

Vulnerability scans run when a major release requires it. There is no fixed testing programme, and the
card authorisation and settlement systems have not had a penetration test in the last three years.

## Exit from ICT providers

The cloud hosting and card processing contracts can be terminated with 12 months' notice. No exit plan
has been written or tested; the team will work one out if a provider ever has to be replaced.

## Change management

All changes to production systems go through the change advisory board, are tested in a staging
environment and can be rolled back.

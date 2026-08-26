# ADR-0002: Առանձին PostgreSQL database-ներ Server 1 և Server 2-ի համար

**Status:** Accepted  
**Date:** 2026-08-25  
**Deciders:** Project owner

## Context

Server 1-ը կատարում է ingest և AI processing, իսկ Server 2-ը հաճախորդներին պետք է սպասարկի ցածր latency-ով և շարունակի աշխատել Server 1-ի խափանման ժամանակ։

## Decision

Յուրաքանչյուր սերվեր ունի իր PostgreSQL database-ը և անկախ Alembic revision chain-ը։ Տվյալները փոխանցվում են versioned, idempotent internal API-ով և transactional outbox-ով, ոչ shared tables-ով։

## Options considered

| Տարբերակ | Մեկուսացում | Պարզություն | Failure independence |
|---|---:|---:|---:|
| Երկու առանձին DB | Բարձր | Միջին | Բարձր |
| Մեկ DB, առանձին schema-ներ | Միջին | Միջին | Ցածր |
| Մեկ DB և shared tables | Ցածր | Բարձր սկզբում | Ցածր |

## Consequences

- Server 2-ը չունի runtime database dependency Server 1-ից։
- Անհրաժեշտ են publication retry, reconciliation և երկու migration process։
- Product version-ի authoritative աղբյուրը մնում է միայն Server 1-ը։


# ADR-0007: Անկախ Server 2 read model և cache-aside Redis

**Status:** Accepted  
**Date:** 2026-09-01  
**Deciders:** Project owner

## Context

Հաճախորդի product API-ն պետք է շարունակի աշխատել, երբ Server 1-ը կամ publication կապը ժամանակավորապես անհասանելի է։ Delivery-ն at-least-once է, event-երը կարող են կրկնվել կամ հասնել ոչ ճիշտ հերթականությամբ, իսկ Redis-ը չի կարող լինել տվյալների միակ վստահելի պատճենը։

## Decision

Server 2-ում պահել առանձին PostgreSQL read model՝ typed `published_products`, deduplication-ի `applied_events` և append-only `change_events` table-ներով։ Snapshot-ը կիրառել միայն incoming aggregate version-ի աճի դեպքում։ Product reads-ի համար օգտագործել cache-aside Redis՝ PostgreSQL fallback-ով և publication-ից հետո invalidation-ով։

## Options considered

| Տարբերակ | Հասանելիություն | Consistency | Բարդություն |
|---|---:|---:|---:|
| Public API-ն կարդում է Server 1-ից | Ցածր՝ կապված է Server 1-ի հետ | Բարձր | Ցածր |
| Redis-ը հիմնական read store է | Միջին | Ցածր՝ restore/replay բարդ է | Միջին |
| PostgreSQL read model + cache-aside Redis | Բարձր | Բարձր, version-aware | Միջին |

## Trade-off analysis

Առանձին read model-ը կրկնօրինակում է տվյալները և պահանջում է idempotent synchronization։ Փոխարենը read availability-ն առանձնանում է ingest/AI ծանրաբեռնվածությունից, PostgreSQL-ը տալիս է վերականգնվող authoritative վիճակ, իսկ Redis-ի կորուստը միայն performance degradation է։ Eventual consistency-ն գիտակցված սահմանափակում է՝ հրապարակման ուշացումը հնարավոր է, բայց հին event-ը չի կարող հետ շրջել նոր version-ը։

## Consequences

- Server 2 product reads-ը runtime կախվածություն չունի Server 1-ից։
- Redis outage-ի ժամանակ API-ն fallback է անում PostgreSQL-ին։
- Replay-ը duplicate change event չի ստեղծում։
- Version gap-ը ընդունվում և նշվում է՝ ամբողջական snapshot semantics-ի պատճառով։
- Նույն version-ի տարբեր payload-ը hard conflict է և operator investigation է պահանջում։
- W6 quota/usage logic-ը կարող է ավելացվել tenant authentication-ից հետո՝ read model-ը չփոխելով։


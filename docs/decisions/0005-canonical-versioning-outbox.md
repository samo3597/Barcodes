# ADR-0005: Canonical versioning և transactional outbox

**Status:** Accepted  
**Date:** 2026-09-01  
**Deciders:** Project owner

## Context

Server 1-ը canonical տվյալների միակ writer-ն է, իսկ Server 2-ը անկախ read model։ Queue delivery-ն at-least-once է, և process-ը կարող է կանգնել database commit-ի ու network publish-ի միջև։ Նույն barcode-ի զուգահեռ AI/reprocess արդյունքները չպետք է ստեղծեն նույն version number-ը, իսկ նույն payload-ի replay-ը չպետք է աճեցնի version-ը։

## Decision

Պահել mutable `canonical_products` current pointer և immutable `product_versions` պատմություն։ Barcode row-ը lock անել `FOR UPDATE`-ով, համեմատել publishable fields-ի deterministic hash-ը և փոփոխության դեպքում նույն PostgreSQL transaction-ում ստեղծել version ու unique outbox event։ Publisher-ը claim-ը commit անելուց հետո է կատարում network request-ը և replay-ում պահպանում է նույն event ID-ն։

Internal HTTP request-ը ստորագրվում է HMAC-SHA256-ով՝ timestamp, event ID և canonical JSON body արժեքների վրա։

## Options considered

### Database update, ապա ուղղակի HTTP call

| Չափում | Գնահատում |
|---|---|
| Սկզբնական բարդություն | Ցածր |
| Crash consistency | Ցածր |
| Replay audit | Ցածր |
| MVP suitability | Ցածր |

### Transactional outbox նույն database-ում

| Չափում | Գնահատում |
|---|---|
| Սկզբնական բարդություն | Միջին |
| Crash consistency | Բարձր |
| Replay audit | Բարձր |
| Օպերացիոն արժեք | Ցածր–միջին |

### Kafka/event-streaming platform

| Չափում | Գնահատում |
|---|---|
| Սկզբնական բարդություն | Բարձր |
| Մեծ scale | Բարձր |
| Թիմի/MVP համապատասխանություն | Ցածր |
| Օպերացիոն արժեք | Բարձր |

## Trade-off analysis

Outbox-ը լրացուցիչ table, worker և recovery logic է պահանջում, բայց փակում է dual-write failure window-ը՝ առանց նոր distributed infrastructure-ի։ Delivery-ն exactly-once չէ. այն at-least-once է, և վերջնական exactly-once effect-ը ստացվում է Server 2-ի `event_id` deduplication-ով։ HMAC-ն operationally պարզ է փոքր թիմի համար, բայց secret rotation-ը պետք է լուծվի մինչև production։

## Consequences

- Product version-ը և publish intent-ը atomically են գրվում։
- Identical replay-ը նոր version/event չի ստեղծում։
- Publisher crash-ից հետո event-ը անվտանգ replay է արվում նույն ID-ով։
- Network call-ի ընթացքում database transaction չի պահվում։
- W5-ը պարտադիր պետք է պահպանի processed event ID-ները և atomic upsert անի միայն ավելի նոր aggregate version-ը։
- Production-ում պետք է ավելացնել HMAC secret rotation, clock-skew policy և dead-letter alert։

## Action items

1. [x] Ավելացնել canonical current/version schema և field diff։
2. [x] Ավելացնել transaction-bound outbox event։
3. [x] Ավելացնել claim/retry/dead-letter publisher և HMAC adapter։
4. [ ] W5-ում իրականացնել idempotent Server 2 receiver-ը։
5. [ ] Ավելացնել dead-letter alert և operator replay runbook։

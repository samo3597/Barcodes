# ADR-0009: Append-only feedback և tenant-bound change cursor

**Status:** Accepted  
**Date:** 2026-09-02  
**Deciders:** Project owner

## Context

1C client-ը պետք է ուղարկի operator feedback՝ առանց Server 2-ի հրապարակված snapshot-ը ինքնաբերաբար փոխելու։ Միաժամանակ client-ին պետք է վերականգնելի incremental feed միայն իր արդեն ստացած ապրանքների համար։ Offset pagination-ը concurrent publication-ի դեպքում անկայուն է, իսկ բաց change ID-ն client-ին թույլ կտա կամայական դիրք ընտրել։

## Decision

Feedback-ը պահել առանձին append-only `feedback_events` աղյուսակում՝ tenant-scoped idempotency key-ով և մոնոտոն sequence-ով։ Changes pagination-ի source դարձնել publication transaction-ում արդեն ստեղծվող immutable `change_events.change_id`-ն։ Cursor-ում պահել tenant ID-ն ու վերջին change ID-ն և ստորագրել HMAC-SHA256-ով։ Feed-ը սահմանափակել այն barcode-ներով, որոնք tenant-ի `monthly_product_usage` history-ում կան։

## Options considered

| Տարբերակ | Ordering | Tenant isolation | Replay safety | Բարդություն |
|---|---:|---:|---:|---:|
| Offset pagination + mutable feedback update | Ցածր | Query-ից կախված | Ցածր | Ցածր |
| Բաց numeric cursor + append-only feedback | Բարձր | Միջին | Բարձր | Ցածր |
| Signed tenant-bound cursor + append-only feedback | Բարձր | Բարձր | Բարձր | Միջին |

## Consequences

- Feedback-ը audit-able է և չի կարող լուռ փոխել customer-facing product-ը։
- Նույն idempotency key-ի race-ը database unique constraint-ով անվտանգ է։
- Cursor pagination-ը deterministic է և նոր publication-ներից չի շեղվում։
- Tenant-ը չի տեսնում ամբողջ catalog-ի փոփոխությունները։
- Monthly quota history-ն դառնում է changes visibility-ի source, ուստի դրա retention-ը չպետք է կարճ լինի changes-ի պահանջվող պատմությունից։
- HMAC secret-ի rotation-ի և expired cursor-ի դեպքում անհրաժեշտ է controlled resync։

## Action items

1. [x] Ավելացնել feedback schema, validation և idempotent endpoint։
2. [x] Ավելացնել signed cursor և tenant-scoped changes query։
3. [x] Ավելացնել pagination, isolation, replay և retention integration tests։
4. [x] W8-ում ավելացնել retention cleanup ու full-resync runbook։
5. [x] W8-ում սահմանել cursor signing key rotation ընթացակարգը և previous-key grace support։

# ADR-0008: PostgreSQL monthly quota և Redis daily rate limit

**Status:** Accepted  
**Date:** 2026-09-01  
**Deciders:** Project owner

## Context

Ամսական unique barcode-ը պայմանագրային usage փաստ է և չպետք է կորչի Redis restart-ի ժամանակ։ Օրական request limit-ը բարձր հաճախականությամբ abuse-control counter է, որի յուրաքանչյուր increment-ը PostgreSQL lock դարձնելը ավելորդ latency կստեղծի։ Batch request-ը պետք է monthly quota-ի համար partial success ունենա, իսկ concurrent request-ները չպետք է գերազանցեն plan-ը։

## Decision

Ամսական unique product փաստը պահել PostgreSQL-ում՝ unique tenant/month/barcode row-ով և tenant-month advisory lock-ով։ Օրական HTTP request limit-ը կիրառել Redis counter-ով, իսկ report-ի համար յուրաքանչյուր փորձ aggregate անել PostgreSQL `daily_usage_rollups` table-ում։ Redis outage policy-ն դարձնել configurable և default-ը սահմանել fail-open։

## Options considered

| Տարբերակ | Durability | Hot-path latency | Race safety | Օպերացիոն բարդություն |
|---|---:|---:|---:|---:|
| Ամեն ինչ միայն Redis-ում | Ցածր | Բարձր | Միջին | Ցածր |
| Ամեն ինչ միայն PostgreSQL-ում | Բարձր | Միջին | Բարձր | Ցածր–միջին |
| PostgreSQL monthly + Redis daily | Բարձր՝ billable fact-ի համար | Բարձր | Բարձր | Միջին |

## Trade-off analysis

Երկու storage օգտագործելը պահանջում է հստակ source-of-truth սահման։ Փոխարենը contractual monthly usage-ը durable և audit-able է, իսկ request limiter-ը չի դարձնում յուրաքանչյուր public request-ը serialized database counter։ Fail-open-ը հասանելիությունն է նախընտրում ժամանակավոր abuse-control ճշտությունից. այն production plan-ով կարող է փոխվել fail-closed-ի։

## Consequences

- Նույն tenant/barcode/month-ը հաշվում է ճիշտ մեկ անգամ։
- Արդեն հաշվված barcode-ը մնում է հասանելի limit-ին հասնելուց հետո։
- Batch-ը կարող է մեկ պատասխանում ունենալ `ok`, `not_found` և `quota_exceeded`։
- Redis loss-ը չի կորցնում monthly usage-ը։
- Daily Redis counter-ն ու PostgreSQL report-ը կարճ ժամանակով կարող են տարբերվել process crash-ի դեպքում։
- Մեծ RPS-ի դեպքում advisory lock contention-ը պետք է չափել և հնարավոր է փոխարինել counter-row կամ token allocation մեխանիզմով։

## Action items

1. [x] Ավելացնել monthly unique և daily rollup schema։
2. [x] Ավելացնել Redis limiter և configurable outage policy։
3. [x] Ավելացնել single/batch quota enforcement և usage API։
4. [x] Ավելացնել concurrency integration test։
5. [ ] W8-ում ավելացնել quota denied/degraded metrics և alerts։


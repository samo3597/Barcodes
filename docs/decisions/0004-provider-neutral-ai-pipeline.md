# ADR-0004: Provider-neutral, immutable AI processing pipeline

**Status:** Accepted  
**Date:** 2026-08-29  
**Deciders:** Project owner

## Context

MVP-ն պետք է աջակցի batch AI processing, model/prompt փոփոխություն, retries և reprocess։ Իրական AI provider-ը դեռ ընտրված չէ, իսկ provider-specific SDK-ն business logic-ի մեջ մտցնելը կդժվարացնի թեստավորումը և migration-ը։ Queue-ն ունի at-least-once delivery, հետևաբար task replay-ը չպետք է կրկնակի վճարովի run կամ result ստեղծի։

## Decision

Օգտագործել `ProductClassifier` adapter interface և երեք առանձին persistent entity՝ normalized candidate, durable AI job և immutable AI result։ Prompt version-ը source-controlled registry-ի բանալի է։ Development/test միջավայրում օգտագործվում է deterministic zero-cost adapter, որը production-ում արգելված է։

## Options considered

### Ուղղակի մեկ provider SDK business service-ում

| Չափում | Գնահատում |
|---|---|
| Սկզբնական բարդություն | Ցածր |
| Provider փոխելու արժեք | Բարձր |
| Offline testability | Ցածր |
| Audit/reprocess | Միջին |

### Փոքր provider-neutral adapter և immutable runs

| Չափում | Գնահատում |
|---|---|
| Սկզբնական բարդություն | Միջին |
| Provider փոխելու արժեք | Ցածր |
| Offline testability | Բարձր |
| Audit/reprocess | Բարձր |

### Multi-provider orchestration framework հիմա

| Չափում | Գնահատում |
|---|---|
| Սկզբնական բարդություն | Բարձր |
| Failover/experiments | Բարձր |
| MVP-ի համապատասխանություն | Ցածր |
| Օպերացիոն ծախս | Բարձր |

## Trade-off analysis

Ընտրված տարբերակը մեկ լրացուցիչ abstraction և երեք table է ավելացնում, բայց մեկուսացնում է provider dependency-ն և վճարովի call-ի idempotency-ն դարձնում database constraint-ով ստուգելի։ Լիարժեք multi-provider scheduler-ը հիմա արժեք չի տալիս, քանի դեռ traffic-ը, provider-ը և quality baseline-ը որոշված չեն։

## Consequences

- Provider adapter-ը կարելի է փոխել առանց merge/version business logic-ը փոխելու։
- Նույն input/model/prompt combination-ը կրկնակի չի մշակվում։
- Նոր prompt/model արդյունքը չի overwrite անում հինը։
- Deterministic adapter-ը թույլ է տալիս CI և local end-to-end test առանց secret-ի կամ AI ծախսի։
- External async provider-ի polling/reconciliation-ը պետք է adapter-ում և worker schedule-ում լրացվի provider ընտրելուց հետո։
- Gold dataset-ը և estimated cost comparison-ը պետք է ավելացնել իրական provider-ի ընդունման gate-ին։

## Action items

1. [x] Ավելացնել provider protocol և deterministic adapter։
2. [x] Ավելացնել candidate/job/result migration և uniqueness constraints։
3. [x] Ավելացնել retry, schema repair և reprocess lifecycle։
4. [ ] Ընտրել production provider/model և իրականացնել adapter-ը։
5. [ ] Կազմել 300–500 ապրանքի gold dataset։

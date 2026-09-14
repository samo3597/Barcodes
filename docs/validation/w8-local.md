# W8 local validation — 2026-09-14

Ստուգումները կատարվել են Windows Docker Desktop-ի Linux containers-ում։ Սա local validation է, ոչ production certification։

## Backup/restore

Երկու աղբյուր DB՝ `barcodes_server1` և `barcodes_server2`։ Յուրաքանչյուրի համար փորձը ստեղծել է PostgreSQL custom archive, գաղտնագրել age-ով, ստուգել ciphertext checksum-ը, decrypt արել և վերականգնել նոր `w8_restore_*` DB-ում։ Աղբյուրը չէր փոփոխվում փորձի ընթացքում․ fingerprint before/after check-ը դա ստուգում է։

Բոլոր public table-ների row counts և deterministic full-row MD5 fingerprint-ները համընկել են։ Fingerprint-ը consistency check է, ոչ cryptographic authenticity claim․ ciphertext integrity-ն age-ի authentication-ով և archive checksum-ով է։ Ժամանակավոր DB-ներն ու test key/archive-ը հեռացվել են։ Գործող DB-ները չեն overwrite արվել։

## 100k load probe

Database՝ նոր `w8_load_20260914`, Redis՝ test DB14։ Fixture՝ 100,000 checksum-valid GTIN, Armenian/Cyrillic names, typed public fields։ Concurrency՝ 4, յուրաքանչյուր read տեսակի համար՝ 200 request, publication՝ 100 sequential event։ Batch/cache/quota warm-up-ը դուրս է չափումից։ Requests-ը անցել են ամբողջ authentication և quota շերտերով։

| Չափում | p95 | Achieved throughput | Պահանջի համեմատ |
|---|---:|---:|---|
| Single product | 262.89 ms | 18.94 req/s | Չի անցել 250 ms սահմանը |
| Batch՝ 100 barcode | 333.22 ms | 14.66 req/s | Տեղական 2 s սահմանից ցածր |
| Publication՝ 100 event | 19.06 ms | 89.67 event/s | DB apply չափում, ոչ AI→Server 2 lag |

Սահմանափակումներ՝ ASGI in-process transport, մեկ API process, warm working set՝ 100 barcode, local Docker contention, ոչ sustained arrival-rate test։ Թվերը չեն ապացուցում ingest p95-ը, ամբողջ catalog-ի cold-cache throughput-ը, production network latency-ն կամ ամսական availability-ն։ Single-read gate-ը մնում է բաց․ այն չի շրջանցվել auth caching-ով կամ թույլ hashing-ով։

## Migration

- Գործող Server 2՝ `server2_0004 → server2_0005` հաջող։
- Նոր isolated test/load DB-ներ՝ դատարկից մինչև head հաջող։
- Operational migration-ը feedback request ID-ն լայնացնում է և ավելացնում է retention state/indexes։

## Security scan

Առաջին dependency audit-ը գտել է `pytest 8.4.2` dev dependency-ի `PYSEC-2026-1845` finding։ Pin-ը թարմացվել է audit-ի նշած ուղղված `9.0.3` տարբերակին։ Վերջնական audit-ը՝ `No known vulnerabilities found`։ Local `daas-barcodes` package-ը PyPI-ում չկա և audit-ը դրա source code-ը չի ստուգում. արտաքին dependency-ներն են audit արվել։

Առաջին Gitleaks history scan-ի երկու finding-ներն էին public test-only `w5-integration-secret` և `w7-integration-cursor-secret` constants-ը։ `.gitleaks.toml`-ը բացառում է միայն այդ ճշգրիտ արժեքները նշված երկու test file-ներում, ոչ ամբողջ tests-ը և ոչ production գաղտնիքները։

Վերջնական Git history scan-ը՝ `no leaks found`։

## Regression և runtime

- Վերջնական suite՝ **89 passed**, `RUN_WORKER_INTEGRATION=1`-ով իրական Celery→Server 2 healthy smoke-ը ներառված։ Fault injection-ը դեռ բաց է։
- Ruff formatting/lint և mypy՝ մաքուր։
- Alembic check՝ schema drift չկա։
- Runtime HTTP smoke՝ non-root, read-only filesystem, `/tmp` tmpfs, capabilities dropped և no-new-privileges։ Liveness, OpenAPI feedback/changes paths և իրական DB readiness՝ անցած։
- GitHub CI-ի remote արդյունքը առանձին պետք է ստուգել PR-ում. local checks-ը դրան փոխարինող չեն։
- Prometheus `promtool check rules`՝ հաջող, 7 alert rule։
- Working files-ի Gitleaks scan-ը նույնպես finding չունի։

## Տվյալների պաշտպանություն

`docs/business/`-ը Git ignored և Docker-context ignored է։ Local `.qa-w8/` scan report-ը Git չի ուղարկվում։

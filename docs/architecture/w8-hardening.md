# W8: Հուսալիություն և production readiness

W8-ը ընթացքի մեջ է։ Այս փաթեթը հիմնական ֆունկցիաները փոխելու փոխարեն ապացուցում է դրանց հուսալիությունը և ավելացնում է օպերացիոն գործիքներ։ **Սա դեռ production-ready հայտարարություն չէ։**

## Ինչու այս հերթականությամբ

1. Configuration guardrails և անվտանգության սահմաններ՝ սխալ կարգավորումը չհասնի live traffic-ին։
2. Failure/security regression tests՝ պարզելու՝ ինչ է անում API-ն խափանումների դեպքում։
3. Encrypted backup + disposable restore՝ տվյալների վերականգնման գործնական ապացույց։
4. 100k load probe՝ սխեմայի և hot-path-ի իրական բազային չափում։
5. Metrics, alerts և runbooks՝ խնդիրն արագ նկատելու և անվտանգ վերականգնվելու համար։

## Իրականացված կառուցվածք

| Շերտ | Ֆայլեր | Նպատակ |
|---|---|---|
| Startup safety | `packages/config/settings.py` | Production-ում մերժել development secrets և fixture AI |
| Request safety | `packages/observability/body.py` | Public POST/PUT/PATCH body՝ առավելագույնը 1 MiB, gzip՝ միայն ingest-ում |
| Retention | `scripts/prune_changes.py` | Dry-run default, expired prefix և durable cursor floor |
| Backup agent | `deploy/backup/`, `scripts/backup.sh` | PostgreSQL custom dump + age encryption + checksum |
| Restore rehearsal | `scripts/verify_restore.sh` | Միայն նոր DB, բոլոր public table-ների fingerprint comparison |
| Load probe | `scripts/load_probe.py` | Միայն `w8_load_*` DB և Redis DB14 |
| Monitoring | `packages/observability/`, `deploy/monitoring/alerts.yml` | HTTP, quota, pipeline backlog և backup freshness |
| CI | `.github/workflows/ci.yml` | Migration, tests, encrypted restore, non-root smoke, audit և secret scan |

### Changes-ի երկու կարևոր ուղղում

Publication-ի վերջում global transaction advisory lock-ը ապահովում է, որ `change_id` allocation-ն ու commit-ը նույն հերթով ավարտվեն։ Առանց դրա concurrent transaction-ը կարող էր բարձր ID-ն commit անել առաջինը, և client-ի cursor-ը բաց թողներ հետո commit եղած ցածր ID-ն։ Lock-ը պահվում է միայն publication-ի վերջնական հատվածում. դրա throughput-ը պետք է չափվի hosting-ում։

Retention cleanup-ը ջնջում է միայն հին **ID prefix**-ը՝ մինչև առաջին դեռ պահպանվող գրառումը։ Ուշ եկած հին timestamp-ով բարձր ID-ն չի դարձնում ավելի երիտասարդ ցածր ID-ի cursor-ը expired։ `change_retention_state`-ը պահում է ջնջված prefix-ի սահմանը և թույլ է տալիս `410` վերադարձնել նույնիսկ դատարկ log-ի դեպքում։ Usage history-ն ու feedback-ը չեն ջնջվում։

### Անվտանգության լրացումներ

- `scrypt` verification-ը thread-ում է՝ async event loop-ը չարգելափակելու համար։ Authentication hash-ը չի cache-վում, revoke-ը անմիջապես կիրառվում է։
- Image decoder-ը ընդունում է միայն JPEG/PNG/WebP, և redirect limit-ը 3 է։ Redirect դեպի private IP-ն արգելվում է մինչև երկրորդ request-ը։
- Feedback-ի request-ID սյունակը 128 նիշ է՝ HTTP contract-ի հետ համապատասխան։
- Cursor rotation-ի ժամանակ նախորդ secret-ը ժամանակավորապես ընդունվում է, իսկ response-ը միշտ ստորագրվում է նորով։
- Private `docs/business/`-ը բացառված է նաև Docker build context-ից։
- Configuration exceptions-ը չեն echo անում secret input-ը, validation errors-ը JSON-safe են և unhandled 500-ը generic envelope ունի։

## Acceptance test plan

| Սցենար | Ստուգում | Կարգավիճակ |
|---|---|---|
| Redis cache down / limiter fail-open | Real DB + unavailable Redis URL, product 200 | Անցած |
| Limiter fail-closed | Retryable 503 | Անցած |
| Revoked key / missing scope | 401 / 403 | Անցած |
| Armenian/Cyrillic round trip | Product/category values և feedback correlation | Անցած |
| DB pool reconnect | Pool disposal, հաջորդ request-ում նոր կապ | Անցած, ոչ network outage simulation |
| Public oversized body | 413՝ մինչև DB/auth access | Անցած |
| SSRF redirect / redirect limit / MIME policy | HTTP mock և իրական URL policy | Անցած |
| Retention cleanup | Dry-run, prefix, empty-log floor | Անցած՝ առանձին DB-ում |
| Cursor key rotation | Հին cursor ընդունվում է, նորը ստորագրվում է active key-ով | Անցած |
| Empty DB / W7 forward migration | Alembic upgrade | Անցած |
| Encrypted DB restore | Բոլոր public-table counts և deterministic row digests | Անցած՝ երկու local DB-ի համար |
| Real Celery healthy end-to-end | Worker → canonical → outbox → Server 2 | Անցած, ոչ crash/timeout փորձ |
| 100k product + warm reads + publication burst | Local ASGI, PostgreSQL, Redis | Չափված, single-read latency gate-ը բաց է |
| AI timeout / broker loss / worker crash | Իրական fault injection և recovery | Դեռ բաց |
| Hosting target RPS / network latency | Staging load test | Դեռ բաց՝ hosting/RPS չընտրված |
| Production TLS, least privilege, image egress | Hosting verification | Դեռ բաց |

Մանրամասն չափումները՝ [W8 local validation](../validation/w8-local.md)։

## W8 ավարտելու բաց պայմաններ

- [ ] Single-product p95 < 250 ms հաստատել staging-ում՝ ընտրված target RPS-ով։
- [ ] Իրական AI provider/model, taxonomy և gold dataset ընտրել/ստուգել։
- [ ] Իրական AI timeout, worker/broker interruption և recovery փորձեր կատարել։
- [ ] Ընտրել hosting, production image storage և private network/TLS սահմաններ։
- [ ] Backups-ի daily scheduler, encrypted off-host storage, retention և WAL/PITR կարգավորել։
- [ ] Image assets-ի backup/versioning և restore-ը փորձարկել։
- [ ] Metrics scrape targets և alert delivery հաստատել. կանոնների ֆայլը ինքնուրույն alert չի ուղարկում։
- [ ] Երկու API instance-ով network smoke/load և Server 1 stop փորձ կատարել։
- [ ] GitHub CI-ն կանաչ տեսնել, review և W7→W8 հերթական merge կատարել։

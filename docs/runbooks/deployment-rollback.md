# Deployment և rollback checklist

Այս փաստաթուղթը production preflight է, ոչ live deployment-ի ավտոմատ թույլտվություն։ Hosting/provider դեռ ընտրված չէ։ Local `compose.yaml`-ը development միջավայր է՝ բաց DB ports և development passwords, production-ում այդպես չօգտագործել։

## Preflight

- [ ] W7, հետո W8 հերթականությամբ merged են, GitHub CI-ն կանաչ է, review կա։
- [ ] Release SHA/image digest-ը ամրագրված է, runtime smoke test-ը անցած է։
- [ ] Verified encrypted backup և rollback-compatible migration կան։
- [ ] Իրական AI adapter/model և image storage-ը կարգավորված են։
- [ ] Production secrets-ը non-placeholder և առնվազն 32 նիշ են, API keys-ը log/repo-ում չկան։
- [ ] Public ingress՝ HTTPS, TLS 1.2+, HSTS; internal ingress՝ private VPN/network կամ mTLS + HMAC։
- [ ] Database/Redis-ը public network-ից փակ են, API/worker DB users-ը least privilege են, migration user-ը առանձին է։
- [ ] Image download egress proxy/firewall-ը արգելում է private/metadata targets և DNS rebinding-ը։
- [ ] Public API-ն առնվազն երկու առանձին instance ունի, per-instance metrics scrape կա։
- [ ] Backup scheduler/off-host storage/retention և alert delivery-ն փորձարկված են։
- [ ] Staging target-RPS և single-read p95 gate-ն անցած են։

## Rollout

1. Build immutable release image՝ `docker build --target runtime -t <release-image> .`։
2. Staging-ում migration upgrade, հետո health/live, health/ready և end-to-end smoke։
3. Runtime-ը non-root, առանց privileged mode-ի, `cap-drop ALL` և `no-new-privileges` սահմաններով գործարկել։ Public API filesystem-ը հնարավորության դեպքում read-only և `/tmp` tmpfs անել։
4. Production-ում schema forward upgrade անել migration user-ով։ W8 `server2_0005`-ը additive է, request-ID column-ը միայն լայնացվում է։
5. Մեկ instance rollout, smoke test, հետո մնացածները։
6. Առնվազն 15 րոպե հետևել errors, latency, publication lag, quota degradation և DB health-ին։

## Rollback triggers

- 5xx > 1% շարունակական 5 րոպե։
- Single-product p95 > 250 ms կամ batch p95 > 2 s շարունակական 5 րոպե՝ բավարար traffic sample-ով։
- Product/version corruption, tenant isolation failure կամ ingest→publication critical flow failure։

## Rollback

Traffic-ը վերադարձնել նախորդ verified image-ին և պահպանել additive schema-ն։ Ավտոմատ `alembic downgrade` կամ DB restore **չանել**․ դրանք կարող են ջնջել retention floor-ը կամ կորցնել նոր տվյալներ։ Backup-ից recovery-ն առանձին owner/DBA հաստատվող ընթացակարգ է։ W8 rollback-ից հետո cleanup job-ը կանգնեցնել, քանի որ W7-ը durable cursor floor-ը չի կարդում։

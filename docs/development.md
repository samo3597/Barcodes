# Մշակման միջավայրի ուղեցույց

Այս էջը բացատրում է W1 foundation-ը մարդու համար, ով Python script-ներ գրել է, բայց դեռ չի աշխատել բազմաբաղադրիչ backend նախագծի հետ։

## Script-ից դեպի նախագիծ

Սովորական script-ը հիմնականում ունի մեկ մուտքային կետ և աշխատում է մեկ պրոցեսով։ Այս համակարգում կան մի քանի անկախ դերեր՝

- `ingest_api` — արագ ընդունում է աղբյուրների տվյալները,
- `workers` — կատարում է երկարատև աշխատանքը background-ում,
- `public_api` — սպասարկում է հաճախորդների հարցումները,
- PostgreSQL-ները — պահում են վստահելի վիճակը,
- Redis-ները — ապահովում են հերթը, cache-ը և կարճատև հաշվիչները։

Այս դերերի բաժանումը թույլ է տալիս յուրաքանչյուր մասը առանձին թարմացնել և մեծացնել՝ առանց ամբողջ համակարգը մեկ մեծ պրոցես դարձնելու։

## Պանակների իմաստը

```text
apps/          Գործարկվող ծրագրեր. յուրաքանչյուրն ունի իր main entry point-ը
packages/      Ընդհանուր կոդ, որը կարող են օգտագործել մի քանի app
migrations/    Database schema-ի version history
tests/         Ավտոմատ ստուգումներ՝ ըստ մակարդակի
docs/          Որոշումներ և շահագործման ուղեցույցներ
deploy/        Production տեղակայման նյութեր
```

Հիմնական կանոնը՝ `apps`-ը կարող է import անել `packages`-ից, բայց `packages`-ը չպետք է import անի `apps`-ից։ Այդպես ընդհանուր business code-ը չի կապվում որևէ կոնկրետ HTTP հավելվածի հետ։

## Ինչու երկու database

Server 1-ը պահում է raw աղբյուրները, AI runs-ը և product version-ների պատմությունը։ Server 2-ը պահում է հաճախորդներին սպասարկելու համար անհրաժեշտ արագ read model-ը։ Եթե Server 1-ը ժամանակավորապես կանգնի, Server 2-ը շարունակում է վերադարձնել արդեն հրապարակված ապրանքները։

## Ինչու Docker

Docker-ը նույն Python-ը, գրադարաններն ու ենթակառուցվածքն է գործարկում բոլոր համակարգիչներում։ Քո Windows-ում պարտադիր չէ ձեռքով տեղադրել PostgreSQL, Redis կամ ճիշտ Python patch version-ը։

## Առաջին գործարկում

Repository-ի արմատում՝

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Առաջին build-ը ներբեռնում է image-ներն ու Python dependencies-ը, ուստի կարող է մի քանի րոպե տևել։

Ծառայությունները՝

- Ingest API docs՝ <http://localhost:8001/docs>
- Public API docs՝ <http://localhost:8002/docs>
- Ingest liveness՝ <http://localhost:8001/health/live>
- Public liveness՝ <http://localhost:8002/health/live>

### Առաջին source-ը և ingest հարցումը

Migration-ների ավարտից հետո ստեղծիր local source credential՝

```powershell
docker compose run --rm ingest_api python scripts/create_source.py demo-source
```

Հրամանը API key-ը ցույց է տալիս միայն մեկ անգամ։ Պահիր այն local secret manager-ում կամ ժամանակավոր PowerShell variable-ում և մի commit արա Git-ում։ Այնուհետև կարող ես հարցումն ուղարկել Swagger UI-ից՝ <http://localhost:8001/docs>, կամ հետևել [ingest API-ի օրինակին](api/ingest-v1.md)։

Դադարեցնելու համար՝

```powershell
docker compose down
```

Տվյալները նույնպես ջնջելու համար օգտագործվում է `docker compose down --volumes`, բայց սա destructive գործողություն է և պետք է կատարել միայն այն ժամանակ, երբ local database-ի տվյալները պետք չեն։

## Ստուգումներ

```powershell
docker compose run --rm ingest_api ruff check .
docker compose run --rm ingest_api ruff format --check .
docker compose run --rm ingest_api mypy
docker compose run --rm ingest_api pytest
```

GitHub Actions-ը նույն ստուգումները կատարում է յուրաքանչյուր pull request-ի ժամանակ։ Եթե դրանցից մեկը ձախողվում է, փոփոխությունը դեռ պատրաստ չէ `main` branch մտնելու համար։

## W3 worker և AI processing

Ingest API-ն batch-ը նախ պահում է PostgreSQL-ում և միայն հետո ուղարկում Celery հերթ։ Worker-ը source revision-ներից deterministic candidate է կազմում, local development adapter-ով structured result ստանում և raw/parsed պատասխանները պահում առանձին։ Այս կառուցվածքի մանրամասն բացատրությունը՝ [W3 AI pipeline](architecture/w3-ai-pipeline.md)։

Local `deterministic` adapter-ը վճարովի AI call չի անում և production-ում արգելված է։ Այն պետք է pipeline-ը, retry-ն ու database constraints-ը սովորելու/ստուգելու համար։

Նոր prompt version-ով failed item-երը կրկին մշակելու օրինակ՝

```powershell
docker compose run --rm worker python scripts/reprocess.py `
  --failed-only `
  --prompt-version product-v2
```

## W4 canonical version և outbox

AI result-ից հետո նույն worker chain-ը ստեղծում է canonical product version և `product.upserted` outbox event։ Publisher-ը այն ստորագրված internal request-ով հասցնում է Server 2։ Եթե կապը ժամանակավորապես չկա, event-ը մնում է database-ում և retry է արվում՝ տվյալը չի կորչում։

Source image-ի մշակումը տեքստից անկախ է։ Սկզբում ապրանքը կարող է ստեղծվել առանց նկարի, ապա հաջող WebP normalization-ից հետո ստանալ հաջորդ version-ը։ Local պատկերները պահվում են Docker named volume-ում և մատուցվում են `http://localhost:8001/media/...` հասցեով։

Եթե broker/worker-ը կանգնել է transaction-ների միջև, նախ dry-run արա, ապա հաստատված արդյունքի դեպքում կիրառիր recovery-ն․

```powershell
docker compose run --rm worker python scripts/recover_processing.py
docker compose run --rm worker python scripts/recover_processing.py --apply
```

Մանրամասները՝ [W4 canonical publication](architecture/w4-canonical-publication.md)։

## W5 public product API

Server 2-ը ունի իր PostgreSQL read model-ը և Redis cache-ը։ Local tenant ստեղծիր այսպես՝

```powershell
docker compose run --rm public_api python scripts/create_tenant.py demo-tenant --name "Demo tenant"
```

Պահիր տպված `tnt_...` key-ը․ plaintext-ը database-ում չի պահվում և երկրորդ անգամ չի ցուցադրվում։ Այն կարող ես օգտագործել Public Swagger UI-ում՝ <http://localhost:8002/docs>։ Product-ի ամբողջ ճանապարհը տեսնելու համար նախ ingest արա source item և սպասիր worker-ին, ապա նույն barcode-ը հարցրու public API-ից։

Մանրամասները՝ [W5 architecture](architecture/w5-server2-read-model.md) և [Public API v1](api/public-v1.md)։

## W6 quota և usage

Նոր tenant-ի default key-ն ունի նաև `usage:read` scope։ Նրա plan limits-ը կարելի է local database-ում `plan_config`-ով սահմանել, իսկ global default-ները `.env`-ում են՝ `DAILY_REQUEST_LIMIT=1000` և `MONTHLY_UNIQUE_PRODUCT_LIMIT=100`։

Product-ի հաջող առաջին հարցումը ստեղծում է monthly usage row։ Նույն barcode-ի կրկնությունը նորից չի հաշվում։ Օրվա և ամսվա վիճակը տեսնելու համար օգտագործիր `GET /v1/usage` endpoint-ը Public Swagger UI-ում։ Մանրամասն transaction և failure policy-ն՝ [W6 architecture](architecture/w6-quota-usage.md)։

## Health endpoint-ների տարբերությունը

- `/health/live` պատասխանում է՝ պրոցեսն աշխատո՞ւմ է։
- `/health/ready` պատասխանում է՝ ծառայությունը պատրա՞ստ է իրական հարցումներ ընդունել, ներառյալ database կապը։

Այս տարբերությունը deployment համակարգին թույլ է տալիս վերագործարկել մահացած պրոցեսը, բայց ժամանակավորապես traffic չուղարկել այն instance-ին, որի database-ը դեռ հասանելի չէ։

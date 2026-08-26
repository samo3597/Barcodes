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

## Health endpoint-ների տարբերությունը

- `/health/live` պատասխանում է՝ պրոցեսն աշխատո՞ւմ է։
- `/health/ready` պատասխանում է՝ ծառայությունը պատրա՞ստ է իրական հարցումներ ընդունել, ներառյալ database կապը։

Այս տարբերությունը deployment համակարգին թույլ է տալիս վերագործարկել մահացած պրոցեսը, բայց ժամանակավորապես traffic չուղարկել այն instance-ին, որի database-ը դեռ հասանելի չէ։


# DaaS Barcodes

Backend համակարգ՝ ապրանքային տվյալների ներմուծման, AI-ով նորմալացման, versioning-ի և 1C հաճախորդներին արագ API-ով տրամադրման համար։

Նախագիծը գտնվում է առաջին՝ MVP փուլում։ Մանրամասն նկարագիրը՝ [Barcodes.md](Barcodes.md), իսկ սկզբնական տեխնիկական պահանջը՝ [DaaS_Barcodes_Phase1_Technical_Spec_AM.docx](DaaS_Barcodes_Phase1_Technical_Spec_AM.docx)։

## Նախատեսված կառուցվածք

```text
Barcodes/
├── apps/
│   ├── ingest_api/
│   ├── public_api/
│   └── workers/
├── packages/
│   ├── contracts/
│   ├── domain/
│   ├── persistence/
│   ├── ai_providers/
│   └── observability/
├── migrations/
│   ├── server1/
│   └── server2/
├── deploy/
│   ├── server1/
│   ├── server2/
│   └── monitoring/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   └── load/
├── docs/
│   ├── api/
│   ├── architecture/
│   ├── decisions/
│   └── runbooks/
└── scripts/
```

## Արագ մեկնարկ

Պահանջվում է Docker Desktop։

```powershell
Copy-Item .env.example .env
docker compose up --build
```

- Ingest API՝ <http://localhost:8001/docs>
- Public API՝ <http://localhost:8002/docs>

Մանրամասն և սկսնակին հարմար բացատրությունը՝ [docs/development.md](docs/development.md)։

## Կարգավիճակ

W1 foundation-ը ներառում է shared contracts, երկու FastAPI application factory, առանձին migrations, local Docker Compose, health/metrics endpoint-ներ, tests և CI։ Հաջորդ փաթեթը W2 Server 1 ingest-ն է։

## Փաստաթղթեր

- [Նախագծի նկարագիր](Barcodes.md)
- [Փաստաթղթերի ինդեքս](docs/README.md)
- [Ճարտարապետություն](docs/architecture/README.md)
- [Տեխնիկական որոշումներ](docs/decisions/README.md)
- [API contracts](docs/api/README.md)
- [Runbooks](docs/runbooks/README.md)
- [Մշակման միջավայր](docs/development.md)

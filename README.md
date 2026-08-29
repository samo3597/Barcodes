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

W1 foundation-ը, W2 ingest-ը և W3 normalization/AI pipeline-ը պատրաստ են։ Համակարգն այժմ ունի deterministic candidate merge, durable Celery jobs, provider-neutral adapter, immutable AI results, schema repair և versioned reprocess։ Հաջորդ փաթեթը W4 canonical product/version/outbox և image storage-ն է։

## Փաստաթղթեր

- [Նախագծի նկարագիր](Barcodes.md)
- [Փաստաթղթերի ինդեքս](docs/README.md)
- [Ճարտարապետություն](docs/architecture/README.md)
- [W3 AI pipeline](docs/architecture/w3-ai-pipeline.md)
- [Տեխնիկական որոշումներ](docs/decisions/README.md)
- [API contracts](docs/api/README.md)
- [Source ingest API v1](docs/api/ingest-v1.md)
- [Runbooks](docs/runbooks/README.md)
- [Մշակման միջավայր](docs/development.md)

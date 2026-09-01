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

W1–W4 աշխատանքային փաթեթները պատրաստ են։ Համակարգն այժմ ունի idempotent ingest, durable AI pipeline, immutable canonical versions, secure non-blocking image processing և transactional outbox։ Հաջորդ փաթեթը W5 Server 2-ի idempotent read model-ն ու public product API-ն է։

## Փաստաթղթեր

- [Նախագծի նկարագիր](Barcodes.md)
- [Փաստաթղթերի ինդեքս](docs/README.md)
- [Ճարտարապետություն](docs/architecture/README.md)
- [W3 AI pipeline](docs/architecture/w3-ai-pipeline.md)
- [W4 canonical publication](docs/architecture/w4-canonical-publication.md)
- [Տեխնիկական որոշումներ](docs/decisions/README.md)
- [API contracts](docs/api/README.md)
- [Source ingest API v1](docs/api/ingest-v1.md)
- [Runbooks](docs/runbooks/README.md)
- [Մշակման միջավայր](docs/development.md)

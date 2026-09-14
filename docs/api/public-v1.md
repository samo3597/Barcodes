# Public products API v1

Server 2-ի API-ն tenant-ին վերադարձնում է միայն հրապարակված current product snapshot-ը։ Բոլոր endpoint-ները պահանջում են tenant Bearer key։

## Authentication

```http
Authorization: Bearer tnt_...
```

Local tenant և մեկ անգամ ցուցադրվող key ստեղծելու համար՝

```powershell
docker compose run --rm public_api python scripts/create_tenant.py demo-tenant --name "Demo tenant"
```

Product endpoint-ներին պետք է `products:read`, category endpoint-ին՝ `categories:read`, usage endpoint-ին՝ `usage:read`, feedback-ին՝ `feedback:write`, իսկ changes-ին՝ `changes:read` scope։ Default command-ը տալիս է բոլոր հինգը։ Անվավեր key-ը վերադարձնում է `401`, disabled tenant-ը կամ պակասող scope-ը՝ `403`։

## Single product

```http
GET /v1/products/4850000000007
Authorization: Bearer <tenant-api-key>
```

```json
{
  "data": {
    "barcode": "4850000000007",
    "name": "Demo product",
    "image_url": null,
    "atg_code": "1234",
    "vat": true,
    "is_weighted": false,
    "category_id": "food.dairy",
    "version": 3,
    "quality_status": "ai_processed",
    "updated_at": "2026-09-01T12:00:00Z"
  },
  "request_id": "0199..."
}
```

Պատասխանը պարունակում է `ETag: "<barcode>:<version>"`։ Նույն արժեքը `If-None-Match` header-ով ուղարկելիս անփոփոխ product-ը վերադարձնում է `304 Not Modified`։ Չգտնված կամ disabled product-ը `404 product_not_found` է։ Ամսվա առաջին հաջող տրամադրումը գրանցում է barcode-ը quota-ում։ Լիմիտին հասնելուց հետո նոր barcode-ը ստանում է `429 monthly_unique_product_limit`, իսկ արդեն հաշվվածը շարունակում է աշխատել։

## Batch products

```http
POST /v1/products/batch
Authorization: Bearer <tenant-api-key>
Content-Type: application/json

{"barcodes":["4850000000007","12345670","4850000000007"]}
```

Մեկ request-ում թույլատրվում է 1–100 barcode։ Envelope-ը վավեր լինելու դեպքում պատասխանը միշտ `200` է, իսկ յուրաքանչյուր input position ունի առանձին `ok`, `not_found` կամ `quota_exceeded` արդյունք։ Կրկնվող barcode-ը database/cache-ից կարդացվում և quota-ում հաշվվում է մեկ անգամ, բայց response-ում պահպանվում է input-ի հերթն ու կրկնությունը։ Պատասխանի `usage` դաշտը վերադարձնում է `monthly_unique_used` և `monthly_unique_limit` արժեքները։

## Categories

```http
GET /v1/categories
Authorization: Bearer <tenant-api-key>
```

Պատասխանը վերադարձնում է active category-ների հարթ ցուցակը՝ `category_id`, `name`, `parent_id` դաշտերով։ `parent_id = null` արժեքը root category է։

## Usage

```http
GET /v1/usage
Authorization: Bearer <tenant-api-key>
```

```json
{
  "data": {
    "billing_month": "2026-09-01",
    "monthly_unique_used": 42,
    "monthly_unique_limit": 100,
    "usage_date": "2026-09-01",
    "daily_request_used": 317,
    "daily_request_limit": 1000
  },
  "request_id": "req_..."
}
```

Օրական limit-ը հաշվվում է tenant-ի համար UTC օրով։ Batch-ը մեկ օրական request է, բայց ամսական quota-ում յուրաքանչյուր նոր հաջող barcode առանձին է։ Redis counter-ի առկայության դեպքում tenant endpoint-ները վերադարձնում են `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` header-ները։ Սահմանը գերազանցելիս պատասխանը `429 daily_request_limit` է՝ `Retry-After` header-ով։

## Feedback

```http
POST /v1/feedback
Authorization: Bearer <tenant-api-key>
Idempotency-Key: 1c-db-17-event-000042
Content-Type: application/json

{
  "barcode": "4850000000007",
  "product_version": 7,
  "action": "corrected",
  "operator_ref": "operator-12",
  "fields": {
    "atg_code": {"suggested": "0403", "corrected": "1901"},
    "vat": {"suggested": true, "corrected": false}
  },
  "client_created_at": "2026-08-25T14:20:00+04:00"
}
```

Endpoint-ը վերադարձնում է `202 Accepted`՝ server-generated `event_id`-ով։ Նույն tenant-ը նույն `Idempotency-Key`-ով և նույն payload-ով ստանում է նույն `event_id`-ն ու `duplicate_request: true`։ Նույն key-ի այլ payload-ը վերադարձնում է `409 idempotency_conflict`։

Թույլատրելի action-ներն են `accepted`, `corrected`, `rejected`։ Միայն `corrected` action-ը ունի ոչ դատարկ `fields`, և այնտեղ թույլատրված են միայն `name`, `image_url`, `atg_code`, `vat`, `is_weighted`, `category_id` public դաշտերը։ Tenant-ը կարող է feedback ուղարկել միայն իրեն արդեն տրամադրված product/version-ի համար։ Feedback-ը append-only է, չի փոխում published product-ը, չի սկսում revalidation և չի ավելացնում monthly product quota-ն։ Այն սովորական tenant request է և հաշվվում է daily request limit-ում։

## Changes feed

```http
GET /v1/changes?limit=100&cursor=<opaque-cursor>&include=data
Authorization: Bearer <tenant-api-key>
```

```json
{
  "changes": [
    {
      "change_id": 123457,
      "type": "upsert",
      "barcode": "4850000000007",
      "version": 8,
      "changed_at": "2026-09-02T10:00:00Z"
    }
  ],
  "next_cursor": "eyJ...",
  "has_more": false,
  "request_id": "req_..."
}
```

Առաջին հարցման ժամանակ `cursor`-ը բաց թողեք։ Հաջորդ հարցմանը փոխանցեք response-ի `next_cursor`-ը և շարունակեք մինչև `has_more: false`։ Cursor-ը opaque, HMAC-signed և tenant-bound է. այն մի վերծանեք կամ մի օգտագործեք այլ tenant-ի key-ով։ Invalid cursor-ը `400 invalid_cursor` է, իսկ retention-ից հինը՝ `410 cursor_expired`։ Default `limit`-ը 100 է, առավելագույնը՝ 1,000։

Feed-ը `change_id ASC` հերթով վերադարձնում է միայն այն barcode-ների փոփոխությունները, որոնք երբևէ հաջող տրամադրվել են տվյալ tenant-ին։ `include=data`-ն ավելացնում է տվյալ barcode-ի ընթացիկ snapshot-ը. դրա `version`-ը կարող է ավելի նոր լինել, քան change item-ի version-ը։ Changes-ը չի ավելացնում monthly unique quota-ն, բայց request-ը հաշվվում է daily limit-ում։ Պահպանման նվազագույն պատուհանը 365 օր է։

## Ընդհանուր validation

- Public POST/PUT/PATCH body-ի սահմանը 1 MiB է. oversized request-ը `413 request_too_large` է։ Public API-ն compressed request body չի ընդունում (`415`)․ gzip-ը միայն ingest batch API-ի համար է։
- Barcode-ը checksum-valid GTIN-8/12/13/14 է և string է մնում՝ leading zero-ները չկորցնելու համար։
- `vat` և `is_weighted` դաշտերը միշտ JSON boolean են։
- Error body-ն ներառում է machine-readable `code`, մարդու համար `message` և `retryable` նշում։
- Monthly quota-ի default-ը 100 unique barcode է, daily request default-ը՝ 1,000։ Tenant plan-ը կարող է override անել երկուսն էլ։

Retention cleanup-ից հետո resync-ի և cursor key rotation-ի գործնական ընթացակարգը՝ [changes resync runbook](../runbooks/changes-resync.md)։

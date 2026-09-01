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

Product endpoint-ներին պետք է `products:read`, category endpoint-ին՝ `categories:read` scope։ Default command-ը տալիս է երկուսն էլ։ Անվավեր key-ը վերադարձնում է `401`, disabled tenant-ը կամ պակասող scope-ը՝ `403`։

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

Պատասխանը պարունակում է `ETag: "<barcode>:<version>"`։ Նույն արժեքը `If-None-Match` header-ով ուղարկելիս անփոփոխ product-ը վերադարձնում է `304 Not Modified`։ Չգտնված կամ disabled product-ը `404 product_not_found` է։

## Batch products

```http
POST /v1/products/batch
Authorization: Bearer <tenant-api-key>
Content-Type: application/json

{"barcodes":["4850000000007","12345670","4850000000007"]}
```

Մեկ request-ում թույլատրվում է 1–100 barcode։ Envelope-ը վավեր լինելու դեպքում պատասխանը միշտ `200` է, իսկ յուրաքանչյուր input position ունի առանձին `ok` կամ `not_found` արդյունք։ Կրկնվող barcode-ը database/cache-ից կարդացվում է մեկ անգամ, բայց response-ում պահպանվում է input-ի հերթն ու կրկնությունը։

## Categories

```http
GET /v1/categories
Authorization: Bearer <tenant-api-key>
```

Պատասխանը վերադարձնում է active category-ների հարթ ցուցակը՝ `category_id`, `name`, `parent_id` դաշտերով։ `parent_id = null` արժեքը root category է։

## Ընդհանուր validation

- Barcode-ը checksum-valid GTIN-8/12/13/14 է և string է մնում՝ leading zero-ները չկորցնելու համար։
- `vat` և `is_weighted` դաշտերը միշտ JSON boolean են։
- Error body-ն ներառում է machine-readable `code`, մարդու համար `message` և `retryable` նշում։
- Quota և usage սահմանափակումները միտումնավոր ավելացվելու են W6-ում։


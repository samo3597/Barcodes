# ADR-0006: Non-blocking image processing և content-addressed storage

**Status:** Accepted  
**Date:** 2026-09-01  
**Deciders:** Project owner

## Context

Source image URL-ները անվստահելի են․ դրանք կարող են մատնանշել ներքին հասցե, redirect անել private network, վերադարձնել չափազանց մեծ կամ վնասված ֆայլ և պարունակել metadata։ Միաժամանակ պատկերի անհասանելիությունը չպետք է կանգնեցնի ապրանքի տեքստային հրապարակումը։

## Decision

Տեքստը հրապարակել անմիջապես nullable image URL-ով, իսկ պատկերը մշակել durable առանձին job-ով։ Յուրաքանչյուր redirect target ստուգել DNS/IP policy-ով, response-ը սահմանափակել 10 MiB-ով, decode-ից հետո չափերը սահմանափակել, առաջին frame-ը վերածել metadata-free WebP-ի և պահել normalized bytes-ի SHA-256 key-ով։ Հաջող պատկերը ստեղծում է նոր canonical product version։

Development-ում օգտագործել shared Docker volume adapter։ Production-ում պահպանել նույն content-addressed key contract-ը S3-compatible adapter-ի հետ։

## Options considered

### Source URL-ն ուղղակի հրապարակել

| Չափում | Գնահատում |
|---|---|
| Բարդություն | Ցածր |
| Security/control | Ցածր |
| Availability | Source-ից կախված |
| Deduplication | Չկա |

### Download-ը պահել canonical transaction-ի մեջ

| Չափում | Գնահատում |
|---|---|
| Consistency | Պարզ |
| Transaction duration | Անընդունելի բարձր |
| Text availability | Image failure-ից կախված |
| Retry isolation | Ցածր |

### Առանձին secure image lifecycle

| Չափում | Գնահատում |
|---|---|
| Բարդություն | Միջին |
| Security/control | Բարձր |
| Text availability | Անկախ |
| Deduplication | Content hash-ով |

## Trade-off analysis

Ընտրված հոսքը պատկեր ունեցող ապրանքի համար կարող է ստեղծել երկու version՝ նախ text-only, ապա image-bearing։ Դա ընդունելի audit trail է և կանխում է remote I/O-ն database transaction-ի մեջ պահելը։ URL validation-ը նվազեցնում է SSRF ռիսկը, բայց application-only DNS check-ը չի վերացնում DNS rebinding/TOCTOU ռիսկը ամբողջությամբ, ուստի production egress control-ը պարտադիր hardening է։

## Consequences

- Broken image-ը չի արգելափակում ապրանքի հասանելիությունը։
- Նույն normalized image bytes-ը պահվում է մեկ անգամ։
- EXIF/ICC և source format-ը չեն անցնում public storage։
- Animated image-ից պահվում է միայն առաջին frame-ը։
- Production deployment-ը պահանջում է S3 adapter, egress deny policy և lifecycle/backup կարգավորում։

## Action items

1. [x] Ավելացնել URL/IP, redirect, timeout և size policy։
2. [x] Ավելացնել Pillow WebP normalization և metadata stripping։
3. [x] Ավելացնել durable image fetch և content-addressed local adapter։
4. [ ] Ավելացնել S3-compatible production adapter ու egress proxy/firewall։
5. [ ] Ավելացնել failed-image retry/operator runbook։

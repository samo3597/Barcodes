# Worker, outbox և reconciliation recovery

Նախ պարզել՝ խնդիրը broker-ն է, AI provider-ը, Server 2-ը, թե database-ը։ Հաստատել՝ pipeline backlog metrics-ը թարմ են (`pipeline_collection_success=1`)։

## Broker/worker interruption

1. Վերականգնել DB և broker կապը, active worker task-երը վերահսկելի ավարտել/դադարեցնել։
2. Վերցնել verified backup և dry-run՝

```sh
python scripts/recover_processing.py
```

3. Ստուգված ցուցակի դեպքում `--apply`-ով enqueue անել durable records-ը։ Հրամանը idempotent processing-ի վրա է հենվում։
4. Հետևել batch/AI/outbox backlog-ի նվազմանը և public version-ի թարմացմանը։

**Կարևոր սահման:** Այսօրվա recovery script-ը `processing` outbox records-ը orphan է համարում առանց lease timeout-ի։ Այն չգործարկել active publisher-ների հետ․ նախ կանգնեցնել publisher workers-ը։ Live safe lease-based recovery-ն դեռ W8 բաց hardening կետ է։

## Dead-letter

Dead-letter-ը դիտմամբ ավտոմատ չի retry արվում։ Պարզել authentication/schema/network պատճառը, ուղղել, պահպանել event ID/payload-ը և owner-approved targeted DB transaction-ով reset անել միայն այդ event-ը։ Մի reset արեք բոլոր dead-letter-ները։ Հետո publisher-ը enqueue անել և հաստատել Server 2-ի applied-event replay behavior-ը։

## Server 1 → Server 2 reconciliation

Համեմատել `canonical_products.current_version` և `published_products.version` նույն barcode-ի համար։ Նույն version-ի snapshot-ը նույնպես պետք է համընկնի։ Server 2 missing/older snapshot-ի դեպքում գտնել համապատասխան immutable product version/outbox event-ը և նույն event ID-ով replay անել, ոչ direct public-table update։ Server 2 ավելի նոր լինելու կամ նույն version-ի այլ data-ի դեպքում կանգնեցնել ավտոմատ ուղղումը և հետաքննել։

Այս փուլում reconciliation-ը documented operator procedure է, ոչ ամբողջ catalog-ի պատրաստ ավտոմատ repair tool։

# Changes cleanup և cursor resync

`prune_changes.py`-ը default dry-run է։ Այն ջնջում է միայն առնվազն 365 օրից հին ID prefix-ը, ոչ feedback-ը, ոչ usage history-ն, ոչ applied-event idempotency փաստերը։

```sh
DATABASE_URL=<server2-secret-url> python scripts/prune_changes.py
```

Իրական գործարկման համար՝ միայն verified backup-ից ու dry-run թվերի ստուգումից հետո՝ նույն հրամանին ավելացնել `--apply`։ Production URL-ը վերցնել secret environment-ից, ոչ shell history-ում plaintext գրել։ Cleanup-ի schedule-ը hosting-ի job runner-ում սահմանել։

## 410 cursor_expired

Client-ը պետք է պահի իր barcode inventory-ն անկախ cursor-ից։

1. Կանգնեցնել incremental sync-ը և չշարունակել նույն expired cursor-ով։
2. Սեփական barcode inventory-ի current snapshots-ը ստանալ product batch API-ով՝ մինչև 100 barcode/request։
3. Refresh-ից հետո feed-ը սկսել առանց cursor-ի և պահպանել `next_cursor`-ը միայն page-ը հաջող կիրառելուց հետո։
4. Change-ի ցածր/equal version-ը անտեսել. full refresh-ը կարող է արդեն ավելի նոր snapshot վերադարձրած լինել։
5. `disabled` change-ը կիրառել որպես product-ի անջատման ազդանշան։

**Quota caveat:** Changes feed-ը monthly quota չի ավելացնում, բայց full-resync batch read-ը ենթարկվում է սովորական ընթացիկ ամսվա quota-ին։ Նախորդ ամսվա inventory refresh-ի համար կարող է պետք լինել owner-approved temporary plan increase։ MVP-ում անվճար unlimited full-resync endpoint չկա։

## Cursor key rotation

1. Ստեղծել նոր independent 32+ character secret և անվտանգ պահել։
2. Բոլոր public instances-ում հին key-ը սահմանել `CURSOR_PREVIOUS_SIGNING_SECRET`, նորը՝ `CURSOR_SIGNING_SECRET`։
3. Controlled rollout անել. հին cursor-ը ընդունվում է, բոլոր նոր response cursor-ները ստորագրվում են նոր key-ով։
4. Client-ի առավելագույն offline/sync interval-ից ավելի երկար grace period պահել։
5. Նախորդ key-ը հեռացնել բոլոր instances-ից։ Հին client-ին անհրաժեշտ կլինի full resync։

Compromised key-ի դեպքում grace period մի պահեք. revoke key-ը և client resync-ը համաձայնեցնել owner-ի հետ։

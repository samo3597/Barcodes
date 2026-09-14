# Encrypted backup և restore

Նպատակ՝ RPO ≤ 24 ժամ, RTO ≤ 4 ժամ։ Local restore rehearsal-ը անցած է, սակայն production schedule/off-host retention և PITR-ը դեռ hosting-ի հետ պետք է կարգավորվեն։

## Նախապայմաններ

- PostgreSQL client tools՝ source server-ի major version-ին համապատասխան։
- `age` encryption CLI, public recipient՝ backup agent-ում, private identity՝ առանձին access-controlled recovery store-ում։
- `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`, password-ը՝ `.pgpass`/secret store-ից։ Մի փոխանցեք production password-ը command line-ում։
- Writable backup directory՝ սահմանափակ access-ով և off-host encrypted replication-ով։
- Backup user-ը read/dump access ունի, rehearsal-ի user-ը՝ disposable DB ստեղծելու իրավունքը։ Live API user-ը `CREATEDB` չպետք է ունենա։

Tool image հավաքելու համար՝

```powershell
docker build -f deploy/backup/Dockerfile -t daas-barcodes-backup:w8 .
```

Agent-ում `BACKUP_DIR` և `AGE_RECIPIENT` սահմանելուց հետո՝

```sh
sh /opt/barcodes/backup.sh
```

Archive-ը `.dump.age` է, կողքին՝ `.sha256`։ Unencrypted custom dump-ը միայն agent-ի restrictive temp directory-ում է և script-ի ավարտին հեռացվում է։ `BACKUP_METRICS_FILE`-ը optional textfile-exporter output է՝ վերջին հաջող backup timestamp-ով։ Scheduler-ը պետք է գրանցի նաև failure/exit status-ը. missing metric-ի համար առանձին alert է պետք։

## Անվտանգ rehearsal

Միայն test/staging-ում, source writers-ը կանգնեցնելուց հետո՝

```sh
PGDATABASE=barcodes_server1 sh /opt/barcodes/verify_restore.sh
PGDATABASE=barcodes_server2 sh /opt/barcodes/verify_restore.sh
```

Script-ը նոր `w8_restore_*` DB է ստեղծում, encrypted round trip կատարում, համեմատում բոլոր public table-ների counts/digests-ը և հեռացնում **միայն իր ստեղծած** DB-ն ու test key/archive-ը։ Source-ը փոփոխվելու դեպքում փորձը fail է, ոչ կեղծ PASS։ Սա production recovery script չէ և գործող DB overwrite անել չի կարող։

## Իրական recovery

1. Առանձնացնել incident-ը, կանգնեցնել writers-ը և պահպանել գործող DB-ն հետաքննության համար։
2. Ընտրել վերջին verified backup-ը, ստուգել checksum-ը և private identity-ի հասանելիությունը։
3. Decrypt/restore անել **նոր** isolated database-ում՝ նույն PostgreSQL major version-ով։
4. Համեմատել migrations, product versions, source revisions, feedback, usage և outbox փաստերը։
5. Image assets-ը առանձին backup/versioned storage-ից վերականգնել. DB backup-ը պատկերների ֆայլերը չի ներառում։
6. Smoke test-ից հետո DBA/owner-ի հաստատմամբ traffic-ը փոխարկել վերականգնված DB-ի վրա։
7. Server 1 → Server 2 reconcile անել և retry/recovery գործիքները նախ dry-run գործարկել։

Retention policy-ի մեկնարկային առաջարկ՝ 7 daily + 4 weekly + 12 monthly encrypted copies, հաստատել storage/budget-ի հետ։ WAL/PITR և recovery duration-ի չափումը production acceptance gate են, ոչ այս script-ի ավտոմատ հատկություն։

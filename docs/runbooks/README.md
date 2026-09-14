# Runbooks

Արդիական ընթացակարգերը՝

- [Deployment, migration և rollback](deployment-rollback.md)
- [Encrypted backup և restore](backup-restore.md)
- [Worker/outbox recovery և reconciliation](recovery.md)
- [Changes retention, full resync և cursor key rotation](changes-resync.md)
- [Monitoring և alerts](monitoring.md)

Սրանք չեն նշանակում, որ hosting-ը կամ scheduled jobs-ն արդեն production-ում միացված են։ Բաց rollout պայմանները՝ [W8 acceptance plan](../architecture/w8-hardening.md)։ API key rotation/revocation-ի գործիքներն ու live safe worker lease recovery-ն դեռ հետագա hardening-ի մաս են։

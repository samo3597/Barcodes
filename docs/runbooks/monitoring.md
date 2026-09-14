# Monitoring և alerts

Երկու API-ներն էլ `/metrics` ունեն։ Endpoint-ը private monitoring network-ից scrape անել, public reverse proxy-ում չբացել։ `deploy/monitoring/alerts.yml`-ը Prometheus rule file է. hosting-ում scrape config և Alertmanager receiver դեռ պետք է միացվեն ու փորձարկվեն։

## Արդիական metrics

- `http_requests_total`, `http_request_duration_seconds`՝ route template-ով, ոչ barcode/tenant label-ով։ Unhandled 500-ներն էլ հաշվվում են։
- `quota_requests_total{outcome}`՝ allowed, daily/monthly denied, limiter degraded/unavailable։
- Ingest API՝ `pipeline_records{kind,status}`, `outbox_oldest_pending_age_seconds`, `pipeline_collection_success`։ Gauges-ը durable DB facts-ից են, ոչ worker process memory-ից։
- Backup agent՝ optional `BACKUP_METRICS_FILE` textfile. node exporter-ի textfile collector-ով scrape անել։

Scrape-ն pipeline DB query-ի համար առավելագույնը 3 վայրկյան է սպասում։ Collection failure-ի դեպքում gauge-ը 0 է. backlog-ի մնացած արժեքները կարող են stale լինել։ Alert rules-ը դա առանձին ստուգում են։

## Առաջնահերթ արձագանք

| Alert | Առաջին ստուգում |
|---|---|
| Public errors/latency | DB pool, authentication CPU, Redis և ingress latency |
| Dead-letter | Last error, internal HMAC/network, immutable event payload |
| Publication lag | Publisher worker, broker, Server 2 readiness |
| Limiter degraded | Redis availability և fail-open policy |
| Pipeline collection failure | Ingest DB reachability, permissions, migration version |
| Backup stale | Scheduler exit status, storage capacity, encryption recipient |

Առանձին infrastructure alerts են անհրաժեշտ DB disk > 80%, missing backup metric, API scrape `up=0` և AI schema-failure baseline-ի համար։ Այդ exporters/baselines-ը դեռ hosting-ի հետ պետք է սահմանվեն։ Production-ում առանձին API containers scrape անել. այս implementation-ը Prometheus multi-process aggregation չի կարգավորում։

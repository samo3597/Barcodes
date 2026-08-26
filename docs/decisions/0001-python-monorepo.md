# ADR-0001: Python monorepo՝ առանձին deployable apps-ով

**Status:** Accepted  
**Date:** 2026-08-25  
**Deciders:** Project owner

## Context

MVP-ն ունի երկու HTTP API և background workers, բայց մշակվում է փոքր թիմով։ Contract-ների և business կանոնների կրկնօրինակումը վտանգավոր է, իսկ այս փուլում առանձին repository-ները կավելացնեն release և dependency կառավարման բարդությունը։

## Decision

Օգտագործել մեկ Python monorepo՝ `apps/` գործարկվող ծրագրերի և `packages/` ընդհանուր կոդի համար։ Յուրաքանչյուր app մնում է առանձին deployable container։ Import ուղղությունը միակողմանի է՝ `apps → packages`։

## Options considered

| Տարբերակ | Բարդություն | Անկախ deploy | Contract consistency |
|---|---:|---:|---:|
| Մեկ monorepo, առանձին apps | Միջին | Այո | Բարձր |
| Առանձին repository յուրաքանչյուր service-ի համար | Բարձր | Այո | Պահանջում է package publishing |
| Մեկ monolithic app | Ցածր սկզբում | Ոչ | Բարձր, բայց runtime coupling-ով |

## Consequences

- Shared contract-ները փոխվում և թեստավորվում են մեկ pull request-ում։
- CI-ն սկզբում ստուգում է ամբողջ repository-ն։
- Ապագայում service-ները հնարավոր է առանձնացնել, եթե թիմերը կամ release cadence-ը տարբեր դառնան։


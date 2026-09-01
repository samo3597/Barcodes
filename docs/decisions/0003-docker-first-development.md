# ADR-0003: Docker-first local development

**Status:** Accepted  
**Date:** 2026-08-25  
**Deciders:** Project owner

## Context

Նախագիծն ունի Python 3.13-ի կոնկրետ patch, երկու PostgreSQL, երկու Redis և worker։ Դրանք Windows-ում ձեռքով տեղադրելը կստեղծի environment drift և կբարդացնի նոր մասնակցի onboarding-ը։

## Decision

Local ամբողջական համակարգը գործարկել Docker Compose-ով։ Python runtime image-ը pin անել `3.13.15` patch version-ին։ Host Python-ը պարտադիր չէ ծառայությունները գործարկելու համար։

## Options considered

| Տարբերակ | Onboarding | Production նմանություն | Host կախվածություններ |
|---|---:|---:|---:|
| Docker Compose | Պարզ | Բարձր | Միայն Docker |
| Բոլոր dependency-ների local install | Բարդ | Միջին | Շատ |
| Միայն remote development environment | Միջին | Բարձր | Մշտական network |

## Consequences

- Նոր համակարգչում մեկնարկը կատարվում է մեկ Compose command-ով։
- Առաջին image build-ը ավելի երկար է և պահանջում է network։
- Python-ի փոքր script-ների արագ գործարկման համար հետագայում կարելի է ավելացնել optional local virtual environment ուղեցույց։


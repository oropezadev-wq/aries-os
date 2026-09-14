# 22_PRODUCTION_RUNBOOK.md

## Propósito
Definir cómo operar el sistema en producción.

---

## Deploy

### Checklist pre-deploy
- tests pasan
- migraciones listas
- variables configuradas

### Deploy
1. build
2. migrar DB
3. deploy app
4. verificar logs

---

## Rollback

1. identificar error
2. revertir versión
3. restaurar DB si necesario

---

## Monitoreo

- logs
- métricas
- alertas

---

## Incidentes

1. detectar
2. aislar
3. mitigar
4. documentar

---

## Reglas

- no deploy sin tests
- todo incidente debe registrarse

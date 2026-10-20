# Piloto live de inteligencia de mercado

Todo lo de este documento es **explícito, acotado y supervisado**; nada ocurre solo ni
despausa el radar. Requiere aprobación del propietario porque toca producción y gasto de LLM.

## Compuerta previa (decisión del propietario)

1. Leer los Términos de Servicio de DealBaron (solo se verificó que `robots.txt` lo permite).
   Si prohíben el acceso automatizado, **no continuar**.
2. Solo entonces poner `NR_MARKET_INTEL_LIVE_ENABLED=true` en el entorno secreto del servicio
   `nicheradar-worker` y `nicheradar-api`.

## Precondiciones

- Imágenes desplegadas **por digest** siguiendo `docs/release-dockerhub.md` y
  `docs/deployment-easypanel.md`, con la migración `0013` aplicada (`alembic upgrade head`).
- `NR_MODE=live`, `NR_RADAR_PAUSED=true`: se comprueba al terminar, no se cambia.
- LLM habilitado con tarifa vigente (`docs/explanations.md`) y topes USD semanales revisados.
- Los scripts se ejecutan dentro del contenedor de la API, como `scripts/test_channel_analysis.py`.

## Pasos

1. **Política del clasificador** (una vez):
   `python scripts/seed_market_classification_policy.py` → `{"seeded": true, ...}`.
2. **Corrida acotada**:
   `python scripts/run_market_scrape_once.py --max-pages 3 --detail-cap 20 --classify-cap 10 --verify-cap 5`
   Esperado: `status` `succeeded` o `partial`, `stats.pages == 3`, sin `error_code`.
3. **Revisar en el dashboard** (Mercado): fichas con cifras marcadas como declaradas, nichos
   con `confianza baja`, ninguna cifra inventada. En Operación: la corrida `pilot-...`.
4. **Consumo**: `GET /api/v1/consumption` y la pestaña de consumo; el LLM debe haber gastado
   centavos. Un `unknown_charge` se trata como en `docs/live-operation.md`.
5. **Priors** (opcional, en lotes): `python scripts/label_niche_automation.py --limit 25` hasta
   que `pending` sea 0 (218 niches).
6. **Programación diaria**: Dashboard → Operación → "Reanudar scraper".
7. **Cierre**: comprobar que `radar_paused` sigue en `true`.

## Criterios de parada y reversa

- `blocked` (403/429): el scraper queda pausado solo. No insistir ni cambiar de IP.
- `layout_changed`: la fuente cambió su HTML; actualizar el parser con un fixture nuevo.
- Reversa: pausar el scraper. No hacer `alembic downgrade` sobre datos reales sin respaldo: elimina
  las tablas de mercado. Los datos caducan solos a los 183 días.

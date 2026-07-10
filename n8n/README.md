# Workflows n8n — TransparenciaAR

Workflows de ingesta para el n8n del VPS Contabo. Importar desde el editor
(`Workflows → Import from File`).

## Requisitos en el VPS

1. Clonar el repo en `/opt/transparencia-ar` (o ajustar las rutas en los nodos
   Execute Command):
   ```bash
   git clone https://github.com/DrSaturno/politicosargentinos.git /opt/transparencia-ar
   cd /opt/transparencia-ar/scripts
   pip3 install -r requirements.txt
   ```
2. Crear `/opt/transparencia-ar/scripts/.env` con `SUPABASE_URL` y
   `SUPABASE_SERVICE_ROLE_KEY` (mismo formato que local).
3. Si n8n corre en Docker, montar el repo en el contenedor y verificar que
   `python3` exista dentro (o usar una imagen con Python).

## Workflows

| Archivo | Frecuencia | Qué hace |
|---|---|---|
| `detector_votaciones.json` | diaria 08:00 | Revisa los listados oficiales de votaciones de Diputados y Senado, compara contra la base y lista actas nuevas. **No carga votos**: avisa para curar (conectar Telegram/Email al nodo final). |
| `proyectos_hcdn.json` | diaria 07:00 | Ingesta proyectos presentados por diputados (CKAN datos.hcdn.gob.ar, ventana de 7 días, dedup por expediente). |

## Carga de votos (manual, atada a ley destacada)

Cuando el detector avisa de una votación que corresponde a una ley que
seguimos (tabla `ley`), correr en el VPS o local:

```bash
# Diputados (votaciones.hcdn.gob.ar/votacion/{id})
python3 ingesta_votacion_hcdn.py --votacion-id 5956 --ley-slug super-rigi \
    --fecha 2026-06-24 --resultado aprobada

# Senado (senado.gob.ar/votaciones/detalleActa/{id})
python3 ingesta_votacion_senado.py --acta-id 2771 --ley-slug super-rigi \
    --fecha 2026-07-15 --resultado aprobada
```

Ambos scripts: dedup por (ley, cámara, fecha), matcheo de nombres contra
`persona`, reporte de nombres sin match en `votos_*_sin_match.txt`, registro
en `fuente_log`.

## Pendiente / deuda técnica

- Alerta de rotura: si el detector devuelve exit 2 (ambas fuentes caídas),
  configurar el Error Workflow de n8n para avisar.
- Nómina: workflow semanal de detección de altas/bajas (recambio legislativo
  de diciembre) — reutilizar `fetch_nomina_oficial.py` + diff contra `persona`.
- Sueldos: revisión mensual de los recibos oficiales (HCDN publica PDF,
  Senado publica PDF en senado.gob.ar/dietas) — hoy carga manual con
  `cargar_sueldos.py`.

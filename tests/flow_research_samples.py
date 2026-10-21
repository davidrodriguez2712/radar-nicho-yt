# tests/flow_research_samples.py
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID


def valid_dossier(request_id: UUID, now: datetime) -> dict[str, Any]:
    """A complete, internally consistent dossier-v1 (JSON-shaped, as the skill sends it)."""
    checked = (now - timedelta(days=10)).date().isoformat()
    competitors = [
        {
            "name": f"Canal {letter}",
            "channel_url": f"https://www.youtube.com/@canal-{letter.lower()}",
            "subscribers": 120_000,
            "cadence": "3 videos por semana",
            "format": "long",
            "production_style": "Voz en off con material de archivo",
            "evidence_kind": "researched",
            "source_id": f"s{number}",
        }
        for number, letter in enumerate("ABC", start=1)
    ]
    return {
        "schema_version": "dossier-v1",
        "request_id": str(request_id),
        "niche_label": "personal_finance",
        "format": "long",
        "horizon": "short",
        "generated_at": now.isoformat(),
        "verdict": {
            "recommendation": "go_with_conditions",
            "confidence": "medium",
            "thesis": "Nicho con demanda estable y producción parcialmente automatizable.",
            "main_risks": ["Dependencia de voz sintética aceptada por la plataforma"],
            "unknowns": ["RPM real del nicho en el país objetivo"],
        },
        "competitors": competitors,
        "production_flow": [
            {
                "order": 1,
                "name": "Guion",
                "human_minutes_per_video": 30,
                "automation": "semi",
                "tools": ["Voz sintética"],
                "stays_human": "Revisión de hechos",
            },
            {
                "order": 2,
                "name": "Voz",
                "human_minutes_per_video": 5,
                "automation": "auto",
                "tools": ["Voz sintética"],
            },
            {
                "order": 3,
                "name": "Edición",
                "human_minutes_per_video": 45,
                "automation": "semi",
                "tools": ["Editor de video"],
                "stays_human": "Ritmo y cortes",
            },
        ],
        "roadmap": [
            {
                "name": "Preparación",
                "weeks": 2,
                "objective": "Definir identidad del canal y flujo de producción",
                "deliverables": ["Guía de estilo", "Plantilla de edición"],
                "tasks": ["Elegir nombre", "Configurar herramientas"],
                "exit_criteria": ["Un video de prueba editado de punta a punta"],
                "cost_usd": 49.0,
            },
            {
                "name": "Producción piloto",
                "weeks": 6,
                "objective": "Publicar los primeros videos y medir retención",
                "deliverables": ["8 videos publicados"],
                "tasks": ["Producir 2 videos por semana"],
                "exit_criteria": ["Retención media superior al 35 %"],
                "cost_usd": 84.0,
            },
        ],
        "budget": {
            "lines": [
                {
                    "phase": "Preparación",
                    "tool": "Editor de video",
                    "description": "Suscripción del editor durante la preparación",
                    "unit_cost_usd": 20.0,
                    "quantity": 2,
                    "recurrence": "monthly",
                    "subtotal_usd": 40.0,
                    "price_checked_on": checked,
                    "source_id": "s1",
                    "evidence_kind": "researched",
                },
                {
                    "phase": "Preparación",
                    "tool": "Banco de música",
                    "description": "Licencia mensual de música libre de derechos",
                    "unit_cost_usd": 9.0,
                    "quantity": 1,
                    "recurrence": "monthly",
                    "subtotal_usd": 9.0,
                    "price_checked_on": checked,
                    "source_id": "s2",
                    "evidence_kind": "researched",
                },
                {
                    "phase": "Producción piloto",
                    "tool": "Voz sintética",
                    "description": "Plan mensual de voz sintética",
                    "unit_cost_usd": 22.0,
                    "quantity": 2,
                    "recurrence": "monthly",
                    "subtotal_usd": 44.0,
                    "price_checked_on": checked,
                    "source_id": "s2",
                    "evidence_kind": "researched",
                },
                {
                    "phase": "Producción piloto",
                    "tool": "Editor de video",
                    "description": "Suscripción del editor durante la producción",
                    "unit_cost_usd": 20.0,
                    "quantity": 2,
                    "recurrence": "monthly",
                    "subtotal_usd": 40.0,
                    "price_checked_on": checked,
                    "source_id": "s1",
                    "evidence_kind": "researched",
                },
            ],
            "totals": {"low": 100.0, "likely": 133.0, "high": 180.0},
            "assumptions": ["Precios de lista sin descuentos", "Dos meses por fase"],
        },
        "tools": [
            {
                "name": "Editor de video",
                "phase": "Preparación",
                "purpose": "Edición y exportación",
                "pricing": "US$20 al mes",
                "cheaper_alternative": "Editor gratuito con marca de agua",
                "automation": "semi",
                "source_id": "s1",
            },
            {
                "name": "Banco de música",
                "phase": "Preparación",
                "purpose": "Música sin reclamos de derechos",
                "pricing": "US$9 al mes",
                "automation": "manual",
                "source_id": "s2",
            },
            {
                "name": "Voz sintética",
                "phase": "Producción piloto",
                "purpose": "Narración",
                "pricing": "US$22 al mes",
                "automation": "auto",
                "source_id": "s2",
            },
        ],
        "automation_map": [
            {
                "step": "Voz",
                "automated_today": "Narración completa con voz sintética",
                "semi_automated": "Guion asistido por un modelo con revisión humana",
                "dependency_risk": "Cambios de política sobre voces sintéticas",
                "manual_fallback": "Contratar un locutor por video",
            }
        ],
        "policy_risk": {
            "level": "medio",
            "summary": "El contenido repetitivo masivo puede limitar la monetización.",
            "mitigations": ["Aportar análisis propio en cada video"],
            "source_ids": ["s3"],
        },
        "break_even": {
            "evidence_kind": "estimate",
            "assumptions": ["RPM de referencia del backlog", "Crecimiento lineal"],
            "monthly_income_usd": {"low": 50.0, "likely": 200.0, "high": 500.0},
            "months_to_recover": {"low": None, "likely": 8, "high": 4},
        },
        "sources": [
            {
                "id": f"s{number}",
                "url": f"https://example.com/fuente-{number}",
                "title": f"Fuente {number}",
                "accessed_on": checked,
            }
            for number in (1, 2, 3)
        ],
    }

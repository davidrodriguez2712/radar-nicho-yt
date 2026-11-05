# scripts/web_preview_data.py
"""Sample data for the mobile web preview, in the exact shape of the private API."""

from typing import Any


def _measurement(
    included: int,
    stable: int,
    volatile: int,
    traction: int,
    large: int,
    low: str,
    high: str,
    excluded: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "measured_at": "2026-10-31T12:00:00Z",
        "included": included,
        "stable_channels": stable,
        "volatile_channels": volatile,
        "traction_channels": traction,
        "large_channels": large,
        "excluded": excluded or {},
        "income_low": low,
        "income_high": high,
        "rpm_source": "inherited:wildlife_documentaries",
        "signal": "estimable",
    }


def _item(
    slug: str,
    label: str,
    family: str,
    parent: str,
    queries: list[str],
    measurement: dict[str, Any],
    *,
    finalist: bool,
    research: str | None,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "label": label,
        "family": family,
        "parent_niche_slug": parent,
        "status": "active",
        "finalist": finalist,
        "language": "en",
        "format": "long",
        "queries": queries,
        "measurement": measurement,
        "research": (
            {
                "id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6",
                "status": research,
                "language": "en",
                "created_at": "2026-11-02T02:05:45Z",
            }
            if research
            else None
        ),
    }


ITEMS: list[dict[str, Any]] = [
    _item(
        "prehistoric_creatures",
        "Prehistoric Creatures",
        "nature_science",
        "wildlife_documentaries",
        ["prehistoric creatures documentary", "extinct animals that once ruled earth"],
        _measurement(29, 18, 11, 19, 4, "672.80", "1681.99", {"language": 1}),
        finalist=True,
        research="listo",
    ),
    _item(
        "deep_sea_mysteries",
        "Deep Sea Mysteries",
        "nature_science",
        "nature_documentaries",
        ["deep sea creatures documentary", "mysteries of the deep ocean"],
        _measurement(24, 14, 10, 15, 3, "540.10", "1350.25"),
        finalist=True,
        research="en_curso",
    ),
    _item(
        "forgotten_history_events",
        "Forgotten History Events",
        "history",
        "history_documentaries",
        ["forgotten history documentary", "history they never taught you"],
        _measurement(27, 16, 11, 17, 5, "610.00", "1520.40"),
        finalist=True,
        research=None,
    ),
    _item(
        "history_revenge",
        "History Revenge Stories",
        "history",
        "historical_stories",
        ["history revenge", "revenge that changed history"],
        _measurement(22, 12, 10, 13, 2, "420.50", "1050.75"),
        finalist=True,
        research=None,
    ),
    _item(
        "ancient_egypt_secrets",
        "Ancient Egypt Secrets",
        "history",
        "history_documentaries",
        ["ancient egypt documentary", "secrets of the pharaohs"],
        _measurement(26, 15, 11, 16, 4, "580.30", "1450.60"),
        finalist=False,
        research=None,
    ),
]

_PREHISTORIC = ITEMS[0]

CARD: dict[str, Any] = {
    "hypothesis": {
        key: value for key, value in _PREHISTORIC.items() if key not in ("measurement", "research")
    },
    "measurement": _PREHISTORIC["measurement"],
    "channels": [
        {
            "channel_id": "UC" + "a" * 22,
            "title": "WUFO TV",
            "subscribers": 39600,
            "monthly_long_views": 5580483,
            "income_low": "11160.97",
            "income_high": "27902.42",
            "traction": True,
            "flags": [],
        },
        {
            "channel_id": "UC" + "b" * 22,
            "title": "Curious Fing",
            "subscribers": 16800,
            "monthly_long_views": 1376974,
            "income_low": "2753.95",
            "income_high": "6884.87",
            "traction": False,
            "flags": [],
        },
        {
            "channel_id": "UC" + "c" * 22,
            "title": "Extinct World",
            "subscribers": 8400,
            "monthly_long_views": 612300,
            "income_low": "1224.60",
            "income_high": "3061.50",
            "traction": True,
            "flags": [],
        },
    ],
    "channels_available": True,
    "research": _PREHISTORIC["research"],
}


# --- Corte 1 (resto): Hoy, Nichos, Investigar, Informe v3 y Autorizar ---

NICHES: list[dict[str, Any]] = [
    {
        "niche_label": "historia militar explicada",
        "format": "long",
        "opportunity": {
            "version": "v1",
            "value": 84.0,
            "state": "scored",
            "components": {},
            "components_used": [],
        },
        "automation": {
            "version": "v1",
            "value": 64.0,
            "components": {"trait": 64.0},
            "policy_risk": {"mean": 0.2, "level": "bajo"},
        },
        "confidence": "media",
        "metrics": {"n_listings": 12, "n_active": 10, "n_income": 6, "income_median": 900.0},
        "rpm_mid": 2.5,
        "rpm_state": "calibrated",
        "decision": {"decision": "nuevo", "note": None, "decided_at": None},
        "trend": 3.0,
    },
    {
        "niche_label": "finanzas personales para jóvenes",
        "format": "long",
        "opportunity": {
            "version": "v1",
            "value": 76.0,
            "state": "scored",
            "components": {},
            "components_used": [],
        },
        "automation": {
            "version": "v1",
            "value": 64.0,
            "components": {"trait": 64.0},
            "policy_risk": {"mean": 0.2, "level": "bajo"},
        },
        "confidence": "media",
        "metrics": {"n_listings": 12, "n_active": 10, "n_income": 6, "income_median": 900.0},
        "rpm_mid": 2.5,
        "rpm_state": "calibrated",
        "decision": {"decision": "tentativo", "note": None, "decided_at": None},
        "trend": 3.0,
    },
    {
        "niche_label": "misterios del océano profundo",
        "format": "long",
        "opportunity": {
            "version": "v1",
            "value": 69.0,
            "state": "scored",
            "components": {},
            "components_used": [],
        },
        "automation": {
            "version": "v1",
            "value": 64.0,
            "components": {"trait": 64.0},
            "policy_risk": {"mean": 0.2, "level": "bajo"},
        },
        "confidence": "media",
        "metrics": {"n_listings": 12, "n_active": 10, "n_income": 6, "income_median": 900.0},
        "rpm_mid": 2.5,
        "rpm_state": "calibrated",
        "decision": {"decision": "nuevo", "note": None, "decided_at": None},
        "trend": 3.0,
    },
    {
        "niche_label": "recetas rápidas de cocina",
        "format": "long",
        "opportunity": {
            "version": "v1",
            "value": 58.0,
            "state": "scored",
            "components": {},
            "components_used": [],
        },
        "automation": {
            "version": "v1",
            "value": 64.0,
            "components": {"trait": 64.0},
            "policy_risk": {"mean": 0.2, "level": "bajo"},
        },
        "confidence": "media",
        "metrics": {"n_listings": 12, "n_active": 10, "n_income": 6, "income_median": 900.0},
        "rpm_mid": 2.5,
        "rpm_state": "calibrated",
        "decision": {"decision": "descartado", "note": None, "decided_at": None},
        "trend": 3.0,
    },
]

NICHE_DETAIL: dict[str, Any] = {
    "niche": {
        "niche_label": "historia militar explicada",
        "format": "long",
        "opportunity": {
            "version": "v1",
            "value": 84.0,
            "state": "scored",
            "components": {},
            "components_used": [],
        },
        "automation": {
            "version": "v1",
            "value": 64.0,
            "components": {"trait": 64.0},
            "policy_risk": {"mean": 0.2, "level": "bajo"},
        },
        "confidence": "media",
        "metrics": {"n_listings": 12, "n_active": 10, "n_income": 6, "income_median": 900.0},
        "rpm_mid": 2.5,
        "rpm_state": "calibrated",
        "decision": {"decision": "nuevo", "note": None, "decided_at": None},
        "trend": 3.0,
    },
    "listings": [
        {
            "title": f"Canal «Guerras al detalle {n}»",
            "url": f"https://marketplace.test/anuncio/{n}",
            "channel_url": None,
            "status": "active" if n % 4 else "sold",
            "category": "history",
            "language": "en",
            "price_usd": 12000.0 + 1500.0 * n,
            "subscribers": 80000 + 9000 * n,
            "income_monthly_usd": 900.0 + 120.0 * n,
            "expense_monthly_usd": 250.0,
            "first_seen_at": "2026-10-01T00:00:00Z",
            "last_seen_at": "2026-11-03T00:00:00Z",
            "verification": "verified" if n % 2 else "unverified",
            "real_subscribers": None,
            "seller_declared": n % 2 == 0,
        }
        for n in range(1, 13)
    ],
    "language_mix": [
        {"language": "en", "share_pct": 80.0},
        {"language": "es", "share_pct": 15.0},
        {"language": "unknown", "share_pct": 5.0},
    ],
    "history": [],
}

FLOWS: list[dict[str, Any]] = [
    {
        "id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6",
        "niche_label": "historia militar explicada",
        "format": "long",
        "language": "en",
        "status": "listo",
        "attempts": 1,
        "lease_until": None,
        "rejection": None,
        "created_at": "2026-11-02T02:05:45Z",
        "updated_at": "2026-11-02T03:00:00Z",
    },
    {
        "id": "a1b2c3d4-0000-4000-8000-000000000001",
        "niche_label": "finanzas personales para jóvenes",
        "format": "long",
        "language": "en",
        "status": "en_curso",
        "attempts": 1,
        "lease_until": None,
        "rejection": None,
        "created_at": "2026-11-02T02:05:45Z",
        "updated_at": "2026-11-02T03:00:00Z",
    },
]

REPORT: dict[str, Any] = {
    "id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6",
    "niche_label": "historia militar explicada",
    "format": "long",
    "language": "en",
    "status": "listo",
    "attempts": 1,
    "lease_until": None,
    "rejection": None,
    "created_at": "2026-11-02T02:05:45Z",
    "updated_at": "2026-11-02T03:00:00Z",
    "evidence": {
        "confidence": "media",
        "language_mix": [
            {"language": "en", "share_pct": 80.0},
            {"language": "es", "share_pct": 15.0},
            {"language": "unknown", "share_pct": 5.0},
        ],
        "gate": {
            "min_automation": 90,
            "max_human_minutes": 60,
            "max_calibration_hours": 40,
            "block_high_policy_risk": True,
            "passed": True,
            "reasons": [],
        },
    },
    "dossier": {
        "schema_version": "dossier-v3",
        "request_id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6",
        "niche_label": "personal_finance",
        "format": "long",
        "language": "en",
        "horizon": "short",
        "generated_at": "2026-11-02T03:00:00+00:00",
        "verdict": {
            "recommendation": "go_with_conditions",
            "confidence": "medium",
            "thesis": "Nicho con demanda estable y producción parcialmente automatizable.",
            "main_risks": ["Dependencia de voz sintética aceptada por la plataforma"],
            "unknowns": ["RPM real del nicho en el país objetivo"],
            "conditions": ["Pasar a régimen tras 3 videos seguidos bajo 60 minutos humanos"],
        },
        "competitors": [
            {
                "name": "Canal A",
                "channel_url": "https://www.youtube.com/@canal-a",
                "subscribers": 120000,
                "cadence": "3 videos por semana",
                "format": "long",
                "production_style": "Voz en off con material de archivo",
                "evidence_kind": "researched",
                "source_id": "s1",
            },
            {
                "name": "Canal B",
                "channel_url": "https://www.youtube.com/@canal-b",
                "subscribers": 120000,
                "cadence": "3 videos por semana",
                "format": "long",
                "production_style": "Voz en off con material de archivo",
                "evidence_kind": "researched",
                "source_id": "s2",
            },
            {
                "name": "Canal C",
                "channel_url": "https://www.youtube.com/@canal-c",
                "subscribers": 120000,
                "cadence": "3 videos por semana",
                "format": "long",
                "production_style": "Voz en off con material de archivo",
                "evidence_kind": "researched",
                "source_id": "s3",
            },
        ],
        "production_flow": [
            {
                "order": 1,
                "name": "Guion",
                "human_minutes_per_video": 20,
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
                "human_minutes_per_video": 30,
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
                    "price_checked_on": "2026-10-23",
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
                    "price_checked_on": "2026-10-23",
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
                    "price_checked_on": "2026-10-23",
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
                    "price_checked_on": "2026-10-23",
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
        "rights": {
            "verdict": "cleared",
            "summary": "Material propio generado o con licencia comercial vigente.",
            "materials": [
                {
                    "kind": "visual",
                    "description": "Gráficos y capturas generados por el propio pipeline",
                    "origin": "own_generation",
                    "license_or_policy": "Producción propia, sin material de terceros",
                    "requires_permission": False,
                },
                {
                    "kind": "audio",
                    "description": "Música de banco con licencia comercial",
                    "origin": "licensed",
                    "license_or_policy": "Licencia mensual que cubre uso comercial en YouTube",
                    "source_id": "s2",
                    "requires_permission": False,
                },
                {
                    "kind": "voice",
                    "description": "Narración sintética del plan de voz",
                    "origin": "licensed",
                    "license_or_policy": "El plan incluye licencia comercial de la voz",
                    "source_id": "s2",
                    "requires_permission": False,
                },
            ],
            "conditions": [],
        },
        "automation_plan": {
            "summary": "El guion lo redacta un modelo con datos "
            "verificados por una persona, la voz se sintetiza "
            "sin intervención y el montaje parte de una "
            "plantilla con cortes ajustados a mano; la "
            "revisión final siempre es humana.",
            "stages": [
                {
                    "step": "Guion",
                    "mode": "semi",
                    "approach": "Un modelo de lenguaje redacta el "
                    "borrador a partir de una ficha de "
                    "datos con fuentes citadas; una "
                    "persona verifica cada cifra y "
                    "reescribe el análisis propio antes "
                    "de pasar a la voz. Se guarda la "
                    "ficha.",
                    "tools": [
                        {"name": "Voz sintética", "interface": "API", "cost_usd_per_video": 0.5}
                    ],
                    "inputs": "Ficha de datos con fuentes",
                    "outputs": "Guion final aprobado",
                    "quality_gate": "Cada cifra tiene fuente y fue revisada por una persona",
                    "failure_mode": "El modelo inventa una cifra",
                    "retry_policy": "Regenerar el borrador con la ficha corregida, máximo 2 veces",
                    "human_minutes_per_video": 20,
                    "stays_human": "Verificar los hechos y escribir el análisis original",
                },
                {
                    "step": "Voz",
                    "mode": "auto",
                    "approach": "El guion aprobado se envía por API "
                    "al servicio de voz sintética con una "
                    "voz fija; se transcribe el resultado "
                    "y se compara con el guion para "
                    "detectar omisiones o repeticiones "
                    "antes de continuar al montaje.",
                    "tools": [
                        {"name": "Voz sintética", "interface": "API", "cost_usd_per_video": 1.0}
                    ],
                    "inputs": "Guion final aprobado",
                    "outputs": "Audio narrado y su transcripción",
                    "quality_gate": "El error de palabras no supera el umbral configurado",
                    "failure_mode": "El servicio repite o recorta una frase",
                    "retry_policy": "Resintetizar solo el fragmento fallido, máximo 3 veces",
                    "human_minutes_per_video": 5,
                    "stays_human": "Escuchar el resultado final",
                },
                {
                    "step": "Edición",
                    "mode": "semi",
                    "approach": "Una plantilla de proyecto coloca "
                    "audio, subtítulos y gráficos de "
                    "forma automática; una persona ajusta "
                    "cortes y ritmo y aprueba el render. "
                    "La plantilla varía entre videos para "
                    "no repetir la estructura.",
                    "tools": [
                        {
                            "name": "Editor de video",
                            "interface": "Aplicación de escritorio",
                            "cost_usd_per_video": 0,
                        }
                    ],
                    "inputs": "Audio, subtítulos y gráficos",
                    "outputs": "Video renderizado",
                    "quality_gate": "Duración, volumen y subtítulos pasan la revisión numérica",
                    "failure_mode": "El render sale con subtítulos desfasados",
                    "retry_policy": "Volver a renderizar tras corregir la plantilla",
                    "human_minutes_per_video": 30,
                    "stays_human": "Ritmo y cortes",
                },
            ],
            "milestones": [
                {
                    "order": 1,
                    "name": "Voz y guion automatizados",
                    "description": "Se automatiza la cadena de "
                    "guion asistido y voz "
                    "sintética con sus controles "
                    "de calidad, y se mide cuántos "
                    "minutos humanos exige cada "
                    "video de prueba durante la "
                    "preparación del canal.",
                    "acceptance_criteria": ["Un video de prueba con voz sin edición manual"],
                    "depends_on": [],
                },
                {
                    "order": 2,
                    "name": "Montaje con plantilla",
                    "description": "Se construye la plantilla de "
                    "montaje que ensambla audio, "
                    "subtítulos y gráficos, de "
                    "modo que la persona solo "
                    "ajuste cortes y apruebe el "
                    "render final de cada video "
                    "del piloto.",
                    "acceptance_criteria": ["Un video completo en menos de 30 minutos humanos"],
                    "depends_on": [1],
                },
            ],
        },
        "sources": [
            {
                "id": "s1",
                "url": "https://example.com/fuente-1",
                "title": "Fuente 1",
                "accessed_on": "2026-10-23",
            },
            {
                "id": "s2",
                "url": "https://example.com/fuente-2",
                "title": "Fuente 2",
                "accessed_on": "2026-10-23",
            },
            {
                "id": "s3",
                "url": "https://example.com/fuente-3",
                "title": "Fuente 3",
                "accessed_on": "2026-10-23",
            },
        ],
        "calibration": {
            "videos": 6,
            "setup_hours": 8.0,
            "exit_criterion": {
                "max_minutes_per_video": 60,
                "consecutive_videos": 3,
                "statement": "Pasar a régimen tras 3 videos seguidos bajo 60 minutos humanos",
            },
            "minutes_by_step": [
                {"step": "Guion", "minutes_per_video": 40},
                {"step": "Voz", "minutes_per_video": 10},
                {"step": "Edición", "minutes_per_video": 45},
            ],
        },
        "steady_state_evidence": {
            "basis": "measured",
            "reference_channel": "canal-historias",
            "reference_minutes_per_video": 20,
            "reference_sample_videos": 10,
            "format_match": "Mismo formato (narración larga sin rostro) e idioma (inglés)",
        },
    },
    "dossier_created_at": "2026-11-02T03:00:00Z",
}

PILOT_ID = "pil_20261102_historia"
CALIBRATING_ID = "pil_20261026_finanzas"
_NOW = "2026-11-03T12:00:00Z"


def _totals(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "videos": 0,
        "published": 0,
        "measured": 0,
        "by_stage": {},
        "spent_usd": 0,
        "equivalent_usd": 0,
        "machine_minutes": 0,
        "machine_minutes_complete": True,
    }
    return base | over


def _check(check_id: str, label: str, ok: bool, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": check_id,
        "label": label,
        "ok": ok,
        "detail": None,
        "expires_at": None,
    }
    return base | over


_CHECKS = [
    _check("youtube_oauth", "Autorizar subida y medición de YouTube", True,
           expires_at="2026-11-08T00:00:00Z"),
    _check("channel_dir", "Carpeta del canal en la Mac", False, detail="No se encontró."),
]  # fmt: skip


def _pilot(pilot_id: str, label: str, status: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "pilot_id": pilot_id,
        "status": status,
        "niche_label": label,
        "format": "long",
        "target_channel": "canal-historias",
        "authorized_at": "2026-11-02T03:00:00Z",
        "last_report_at": None,
        "channel_last_contact_at": None,
        "totals": _totals(),
        "proposal": {
            "action": "sin_datos_suficientes",
            "reason": "Aún no hay medición suficiente.",
        },
        "needs_decision": False,
        "valid_until": "2026-11-16T03:00:00Z",
        "delivered_at": None,
        "channel": None,
    }
    return base | over


PILOTS: list[dict[str, Any]] = [
    _pilot(
        PILOT_ID, "historia militar explicada", "entregado",
        delivered_at="2026-11-03T10:00:00Z",
        channel_last_contact_at="2026-11-03T11:00:00Z",
        channel={"reported_at": "2026-11-03T11:00:00Z", "channel_status": "active",
                 "note": None, "checks": _CHECKS},
    ),
    _pilot(
        "pil_20261030_ciencia", "ciencia en español", "decision_pendiente",
        needs_decision=True, last_report_at="2026-11-03T08:00:00Z",
        channel_last_contact_at="2026-11-03T08:00:00Z",
        totals=_totals(videos=10, published=10, measured=8, spent_usd=18.5,
                       equivalent_usd=120, machine_minutes=640),
        proposal={"action": "cerrar", "reason": "Dos hitos fallidos seguidos."},
    ),
    _pilot(
        "pil_20261101_cine", "cine de terror explicado", "autorizado",
        valid_until="2026-11-05T03:00:00Z",
    ),
    _pilot("pil_20261020_viejo", "viajes baratos", "cerrado"),
    _pilot(
        CALIBRATING_ID, "finanzas personales explicadas", "en_ejecucion",
        last_report_at="2026-11-03T09:00:00Z", channel_last_contact_at="2026-11-03T09:00:00Z",
        totals=_totals(videos=5, published=5, measured=3, spent_usd=2.4, machine_minutes=310),
    ),
]  # fmt: skip

PILOT_DETAIL: dict[str, Any] = PILOTS[0] | {
    "language": "en",
    "authorized_by": "propietario (web)",
    "first_report_at": None,
    "closed_at": None,
    "close_reason": None,
    "package": {
        "niche": {"label": "historia militar explicada", "format": "long", "language": "en"},
        "dossier": {
            "request_id": "f0c90924-295a-4136-a0fb-d3fb2c3eacc6",
            "schema": "dossier-v3",
            "recommendation": "go",
            "confidence": "medium",
            "thesis": "Historia militar con voz neutra",
            "unknowns": [],
        },
        "budget": {
            "currency": "USD", "low": 3, "likely": 19.5, "high": 41, "max_videos": 10,
            "basis": "Estimación del dossier",
        },
        "stop_rules": [
            {"text": "Cerrar si no hay 1.000 vistas al video 10",
             "milestone": {"kind": "video", "value": 10}},
            {"text": "Revisar la retención a la semana 6",
             "milestone": {"kind": "week", "value": 6}},
        ],
        "close_after_failed_milestones": 2,
    },
    "evaluation": {
        "rules": [
            {"id": "r1", "text": "Cerrar si no hay 1.000 vistas al video 10",
             "milestone": "video:10", "status": "pendiente", "detail": "Aún no hay datos."},
            {"id": "r2", "text": "Revisar la retención a la semana 6",
             "milestone": "week:6", "status": "sin_datos_suficientes", "detail": None},
        ],
        "milestones": [], "totals": {}, "warnings": [], "close_after": 2,
    },
    "acknowledged": [],
    "events": [
        {"kind": "authorized", "actor": "propietario (web)", "at": "2026-11-02T03:00:00Z",
         "detail": {"note": "Autorizado desde la web"}},
        {"kind": "delivered", "actor": "canal", "at": "2026-11-03T10:00:00Z", "detail": {}},
    ],
}  # fmt: skip
PILOT_VIDEOS: list[dict[str, Any]] = [
    {
        "video_id": "v1", "source_state": "PUBLICADO", "stage": "published",
        "visibility": "public", "published_at": "2026-11-05T12:00:00Z", "cost_usd": 0.32,
        "cost_equivalent_usd": 1.5, "machine_minutes": 70, "failure_code": None,
        "measurement": None,
    }
]  # fmt: skip


def _human(
    video_id: str, minutes: int | None, method: str | None = "claude_sessions_plus_assumed"
) -> dict[str, Any]:
    return PILOT_VIDEOS[0] | {
        "video_id": video_id,
        "published_at": f"2026-10-{26 + int(video_id[1:]):02d}T12:00:00Z",  # before «today» (3 nov)
        "human_minutes": minutes,
        "human_minutes_method": method if minutes is not None else None,
    }


# A pilot in calibration: two videos over the 60-minute criterion, a measured zero, then a run of
# two under it, and one not measured yet (never shown as 0 min).
CALIBRATION_VIDEOS: list[dict[str, Any]] = [
    _human("v1", 85), _human("v2", 70), _human("v3", 0), _human("v4", 48), _human("v5", None),
]  # fmt: skip
CALIBRATION_DETAIL: dict[str, Any] = PILOT_DETAIL | {
    "pilot_id": CALIBRATING_ID,
    "status": "en_ejecucion",
    "niche_label": "finanzas personales explicadas",
}


SCHEDULE: dict[str, Any] = {
    "paused": True,
    "next_due_at": "2026-11-04T11:00:00+00:00",
    "interval_seconds": 86400,
    "mode": "live",
    "live_enabled": True,
    "radar_paused": True,
}


def _run(
    key: str, status: str, stage: str, day: str, mins: int, code: str | None
) -> dict[str, Any]:
    start, end = f"2026-11-{day}T11:00:00+00:00", f"2026-11-{day}T11:{mins:02d}:00+00:00"
    return {
        "id": f"7a1b2c3d-0000-4000-8000-0000000000{key}",
        "run_key": f"run-{key}",
        "analysis_run_id": None,
        "status": status,
        "stage": stage,
        "attempts": 1,
        "lease_owner": None,
        "lease_until": None,
        "checkpoints": {},
        "error_code": code,
        "stats": {},
        "started_at": start,
        "finished_at": end,
        "created_at": start,
    }


RUNS: list[dict[str, Any]] = [
    _run("03", "partial", "detail", "03", 21, None),
    _run("02", "succeeded", "snapshot", "02", 9, None),
    _run("01", "failed", "list", "01", 2, "timeout"),
]

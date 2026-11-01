# tests/flow_research_samples.py
import copy
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

EXIT_STATEMENT = "Pasar a régimen tras 3 videos seguidos bajo 60 minutos humanos"


def valid_dossier(request_id: UUID, now: datetime) -> dict[str, Any]:
    """A complete, internally consistent dossier-v3 (JSON-shaped, as the skill sends it)."""
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
        "schema_version": "dossier-v3",
        "request_id": str(request_id),
        "niche_label": "personal_finance",
        "format": "long",
        "language": "en",
        "horizon": "short",
        "generated_at": now.isoformat(),
        "verdict": {
            "recommendation": "go_with_conditions",
            "confidence": "medium",
            "thesis": "Nicho con demanda estable y producción parcialmente automatizable.",
            "main_risks": ["Dependencia de voz sintética aceptada por la plataforma"],
            "unknowns": ["RPM real del nicho en el país objetivo"],
            "conditions": [EXIT_STATEMENT],
        },
        "competitors": competitors,
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
            "summary": (
                "El guion lo redacta un modelo con datos verificados por una persona, la voz se "
                "sintetiza sin intervención y el montaje parte de una plantilla con cortes "
                "ajustados a mano; la revisión final siempre es humana."
            ),
            "stages": [
                {
                    "step": "Guion",
                    "mode": "semi",
                    "approach": (
                        "Un modelo de lenguaje redacta el borrador a partir de una ficha de "
                        "datos con fuentes citadas; una persona verifica cada cifra y reescribe "
                        "el análisis propio antes de pasar a la voz. Se guarda la ficha."
                    ),
                    "tools": [
                        {
                            "name": "Voz sintética",
                            "interface": "API",
                            "cost_usd_per_video": 0.5,
                        }
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
                    "approach": (
                        "El guion aprobado se envía por API al servicio de voz sintética con una "
                        "voz fija; se transcribe el resultado y se compara con el guion para "
                        "detectar omisiones o repeticiones antes de continuar al montaje."
                    ),
                    "tools": [
                        {
                            "name": "Voz sintética",
                            "interface": "API",
                            "cost_usd_per_video": 1.0,
                        }
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
                    "approach": (
                        "Una plantilla de proyecto coloca audio, subtítulos y gráficos de forma "
                        "automática; una persona ajusta cortes y ritmo y aprueba el render. La "
                        "plantilla varía entre videos para no repetir la estructura."
                    ),
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
                    "description": (
                        "Se automatiza la cadena de guion asistido y voz sintética con sus "
                        "controles de calidad, y se mide cuántos minutos humanos exige cada video "
                        "de prueba durante la preparación del canal."
                    ),
                    "acceptance_criteria": ["Un video de prueba con voz sin edición manual"],
                    "depends_on": [],
                },
                {
                    "order": 2,
                    "name": "Montaje con plantilla",
                    "description": (
                        "Se construye la plantilla de montaje que ensambla audio, subtítulos y "
                        "gráficos, de modo que la persona solo ajuste cortes y apruebe el render "
                        "final de cada video del piloto."
                    ),
                    "acceptance_criteria": ["Un video completo en menos de 30 minutos humanos"],
                    "depends_on": [1],
                },
            ],
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
        "calibration": {
            "videos": 6,
            "setup_hours": 8.0,
            "exit_criterion": {
                "max_minutes_per_video": 60,
                "consecutive_videos": 3,
                "statement": EXIT_STATEMENT,
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
    }


def valid_dossier_v2(request_id: UUID, now: datetime) -> dict[str, Any]:
    """The same dossier as ``valid_dossier`` in the dossier-v2 shape (stored before dossier-v3)."""
    payload = copy.deepcopy(valid_dossier(request_id, now))
    payload["schema_version"] = "dossier-v2"
    del payload["calibration"], payload["steady_state_evidence"]
    del payload["verdict"]["conditions"]
    return payload

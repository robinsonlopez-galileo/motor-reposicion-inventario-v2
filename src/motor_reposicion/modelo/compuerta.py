"""Criterio de reemplazo del modelo vigente (DECISIONES.md, D10).

1. El candidato debe tener menor costo que el baseline en la validación.
2. Si no hay modelo vigente, el candidato pasa a ser el vigente; si no supera al baseline, el
   vigente pasa a ser el baseline (el motor nunca se queda sin modelo).
3. Si hay vigente, el candidato lo reemplaza solo si baja el costo al menos ``min_improvement_pct``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

PROMOVER = "promover_candidato"
CONSERVAR = "conservar_vigente"
BASELINE = "usar_baseline"


@dataclass(frozen=True)
class Decision:
    accion: str
    motivo: str
    metrica: str
    valor_candidato: float
    valor_baseline: float
    valor_vigente: float | None
    mejora_pct: float | None

    def como_dict(self) -> dict:
        return asdict(self)


def _fmt(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", " ")


def decidir(
    metricas_candidato: dict,
    metricas_baseline: dict,
    metricas_vigente: dict | None,
    metrica: str = "costo_total",
    mejora_minima_pct: float = 2.0,
) -> Decision:
    c = float(metricas_candidato[metrica])
    b = float(metricas_baseline[metrica])
    v = float(metricas_vigente[metrica]) if metricas_vigente else None
    mejora = None if v in (None, 0) else round((v - c) / v * 100, 2)

    if c >= b:
        motivo = f"El candidato ({_fmt(c)}) no mejora al baseline ({_fmt(b)}) en {metrica}"
        if v is None:
            return Decision(BASELINE, motivo + "; el baseline queda como vigente", metrica,
                            c, b, v, mejora)
        return Decision(CONSERVAR, motivo + "; se conserva el vigente", metrica, c, b, v, mejora)

    if v is None:
        return Decision(PROMOVER, f"No hay modelo vigente y el candidato ({_fmt(c)}) mejora al "
                        f"baseline ({_fmt(b)})", metrica, c, b, v, mejora)
    if mejora is not None and mejora >= mejora_minima_pct:
        return Decision(PROMOVER, f"El candidato baja {metrica} {mejora:.2f} % frente al vigente "
                        f"({_fmt(c)} vs {_fmt(v)})", metrica, c, b, v, mejora)
    return Decision(CONSERVAR, f"Mejora frente al vigente de {mejora:.2f} %, menor que "
                    f"{mejora_minima_pct:.2f} % ({_fmt(c)} vs {_fmt(v)})", metrica, c, b, v, mejora)

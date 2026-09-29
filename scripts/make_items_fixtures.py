"""Generador de fixtures sintéticos (12/11/10 ítems, textos largos).

Sin datos reales: artículos genéricos. Uso:
    python scripts/make_items_fixtures.py
Escribe fixtures/remito_12_items.json (+11/+10 por truncado).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from fasa_print_agent.remito_data import (  # noqa: E402
    RemitoCtaCte,
    RemitoItem,
    sample_fixture,
)

LONG_DETALLE = (
    "Perfil ángulo galvanizado de ala ancha para estructuras metálicas "
    "pesadas con tratamiento anticorrosivo doble mano"
)


def make_items(n: int) -> list[RemitoItem]:
    items = []
    for i in range(1, n + 1):
        items.append(RemitoItem(
            cantidad=f"{i * 2},00",
            articulo=f"AR{i:05d}",
            detalle=LONG_DETALLE if i % 3 == 0 else f"Artículo sintético {i}",
        ))
    return items


def main() -> None:
    base = sample_fixture()
    for n in (12, 11, 10):
        raw = base.to_dict()
        raw["items"] = [it.to_dict() for it in make_items(n)]
        raw["numero"] = f"0004-0000{n:04d}"
        data = RemitoCtaCte.from_dict(raw)
        out = REPO / "fixtures" / f"remito_{n}_items.json"
        out.write_text(json.dumps(data.to_dict(), indent=2,
                                  ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(f"{out.name}: {n} ítems")


if __name__ == "__main__":
    main()

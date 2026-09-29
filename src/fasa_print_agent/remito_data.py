"""Datos variables del REMITO_CTACTE.

Fixture de primera calibración (no hardcodeado en la lógica: viene de
`sample_fixture()` / JSON externo y se inyecta al generador de PDF).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RemitoItem:
    cantidad: str = ""
    articulo: str = ""
    detalle: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "RemitoItem":
        return cls(
            cantidad=str(data.get("cantidad", "")),
            articulo=str(data.get("articulo", "")),
            detalle=str(data.get("detalle", "")),
        )

    def to_dict(self) -> dict:
        return {"cantidad": self.cantidad, "articulo": self.articulo,
                "detalle": self.detalle}


@dataclass
class RemitoCtaCte:
    numero: str = ""
    fecha: str = ""
    cliente_nombre: str = ""
    cliente_codigo: str = ""
    cliente_cuit: str = ""
    cliente_cond_iva: str = ""
    # Datos extendidos del cliente. `cliente_localidad` llega ya resuelto
    # (en el ERP: join con la tabla `localidad`); el agente solo lo dibuja.
    cliente_domicilio: str = ""
    cliente_telefono: str = ""
    cliente_cp: str = ""
    cliente_localidad: str = ""
    items: list[RemitoItem] = field(default_factory=list)
    observaciones: str = ""
    transp_nombre: str = ""
    transp_cuit: str = ""
    transp_domicilio: str = ""
    transp_chofer: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "RemitoCtaCte":
        items = [RemitoItem.from_dict(i) for i in data.get("items", [])]
        return cls(
            numero=str(data.get("numero", "")),
            fecha=str(data.get("fecha", "")),
            cliente_nombre=str(data.get("cliente_nombre", "")),
            cliente_codigo=str(data.get("cliente_codigo", "")),
            cliente_cuit=str(data.get("cliente_cuit", "")),
            cliente_cond_iva=str(data.get("cliente_cond_iva", "")),
            cliente_domicilio=str(data.get("cliente_domicilio", "")),
            cliente_telefono=str(data.get("cliente_telefono", "")),
            cliente_cp=str(data.get("cliente_cp", "")),
            cliente_localidad=str(data.get("cliente_localidad", "")),
            items=items,
            observaciones=str(data.get("observaciones", "")),
            transp_nombre=str(data.get("transp_nombre", "")),
            transp_cuit=str(data.get("transp_cuit", "")),
            transp_domicilio=str(data.get("transp_domicilio", "")),
            transp_chofer=str(data.get("transp_chofer", "")),
        )

    def to_dict(self) -> dict:
        return {
            "numero": self.numero,
            "fecha": self.fecha,
            "cliente_nombre": self.cliente_nombre,
            "cliente_codigo": self.cliente_codigo,
            "cliente_cuit": self.cliente_cuit,
            "cliente_cond_iva": self.cliente_cond_iva,
            "cliente_domicilio": self.cliente_domicilio,
            "cliente_telefono": self.cliente_telefono,
            "cliente_cp": self.cliente_cp,
            "cliente_localidad": self.cliente_localidad,
            "items": [i.to_dict() for i in self.items],
            "observaciones": self.observaciones,
            "transp_nombre": self.transp_nombre,
            "transp_cuit": self.transp_cuit,
            "transp_domicilio": self.transp_domicilio,
            "transp_chofer": self.transp_chofer,
        }


def sample_fixture() -> RemitoCtaCte:
    """Datos de prueba de la primera calibración (29/09/2026)."""
    return RemitoCtaCte(
        numero="0004-00000956",
        fecha="29/09/2026",
        cliente_nombre="VOGEL JOSE OSCAR",
        cliente_codigo="00040",
        cliente_cuit="20-23347203-5",
        cliente_cond_iva="",
        items=[RemitoItem(cantidad="10,00", articulo="PE00037",
                          detalle="Perfil T 25mm")],
        observaciones="",
        transp_nombre="CENTRAL ARGENTINO S.A.",
        transp_cuit="30-54650428-6",
        transp_domicilio="AV BUCHARDO 2413",
        transp_chofer="",
    )

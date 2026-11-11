"""rto.py - one RTO planilla (a row of the 'Lista de Planillas' page)."""

import enum
import re
from dataclasses import dataclass

# Old format ABC123, Mercosur format AB123CD.
_PATENTE_RE = re.compile(r"[A-Z]{3}\d{3}|[A-Z]{2}\d{3}[A-Z]{2}")
_PLACEHOLDER_PLATES = ("000000", "999999")      # slots without a real vehicle


class PlanillaError(ValueError):
    """Raised when a planilla can't be built from the given data."""


class Linea(enum.Enum):
    LINEA_1 = 1
    LINEA_2 = 2
    LINEA_3 = 3

    @classmethod
    def parse(cls, text: "str | int | Linea") -> "Linea":
        """Accepts a Linea, 2, '2' or 'Línea 2'."""
        if isinstance(text, cls):
            return text
        match = re.search(r"\d+", str(text))
        try:
            return cls(int(match.group()))
        except (AttributeError, ValueError):
            raise PlanillaError(f"Línea inválida: {text!r}") from None


class Resultado(enum.Enum):
    NO_REVISADO = 0
    APTO = "Apto (1)"
    CONDICIONAL = "Condicional (2)"
    RECHAZADO = "Rechazado (3)"
    ANULADO = "Anulado (4)"

    @classmethod
    def parse(cls, text: "str | Resultado") -> "Resultado":
        """Accepts a Resultado, 'Apto (1)', 'apto', or '' (= not reviewed yet)."""
        if isinstance(text, cls):
            return text
        clean = (text or "").strip().lower()
        if not clean:
            return cls.NO_REVISADO
        for member in cls:
            if isinstance(member.value, str) and clean in (
                member.value.lower(),
                member.value.split(" (")[0].lower(),
            ):
                return member
        raise PlanillaError(f"Resultado inválido: {text!r}")


class TipoRevision(enum.Enum):
    GC = "Mercosur/Mercosur/GC"
    GCP = "Mercosur/Mercosur/GCP"
    GP = "Mercosur/Mercosur/GP"

    @classmethod
    def parse(cls, text: "str | TipoRevision") -> "TipoRevision":
        """Accepts a TipoRevision, the full text 'Mercosur/Mercosur/GC' or just 'GC'."""
        if isinstance(text, cls):
            return text
        clean = (text or "").strip().upper()
        for member in cls:
            if clean in (member.value.upper(), member.name):
                return member
        raise PlanillaError(f"Tipo de revisión inválido: {text!r}")


def clean_license_plate(license_plate: str) -> str:
    """Uppercase, without spaces or dashes."""
    return re.sub(r"[\s-]", "", license_plate or "").upper()


def is_license_plate_valid(license_plate: str) -> bool:
    """True for 'ABC123' or 'AB123CD' (case, spaces and dashes are ignored)."""
    return _PATENTE_RE.fullmatch(clean_license_plate(license_plate)) is not None


def is_available(license_plate: str) -> bool:
    """False for the placeholder plates '000000' and '999999'."""
    return clean_license_plate(license_plate) not in _PLACEHOLDER_PLATES


@dataclass
class RTO:
    dominio: str
    numero: "int | str | None"
    tipo_revision: "TipoRevision | str"
    linea: "Linea | str | int"
    resultado: "Resultado | str"
    inicio: str

    def __post_init__(self):
        self.dominio = clean_license_plate(self.dominio)
        if not is_available(self.dominio):
            raise PlanillaError(f"Dominio no disponible: {self.dominio!r}")
        if not is_license_plate_valid(self.dominio):
            raise PlanillaError(f"Formato de dominio inválido: {self.dominio!r}")

        if isinstance(self.numero, str):
            digits = self.numero.replace("-", "").replace(",", "").strip()
            self.numero = int(digits) if digits.isdigit() else None

        self.tipo_revision = TipoRevision.parse(self.tipo_revision)
        self.linea = Linea.parse(self.linea)
        self.resultado = Resultado.parse(self.resultado)

    @classmethod
    def try_create(cls, *args, **kwargs) -> "RTO | None":
        """Like RTO(...), but returns None instead of raising when the data is invalid
        (handy when reading rows from the web page)."""
        try:
            return cls(*args, **kwargs)
        except PlanillaError:
            return None

    def __str__(self) -> str:
        return (f"RTO(dominio={self.dominio}, numero={self.numero}, "
                f"tipo_revision={self.tipo_revision.name}, linea={self.linea.value}, "
                f"resultado={self.resultado.name}, inicio={self.inicio})")
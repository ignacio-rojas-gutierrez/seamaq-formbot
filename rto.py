import enum
import re


class RTO:
    class Linea(enum.Enum):
        LINEA_1 = 1
        LINEA_2 = 2
        LINEA_3 = 3

    class Resultado(enum.Enum):
        NO_REVISADO = 0 # no sé xd
        APTO = "Apto (1)"
        CONDICIONAL = "Condicional (2)"
        RECHAZADO = "Rechazado (3)"
        ANULADO = "Anulado (4)"

    class TipoRevision(enum.Enum):
        GC = "Mercosur/Mercosur/GC"
        GCP = "Mercosur/Mercosur/GCP"
        GP = "Mercosur/Mercosur/GP"


    def __init__(self, dominio: str, numero: str, tipo_revision: str, linea: str, resultado: str, inicio: str):
        if not self._is_license_plate_format_valid(dominio):
            return None
        
        if not self.is_available(dominio):
            return None

        self.dominio = dominio
        numero = numero.replace("-", "").replace(",", "")
        self.numero = int(numero) if numero.isdigit() else None
        self.tipo_revision = tipo_revision
        self.linea = linea
        self.resultado = resultado
        self.inicio = inicio


    def __init__(self, dominio: str, numero: str, tipo_revision: TipoRevision, linea: Linea, resultado: Resultado, inicio: str):
        if not self._is_license_plate_format_valid(dominio):
            return None
        
        if not self.is_available(dominio):
            return None

        self.dominio = dominio
        numero = numero.replace("-", "").replace(",", "")
        self.numero = int(numero) if numero.isdigit() else None
        self.tipo_revision = tipo_revision
        self.linea = linea
        self.resultado = resultado
        self.inicio = inicio

    def __str__(self):
        return f"Planilla(dominio={self.dominio}, numero={self.numero}, tipo_revision={self.tipo_de_revision}, tipo_de_uso={self.tipo_de_uso})"

    def _get_clean_license_plate(self, license_plate: str) -> str:
        """Returns the license plate in a clean format (uppercase, no spaces or dashes)."""
        return re.sub(r"[\s-]", "", license_plate).upper()

    def _is_license_plate_format_valid(self, license_plate: str) -> bool:
        """True si el texto es 'ABC123' o 'AB123CD' (se ignoran mayúsculas, espacios y guiones)."""
        clean = self._get_clean_license_plate(license_plate)
        return self._PATENTE_RE.fullmatch(clean) is not None

    def is_available(self, license_plate: str) -> bool:
        """True si la patente está disponible dentro de la lista de planillas disponibles en el momento (no es '000000' ni '999999')."""
        clean = self._get_clean_license_plate(license_plate)
        return clean not in ("000000", "999999")
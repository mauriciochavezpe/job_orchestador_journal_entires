from dataclasses import dataclass,field
from pathlib import Path
import os

@dataclass
class Config:
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    assets_dir: str = os.getenv("ASSETS_DIR", "assets")
    file_cab: str = os.getenv("FILE_CABECERA")
    file_det: str = os.getenv("FILE_DETALLE")
    sheet_cab: str | None = os.getenv("SHEET_NAME_CABECERA") or None
    sheet_det: str | None = os.getenv("SHEET_NAME_DETALLE") or None
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "500"))
    skip_rows: int = int(os.getenv("SKIP_ROWS", "1"))
    max_xlsx_bytes: int = int(os.getenv("MAX_XLSX_BYTES", str(200*1024*1024)))

    @property
    def cab_path(self) -> Path:
        if not self.file_cab:
            raise ValueError(f"La variable de entorno FILE_CABECERA no está definida. {self.project_root}")
        return self.project_root / self.assets_dir / self.file_cab

    @property
    def det_path(self) -> Path:
        return self.project_root / self.assets_dir / self.file_det
from __future__ import annotations

import io
from pathlib import Path

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage

from app.core.config import get_settings
from app.schemas.contract import ContractRenderContext
from app.services.master_template_service import ensure_master_template
from app.services.signature_asset_service import (
    SignatureAssetError,
    compose_executor_mark,
    prepare_signature_asset,
    validate_executor_asset_binding,
)


class ExecutorAssetsMissingError(FileNotFoundError):
    pass


def render_contract_docx(
    *,
    template_docx_path: Path,
    context: ContractRenderContext,
    output_path: Path,
    include_executor_signature: bool,
) -> Path:
    settings = get_settings()
    ensure_master_template(template_docx_path)
    doc = DocxTemplate(str(template_docx_path))

    data = context.model_dump()
    data["client_signature"] = ""
    data["client_signature_date"] = ""

    if include_executor_signature:
        sig_path = settings.signature_assets_dir / "executor_signature.png"
        stamp_path = settings.signature_assets_dir / "executor_stamp.png"
        missing = [path.name for path in (sig_path, stamp_path) if not path.exists()]
        if missing:
            raise ExecutorAssetsMissingError(
                "Не загружены подпись и/или печать Исполнителя. "
                "Откройте /signature_settings и загрузите оба PNG-файла."
            )
        signature_bytes = sig_path.read_bytes()
        stamp_bytes = stamp_path.read_bytes()
        try:
            validate_executor_asset_binding(
                settings.signature_assets_dir,
                signature_bytes=signature_bytes,
                stamp_bytes=stamp_bytes,
                identifier_label=settings.executor_identifier_label,
                identifier=settings.executor_identifier,
            )
            signature = prepare_signature_asset(signature_bytes, kind="signature")
            stamp = prepare_signature_asset(stamp_bytes, kind="stamp")
        except SignatureAssetError as exc:
            raise ExecutorAssetsMissingError(
                f"Файл подписи или печати некорректен: {exc}. "
                "Загрузите изображения заново через /signature_settings."
            ) from exc

        mark = compose_executor_mark(
            signature_png_bytes=signature.png_bytes,
            stamp_png_bytes=stamp.png_bytes,
            signer_short_name=settings.executor_signer_short_name,
            signature_width_mm=settings.executor_signature_width_mm,
            stamp_diameter_mm=settings.executor_stamp_diameter_mm,
            block_width_mm=settings.executor_signature_block_width_mm,
        )
        mark_stream = io.BytesIO(mark.png_bytes)
        data["executor_signature_block"] = InlineImage(
            doc,
            mark_stream,
            width=Mm(mark.width_mm),
        )
    else:
        data["executor_signature_block"] = ""

    doc.render(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path

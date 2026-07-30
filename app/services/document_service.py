from __future__ import annotations

import io
from pathlib import Path

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage

from app.core.config import get_settings
from app.schemas.contract import ContractRenderContext
from app.services.signature_asset_service import (
    SignatureAssetError,
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
    """Render the master docxtpl template into a concrete contract DOCX.

    Security invariant: client_signature / client_signature_date are ALWAYS rendered blank
    here, regardless of what the caller passes in `context`. The client's simple electronic
    signature is only ever composited onto the already-finalized PDF by signing_service,
    after the client's own explicit action - never via a docxtpl merge field. This keeps
    "no automatic client signature" enforced at the rendering layer, not just by convention.
    """
    settings = get_settings()
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

        # Millimetres are deliberate physical print sizes. Pixel dimensions never influence
        # the result, and only width is set so Word/LibreOffice cannot distort the aspect ratio.
        signature_stream = io.BytesIO(signature.png_bytes)
        stamp_stream = io.BytesIO(stamp.png_bytes)
        data["executor_signature"] = InlineImage(
            doc,
            signature_stream,
            width=Mm(settings.executor_signature_width_mm),
        )
        data["executor_stamp"] = InlineImage(
            doc,
            stamp_stream,
            width=Mm(settings.executor_stamp_diameter_mm),
        )
    else:
        data["executor_signature"] = ""
        data["executor_stamp"] = ""

    doc.render(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path

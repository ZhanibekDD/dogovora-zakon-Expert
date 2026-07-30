from __future__ import annotations

from pathlib import Path

from docx.shared import Cm
from docxtpl import DocxTemplate, InlineImage

from app.core.config import get_settings
from app.schemas.contract import ContractRenderContext


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
        data["executor_signature"] = InlineImage(doc, str(sig_path), width=Cm(4.5))
        data["executor_stamp"] = InlineImage(doc, str(stamp_path), width=Cm(4.0))
    else:
        data["executor_signature"] = ""
        data["executor_stamp"] = ""

    doc.render(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path

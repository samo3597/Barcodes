"""Versioned prompt registry kept in source control for reproducible AI runs."""

PROMPT_VERSIONS: dict[str, str] = {
    "product-v1": (
        "Return strict JSON for name, four-digit atg_code, vat, is_weighted, category_id, "
        "per-field confidence, and warnings. Never change the supplied barcode."
    ),
    "product-v2": (
        "Return the product contract as strict JSON. Preserve barcode, explain every default in "
        "warnings, and assign confidence independently for each canonical field."
    ),
}


def get_prompt(version: str) -> str:
    """Resolve only deployed prompt versions; arbitrary runtime prompt text is forbidden."""

    try:
        return PROMPT_VERSIONS[version]
    except KeyError as error:
        raise ValueError(f"unknown prompt version: {version}") from error

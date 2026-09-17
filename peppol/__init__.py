"""Free subset: UBL 2.1 schema validation + Peppol BIS Billing 3.0 rule checks.

This is the validator only. The full toolkit adds invoice generation, the
Belgian specifics (OGM/VAT/endpoint helpers) and the fixture corpus.
"""
from .xsd import validate_xsd, SchemaError
from .rules import check_rules, RuleFinding

__version__ = "1.0.0"
__all__ = ["validate_xsd", "SchemaError", "check_rules", "RuleFinding"]

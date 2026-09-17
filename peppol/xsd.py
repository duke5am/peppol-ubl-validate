"""Validate a UBL document against the official OASIS UBL 2.1 schemas.

This is authoritative schema validation: the schemas in ../schema are the
published OASIS UBL 2.1 XSDs, so a document that passes here is
schema-valid UBL. It does NOT check Peppol business rules - use
`peppol.rules.check_rules` for those.
"""
import os
from lxml import etree

_HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_DIR = os.path.normpath(os.path.join(_HERE, "..", "schema"))
_INVOICE_XSD = os.path.join(SCHEMA_DIR, "maindoc", "UBL-Invoice-2.1.xsd")
_CREDITNOTE_XSD = os.path.join(SCHEMA_DIR, "maindoc", "UBL-CreditNote-2.1.xsd")

_cache: dict = {}


class SchemaError(RuntimeError):
    """Raised when the schemas themselves cannot be loaded."""


def _schema(path: str):
    if path not in _cache:
        if not os.path.exists(path):
            raise SchemaError(
                f"schema not found at {path}. The 'schema/' directory must sit "
                f"next to the 'peppol/' package."
            )
        try:
            _cache[path] = etree.XMLSchema(etree.parse(path))
        except Exception as exc:
            raise SchemaError(f"could not load schema {path}: {exc}") from exc
    return _cache[path]


def _root_localname(doc) -> str:
    if isinstance(doc, (str, bytes)):
        doc = etree.fromstring(doc.encode("utf-8") if isinstance(doc, str) else doc)
    return etree.QName(doc.getroot() if hasattr(doc, "getroot") else doc).localname


def validate_xsd(doc, raise_on_error: bool = False):
    """Validate and return (is_valid, [error messages]).

    `doc` may be an XML string, bytes, an Element, or an ElementTree.
    """
    if isinstance(doc, str):
        doc = doc.encode("utf-8")
    try:
        tree = etree.parse(__import__("io").BytesIO(doc)) if isinstance(doc, bytes) else doc
    except etree.XMLSyntaxError as exc:
        return False, [f"XML is not well-formed: {exc}"]
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    name = etree.QName(root).localname
    if name == "CreditNote":
        sch = _schema(_CREDITNOTE_XSD)
    elif name == "Invoice":
        sch = _schema(_INVOICE_XSD)
    else:
        return False, [f"root element must be Invoice or CreditNote, got {name}"]
    ok = sch.validate(tree)
    errors = [f"line {e.line}: {e.message}" for e in sch.error_log]
    if not ok and raise_on_error:
        raise ValueError("schema validation failed:\n  " + "\n  ".join(errors))
    return ok, errors

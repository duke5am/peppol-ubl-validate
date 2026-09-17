"""Peppol BIS Billing 3.0 business-rule checks.

IMPORTANT SCOPE: these checks are a re-implementation, in Python, of rules
published in the official Peppol BIS Billing 3.0 rule list. They are NOT the
official OpenPEPPOL Schematron, which is distributed to Peppol members and is
not the same artefact. Rule IDs are quoted from the published list so a
finding can be looked up.

A document passing these checks is *very likely* Peppol-conformant, but the
authoritative test is validation by a registered Peppol Access Point or the
official Schematron. Treat a pass here as necessary, not sufficient.
"""
from dataclasses import dataclass
from decimal import Decimal
from lxml import etree

CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"

VAT_ID = "VAT"
SEVERITIES = ("fatal", "warning", "information")


@dataclass
class RuleFinding:
    rule_id: str
    severity: str
    message: str
    path: str = ""

    def __str__(self):
        loc = f" [{self.path}]" if self.path else ""
        return f"{self.severity.upper():11s} {self.rule_id:12s} {self.message}{loc}"


def _text(el):
    return (el.text or "").strip() if el is not None else ""


def _find(root, path):
    return root.find(path)


def _dec(s):
    try:
        return Decimal(s)
    except Exception:
        return None


def check_rules(doc, currency_tolerance: Decimal = Decimal("0.01")):
    """Return a list of RuleFinding. Empty list means no rule violations found."""
    if isinstance(doc, str):
        doc = doc.encode("utf-8")
    if isinstance(doc, bytes):
        root = etree.fromstring(doc)
    elif hasattr(doc, "getroot"):
        root = doc.getroot()
    else:
        root = doc

    is_cn = etree.QName(root).localname == "CreditNote"
    out: list = []
    add = lambda rid, sev, msg, path="": out.append(RuleFinding(rid, sev, msg, path))

    # ---------- mandatory fields ----------
    # BR-01..BR-16: mandatory business terms
    if not _text(root.find(f"{{{CBC}}}CustomizationID")):
        add("BR-01", "fatal", "Specification identifier (BT-24) is missing")
    if not _text(root.find(f"{{{CBC}}}ProfileID")):
        add("BR-02", "fatal", "Business process type (BT-23) is missing")
    inv_no = _text(root.find(f"{{{CBC}}}ID"))
    if not inv_no:
        add("BR-02", "fatal", "Invoice number (BT-1) is missing")
    if not _text(root.find(f"{{{CBC}}}IssueDate")):
        add("BR-03", "fatal", "Issue date (BT-2) is missing")
    tcode = _text(root.find(f"{{{CBC}}}{'CreditNoteTypeCode' if is_cn else 'InvoiceTypeCode'}"))
    if not tcode:
        add("BR-04", "fatal", "Invoice type code (BT-3) is missing")
    cur = _text(root.find(f"{{{CBC}}}DocumentCurrencyCode"))
    if not cur:
        add("BR-05", "fatal", "Document currency code (BT-5) is missing")

    # Supplier / customer presence and names
    sup = root.find(f"{{{CAC}}}AccountingSupplierParty/{{{CAC}}}Party")
    cus = root.find(f"{{{CAC}}}AccountingCustomerParty/{{{CAC}}}Party")
    def _party_name(party):
        """BT-27/BT-44 may appear as PartyName/Name or as
        PartyLegalEntity/RegistrationName. The official Peppol examples use
        the latter, so checking only PartyName gives false failures."""
        n = _text(party.find(f"{{{CAC}}}PartyName/{{{CBC}}}Name"))
        if n:
            return n
        return _text(party.find(f"{{{CAC}}}PartyLegalEntity/{{{CBC}}}RegistrationName"))

    if sup is None:
        add("BR-06", "fatal", "Seller (BG-4) is missing")
    elif not _party_name(sup):
        add("BR-06", "fatal", "Seller name (BT-27) is missing")
    if cus is None:
        add("BR-07", "fatal", "Buyer (BG-7) is missing")
    elif not _party_name(cus):
        add("BR-07", "fatal", "Buyer name (BT-44) is missing")

    # BR-08/BR-09: postal address present, and country identified
    for tag, label, rc in ((sup, "Seller", "BR-08"), (cus, "Buyer", "BR-09")):
        if tag is None:
            continue
        addr = tag.find(f"{{{CAC}}}PostalAddress")
        if addr is None:
            add(rc, "fatal", f"{label} postal address (BG-5/BG-8) is missing")
            continue
        if not _text(addr.find(f"{{{CAC}}}Country/{{{CBC}}}IdentificationCode")):
            add(rc, "fatal", f"{label} country code (BT-40/BT-55) is missing")

    # BR-CO-09: seller VAT identifier must start with a valid ISO country code
    if sup is not None:
        s_vat = _text(sup.find(f"{{{CAC}}}PartyTaxScheme/{{{CBC}}}CompanyID"))
        if s_vat and not (len(s_vat) >= 3 and s_vat[:2].isalpha()):
            add("BR-CO-09", "fatal",
                f"Seller VAT identifier '{s_vat}' must start with a 2-letter country code")

    # ---------- VAT category rules ----------
    subs = root.findall(f"{{{CAC}}}TaxTotal/{{{CAC}}}TaxSubtotal")
    if not subs:
        add("BR-CO-18", "fatal", "At least one VAT breakdown group (BG-23) is required")
    cat_percents = {}          # category -> set of rates present in the breakdown
    cat_rates = set()          # (category, rate) pairs present in the breakdown
    for st in subs:
        tc = st.find(f"{{{CAC}}}TaxCategory")
        cid = _text(tc.find(f"{{{CBC}}}ID")) if tc is not None else ""
        pct = _text(tc.find(f"{{{CBC}}}Percent")) if tc is not None else ""
        # BT-120 is the free-text reason; BT-121 is the coded form. Either
        # satisfies the requirement, and the official examples use the code.
        reason = ""
        if tc is not None:
            reason = (_text(tc.find(f"{{{CBC}}}TaxExemptionReason"))
                      or _text(tc.find(f"{{{CBC}}}TaxExemptionReasonCode")))
        pct_dec = _dec(pct)
        cat_percents.setdefault(cid, set()).add(pct_dec)
        cat_rates.add((cid, pct_dec))
        if not cid:
            add("BR-CO-04", "fatal", "VAT category code (BT-118) is missing in a breakdown")
        # BR-Z-* zero rated: percent must be 0
        if cid == "Z" and pct not in ("0", "0.0", "0.00"):
            add("BR-Z-05", "fatal", f"VAT category Z must have a rate of 0, got {pct}")
        if cid == "S":
            if pct in ("", "0", "0.0", "0.00"):
                add("BR-S-05", "fatal", f"VAT category S requires a rate above 0, got {pct!r}")
        # BR-E-10 / BR-AE-10: exemption reason mandatory
        if cid in ("E", "AE") and not reason:
            add("BR-E-10" if cid == "E" else "BR-AE-10", "fatal",
                f"VAT category {cid} requires a VAT exemption reason (BT-120)")
        if cid == "AE":
            # BR-AE-05: reverse charge must be 0
            if pct not in ("0", "0.0", "0.00"):
                add("BR-AE-05", "fatal", f"VAT category AE must have a rate of 0, got {pct}")

    # BR-O-*: out of scope must not be mixed with other categories
    if "O" in cat_percents and len(cat_percents) > 1:
        add("BR-O-11", "fatal",
            "An invoice containing an 'Out of scope' (O) category cannot contain other VAT categories")

    # ---------- arithmetic ----------
    tt = root.find(f"{{{CAC}}}TaxTotal/{{{CBC}}}TaxAmount")
    tax_total = _dec(_text(tt)) if tt is not None else None
    sum_sub = sum((_dec(_text(st.find(f"{{{CBC}}}TaxAmount"))) or Decimal(0) for st in subs), Decimal(0))
    if tax_total is not None and abs(tax_total - sum_sub) > currency_tolerance:
        add("BR-CO-14", "fatal",
            f"Tax total {tax_total} does not equal the sum of VAT category amounts {sum_sub}")

    lmt = root.find(f"{{{CAC}}}LegalMonetaryTotal")
    if lmt is None:
        add("BR-CO-15", "fatal", "Document totals (BG-22) are missing")
    else:
        get = lambda t: _dec(_text(lmt.find(f"{{{CBC}}}{t}")))
        line_ext = get("LineExtensionAmount")
        tax_excl = get("TaxExclusiveAmount")
        tax_incl = get("TaxInclusiveAmount")
        payable = get("PayableAmount")
        allow = get("AllowanceTotalAmount") or Decimal(0)
        charge = get("ChargeTotalAmount") or Decimal(0)

        # BR-CO-10: sum of line net amounts
        line_tag = "CreditNoteLine" if is_cn else "InvoiceLine"
        amt_tag = "LineExtensionAmount"
        lines = root.findall(f"{{{CAC}}}{line_tag}")
        if not lines:
            add("BR-16", "fatal", "An invoice must have at least one line (BG-25)")
        sum_lines = sum((_dec(_text(ln.find(f"{{{CBC}}}{amt_tag}"))) or Decimal(0) for ln in lines), Decimal(0))
        if line_ext is not None and abs(line_ext - sum_lines) > currency_tolerance:
            add("BR-CO-10", "fatal",
                f"Sum of line net amounts {sum_lines} does not equal LineExtensionAmount {line_ext}")

        # BR-CO-11/12: allowances and charges totals
        doc_allows = root.findall(f"{{{CAC}}}AllowanceCharge")
        sum_allow = sum((_dec(_text(a.find(f"{{{CBC}}}Amount"))) or Decimal(0)
                         for a in doc_allows
                         if _text(a.find(f"{{{CBC}}}ChargeIndicator")).lower() == "false"), Decimal(0))
        sum_charge = sum((_dec(_text(a.find(f"{{{CBC}}}Amount"))) or Decimal(0)
                          for a in doc_allows
                          if _text(a.find(f"{{{CBC}}}ChargeIndicator")).lower() == "true"), Decimal(0))
        if abs(sum_allow - allow) > currency_tolerance:
            add("BR-CO-11", "fatal",
                f"Sum of allowances {sum_allow} does not equal AllowanceTotalAmount {allow}")
        if abs(sum_charge - charge) > currency_tolerance:
            add("BR-CO-12", "fatal",
                f"Sum of charges {sum_charge} does not equal ChargeTotalAmount {charge}")

        # BR-CO-13: TaxExclusiveAmount = line total - allowances + charges
        if line_ext is not None and tax_excl is not None:
            expect = line_ext - allow + charge
            if abs(expect - tax_excl) > currency_tolerance:
                add("BR-CO-13", "fatal",
                    f"TaxExclusiveAmount {tax_excl} does not equal LineExtensionAmount - allowances + charges = {expect}")

        # BR-CO-15: TaxInclusiveAmount = TaxExclusiveAmount + TaxAmount
        if tax_excl is not None and tax_incl is not None and tax_total is not None:
            expect = tax_excl + tax_total
            if abs(expect - tax_incl) > currency_tolerance:
                add("BR-CO-15", "fatal",
                    f"TaxInclusiveAmount {tax_incl} does not equal TaxExclusiveAmount + TaxAmount = {expect}")

        # BR-CO-16: PayableAmount = TaxInclusiveAmount - prepaid
        prepaid = get("PrepaidAmount") or Decimal(0)
        if tax_incl is not None and payable is not None:
            expect = tax_incl - prepaid
            if abs(expect - payable) > currency_tolerance:
                add("BR-CO-16", "fatal",
                    f"PayableAmount {payable} does not equal TaxInclusiveAmount - PrepaidAmount = {expect}")

        # BR-CO-17: VAT category tax = taxable amount x rate / 100
        for st in subs:
            taxable = _dec(_text(st.find(f"{{{CBC}}}TaxableAmount")))
            cat_tax = _dec(_text(st.find(f"{{{CBC}}}TaxAmount")))
            tc = st.find(f"{{{CAC}}}TaxCategory")
            pct = _dec(_text(tc.find(f"{{{CBC}}}Percent"))) if tc is not None else None
            if taxable is not None and cat_tax is not None and pct is not None:
                expect = (taxable * pct / Decimal(100)).quantize(Decimal("0.01"))
                if abs(expect - cat_tax) > currency_tolerance:
                    add("BR-CO-17", "fatal",
                        f"VAT category tax {cat_tax} does not equal taxable amount x rate = {expect}")

        # BR-CO-18 pt.2: sum of taxable amounts = TaxExclusiveAmount
        sum_taxable = sum((_dec(_text(st.find(f"{{{CBC}}}TaxableAmount"))) or Decimal(0) for st in subs), Decimal(0))
        if tax_excl is not None and abs(sum_taxable - tax_excl) > currency_tolerance:
            add("BR-CO-18", "fatal",
                f"Sum of VAT taxable amounts {sum_taxable} does not equal TaxExclusiveAmount {tax_excl}")

    # ---------- line-level rules ----------
    line_tag = "CreditNoteLine" if is_cn else "InvoiceLine"
    qty_tag = "CreditedQuantity" if is_cn else "InvoicedQuantity"
    for i, ln in enumerate(root.findall(f"{{{CAC}}}{line_tag}"), start=1):
        p = f"{line_tag}[{i}]"
        qty = _dec(_text(ln.find(f"{{{CBC}}}{qty_tag}")))
        price = _dec(_text(ln.find(f"{{{CAC}}}Price/{{{CBC}}}PriceAmount")))
        # UBL price is quoted PER BaseQuantity (defaults to 1). The official
        # Peppol examples use BaseQuantity=2 with PriceAmount=200 to mean a unit
        # price of 100, so ignoring this mis-flags them as arithmetic errors.
        base_qty = _dec(_text(ln.find(f"{{{CAC}}}Price/{{{CBC}}}BaseQuantity"))) or Decimal(1)
        ext = _dec(_text(ln.find(f"{{{CBC}}}LineExtensionAmount")))
        # BR-CO-04: each line needs a VAT category
        ctc = ln.find(f"{{{CAC}}}Item/{{{CAC}}}ClassifiedTaxCategory")
        if ctc is None:
            add("BR-CO-04", "fatal", "Line is missing a VAT category code (BT-151)", p)
        else:
            lid = _text(ctc.find(f"{{{CBC}}}ID"))
            lpct = _text(ctc.find(f"{{{CBC}}}Percent"))
            lp = _dec(lpct)
            if lid not in cat_percents:
                add("BR-CO-04", "fatal",
                    f"Line VAT category '{lid}' does not appear in the document VAT breakdown", p)
            elif (lid, lp) not in cat_rates:
                # Rates compare NUMERICALLY ("25.0" == "25") and the PAIR must
                # match, because a document may hold category S at several
                # rates (the official Vat-category-S example uses 25 and 15).
                present = ", ".join(sorted(str(r) for r in cat_percents[lid]))
                add("BR-CO-04", "fatal",
                    f"Line VAT rate {lpct} for category {lid} does not match any "
                    f"breakdown group for that category (breakdown has: {present})", p)
            if lid == "S" and lpct in ("", "0", "0.0", "0.00"):
                add("BR-S-08", "fatal", "Line in category S must have a rate above 0", p)
        # BR-24: at least one line-level element
        if not _text(ln.find(f"{{{CBC}}}ID")):
            add("BR-21", "fatal", "Line identifier (BT-126) is missing", p)
        # BR-CO-10 line extent = qty x price (net of line allowance/charge)
        if qty is not None and price is not None and ext is not None:
            line_acs = ln.findall(f"{{{CAC}}}AllowanceCharge")
            line_allow = sum((_dec(_text(a.find(f"{{{CBC}}}Amount"))) or Decimal(0)
                              for a in line_acs
                              if _text(a.find(f"{{{CBC}}}ChargeIndicator")).lower() == "false"), Decimal(0))
            line_charge = sum((_dec(_text(a.find(f"{{{CBC}}}Amount"))) or Decimal(0)
                               for a in line_acs
                               if _text(a.find(f"{{{CBC}}}ChargeIndicator")).lower() == "true"), Decimal(0))
            # BR-CO-10: line net amount = (quantity x price) - line allowances + line charges.
            # NOTE: the price used is the gross item price, and line-level
            # AllowanceCharge elements adjust it. This is what the official
            # Peppol examples do, and omitting the charge term mis-flags them.
            if base_qty == 0:
                add("BR-CO-10", "fatal", "Price BaseQuantity must not be zero", p)
            else:
                unit_price = price / base_qty
                expect = (qty * unit_price - line_allow + line_charge).quantize(Decimal("0.01"))
                if abs(expect - ext) > currency_tolerance:
                    add("BR-CO-10", "fatal",
                        f"Line net amount {ext} does not equal "
                        f"(quantity x price/BaseQuantity) - allowances + charges = {expect}", p)

    # ---------- currency consistency ----------
    for tag in ("TaxAmount",):
        el = root.find(f"{{{CAC}}}TaxTotal/{{{CBC}}}{tag}")
        if el is not None and el.get("currencyID") and el.get("currencyID") != cur:
            add("BR-CO-15", "fatal",
                f"Tax total currency {el.get('currencyID')} differs from document currency {cur}")

    # ---------- Belgian: structured communication present when expected ----------
    # Not a Peppol rule, but a real-world requirement for BE B2B invoices.
    s_country = ""
    if sup is not None:
        s_country = _text(sup.find(f"{{{CAC}}}PostalAddress/{{{CAC}}}Country/{{{CBC}}}IdentificationCode"))
    if s_country.upper() == "BE":
        pm = root.find(f"{{{CAC}}}PaymentMeans")
        has_ogm = False
        if pm is not None:
            pid = _text(pm.find(f"{{{CBC}}}PaymentID"))
            if "+++" in pid or (pid.replace("/", "").isdigit() and len(pid.replace("/", "")) == 12):
                has_ogm = True
        if not has_ogm:
            add("BE-PAY-01", "warning",
                "Belgian supplier with no structured communication (OGM/+++) on the payment means; "
                "many Belgian buyers require one to match the payment")

    return out

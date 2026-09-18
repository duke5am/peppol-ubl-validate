# peppol-ubl-validate

Validate UBL invoices against the **official UBL 2.1 schemas** and the
**published Peppol BIS Billing 3.0 rules**. Free, offline, no dependencies
beyond `lxml`.

```bash
python3 validate.py invoice.xml
python3 validate.py fixtures/official/     # all 10 official examples pass
```

```
PASS  base-example.xml
   schema: valid UBL 2.1
PASS  vat-category-S.xml
   schema: valid UBL 2.1
...
10 file(s) passed both checks.
```

Exit codes: `0` clean · `1` fatal rule findings · `2` schema invalid.

## Why this exists

If you issue invoices from your own software in the EU, you have probably hit
this: your generated UBL looks correct, and an Access Point rejects it with a
message that does not tell you why.

Three things cause most of those rejections, and this tool checks all three.

**The totals disagree with each other.** Peppol requires the line sum, the
tax-exclusive amount, the VAT breakdown and the payable amount to be
arithmetically consistent in a specific way. The usual mistake is rounding tax
per line instead of per VAT category — the difference is one cent and the
invoice is invalid.

**One VAT category can appear at several rates.** A document can hold category
`S` at 21% and at 6%, with one breakdown group per (category, rate) pair, and
every line must match one of them. Keying your breakdown by category alone
cannot represent this, and documents that look fine fail.

**UBL is an ordered schema.** Elements must appear in the declared sequence, so
a document assembled in a merely logical order is schema-invalid even though
nothing is missing.

## What it checks

**Schema** — against the published OASIS UBL 2.1 XSDs, vendored in `schema/` so
validation works with no network access. This is the real schema, not a
re-implementation.

**Rules** — the `BR-*` families: mandatory business terms, the `BR-CO-*`
calculation rules, and the per-category VAT rules for `S`, `Z`, `E` and `AE`.
Findings are reported by rule identifier so you can look each one up in the
published rule list.

## What it does not check

The rule checker is an **independent implementation of the published rule list**,
not the official OpenPEPPOL Schematron. Those artefacts are distributed to
Peppol members and are not publicly downloadable, so no free tool can ship them.

It does not validate VAT numbers against VIES, does not check code lists against
the published UNTDID lists, and does not implement every country's specific
rules. A pass here means the document is schema-valid UBL and satisfies the
rules implemented — it is necessary, not sufficient. The authoritative test is
validation by a registered Peppol Access Point.

## The official examples are the test

`fixtures/official/` holds the 10 official Peppol BIS Billing 3 example
documents. They are asserted to be schema-valid *and* rule-clean. That second
assertion is the useful one: when it was first written it failed, and making it
pass found four real bugs in this code — including credit notes being serialized
like invoices (the UBL `CreditNote` schema has no `DueDate`) and
`Price/BaseQuantity` being ignored, so a price quoted per two units was read as a
price per unit.

## Generator, Belgian specifics, and fixtures

This repository is the validator only.

The full toolkit adds:

* a library and CLI that **generate** invoices and credit notes, and **refuse to
  write one that fails validation**;
* Belgian specifics handled properly — structured communication (OGM) with a
  mod-97 check that cannot produce an invalid number, VAT number normalisation
  that raises on a bad check digit, and Peppol endpoint identifiers with the
  right EAS scheme;
* a worked fixture corpus: 21% standard, OGM reference, intra-community
  zero-rated, exempt with reason, credit note, allowances and charges,
  multi-rate, and a negative correction line;
* 51 tests and a documented verification record.

→ More developer tooling like this: **[duke5am.gumroad.com](https://duke5am.gumroad.com)** <!-- GUMROAD-LINK -->

## Licence

MIT for this validator. The schemas in `schema/` are the OASIS UBL 2.1 schemas
and the examples in `fixtures/official/` are OpenPEPPOL's; both remain under
their own terms.

Not affiliated with OpenPEPPOL, OASIS or any Peppol Authority.

#!/usr/bin/env python3
"""peppol-validate: check a UBL invoice/credit note for Peppol BIS Billing 3.0.

Two independent checks:
  1. SCHEMA  - against the official OASIS UBL 2.1 XSDs (authoritative)
  2. RULES   - against a Python implementation of the published Peppol BIS
               Billing 3.0 rule list (NOT the official OpenPEPPOL Schematron)

Exit codes: 0 = schema valid AND no fatal rule findings, 1 = fatal findings,
            2 = schema invalid or unreadable.
"""
import argparse, glob, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from peppol import validate_xsd, check_rules  # noqa: E402

GREEN, RED, YELLOW, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    GREEN = RED = YELLOW = DIM = OFF = ""


def report(path, quiet=False):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print(f"{RED}cannot read{OFF} {path}: {exc}")
        return 2

    ok, errors = validate_xsd(data)
    findings = check_rules(data)
    fatals = [f for f in findings if f.severity == "fatal"]
    warns = [f for f in findings if f.severity == "warning"]

    name = os.path.basename(path)
    if ok and not fatals:
        status = f"{GREEN}PASS{OFF}"
    elif not ok:
        status = f"{RED}SCHEMA-INVALID{OFF}"
    else:
        status = f"{RED}RULE-FAIL{OFF}"

    print(f"{status}  {name}")
    if not ok:
        print(f"   {DIM}schema: not valid UBL 2.1{OFF}")
        for e in errors[:8]:
            print(f"     {RED}x{OFF} {e}")
        if len(errors) > 8:
            print(f"     {DIM}... and {len(errors) - 8} more{OFF}")
    else:
        print(f"   {DIM}schema: valid UBL 2.1{OFF}")

    if not quiet:
        for f in fatals:
            print(f"     {RED}x{OFF} {f}")
        for f in warns:
            print(f"     {YELLOW}!{OFF} {f}")
    elif fatals or warns:
        print(f"   {DIM}{len(fatals)} fatal, {len(warns)} warning{OFF}")

    if not ok:
        return 2
    return 1 if fatals else 0


def main():
    ap = argparse.ArgumentParser(
        prog="peppol-validate",
        description="Validate UBL invoices against the UBL 2.1 schemas and the "
                    "published Peppol BIS Billing 3.0 rules.",
        epilog="Exit codes: 0 clean, 1 fatal rule findings, 2 schema invalid/unreadable.",
    )
    ap.add_argument("paths", nargs="+", help="XML file(s) or glob(s)")
    ap.add_argument("-q", "--quiet", action="store_true", help="summary only")
    args = ap.parse_args()

    files = []
    for p in args.paths:
        if os.path.isdir(p):
            files.extend(sorted(glob.glob(os.path.join(p, "*.xml"))))
        else:
            files.extend(sorted(glob.glob(p)) or [p])
    if not files:
        print("no files matched", file=sys.stderr)
        return 2

    worst = 0
    for f in files:
        worst = max(worst, report(f, args.quiet))
    print()
    n = len(files)
    if worst == 0:
        print(f"{GREEN}{n} file(s) passed both checks.{OFF}")
    elif worst == 1:
        print(f"{YELLOW}At least one file has fatal rule findings.{OFF}")
    else:
        print(f"{RED}At least one file failed schema validation.{OFF}")
    print(f"{DIM}Note: rule checking is an independent implementation of the published "
          f"Peppol BIS Billing 3.0 rules, not the official OpenPEPPOL Schematron.{OFF}")
    return worst


if __name__ == "__main__":
    sys.exit(main())

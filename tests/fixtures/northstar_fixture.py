"""Synthetic Northstar 30-control regression fixture.

IMPORTANT — provenance and limits
----------------------------------
The original 30-control test policy and control matrix referenced by the
remediation mandate were NOT present in the repository (no NS- fixtures,
no Northstar files anywhere in the repo).  This fixture is therefore a
NEW, separately documented synthetic fixture created for this remediation.
It does NOT reproduce the original test and must never be described as
the original Northstar evaluation.

The fixture is authored so the deterministic pipeline (mocked Stage A
outputs -> strict validation -> deterministic Stage B adjudication)
reproduces the expected statuses below.  Stage A outputs are mocked
deterministically; no live model call is made in the regression suite.
Every quotation in the mocked payloads is a verbatim substring of the
policy pages below, so quotation verification can be exercised honestly.

Expected statuses are PROPOSED labels, not certified audit judgements.
Where the source does not support a definitive label, the fixture
prefers "Needs Review".

Policy: "Northstar" — a fictional company security policy with
operational records, deliberately containing partial coverage, stale
evidence, contradictions and policy-only operational claims.
"""

from __future__ import annotations

from evidence_model import PageText

DOC_NAME = "northstar-policy.pdf"

# ---------------------------------------------------------------------------
# Synthetic policy pages (verbatim source for every mocked quotation)
# ---------------------------------------------------------------------------

_POLICY_TEXT = {
    1: (
        "Northstar Security Policy - Access Control.\n"
        "Access reviews are performed periodically for all privileged accounts.\n"
        "Multi-factor authentication is required for administrators.\n"
        "All new joiners complete security awareness training within 30 days of starting."
    ),
    2: (
        "Operational records - Q3 2026.\n"
        "Training completion for Q3 2026 was 82% of staff.\n"
        "Backup restore test completed successfully for the production database on 2026-09-14.\n"
        "Vulnerability scan completed 2026-10-01; 3 high findings open.\n"
        "Patching is applied to all servers within 14 days of release.\n"
        "Patching completed for 14 of 20 servers within 14 days; 6 servers patched late.\n"
        "Two external services still use TLS 1.0."
    ),
    3: (
        "Audit logs are retained for 90 days.\n"
        "Encryption at rest is enabled for the customer database.\n"
        "Incident response plan is reviewed annually.\n"
        "Last review of the incident response plan was 2024-03-01.\n"
        "Third-party vendor assessments are completed before onboarding.\n"
        "Vendor assessments completed for 7 of 10 active vendors."
    ),
    4: (
        "Audit logs are retained for one year.\n"
        "Data classification labels are applied to all documents.\n"
        "Classification labels present on 60% of sampled documents.\n"
        "Change management approval is required for production changes.\n"
        "Change tickets show approval for 18 of 22 production changes in Q3.\n"
        "Remediation of high findings is required within 30 days of identification.\n"
        "Finding F-22, identified 2026-01-15, remains open as of 2026-11-01 with no approved exception.\n"
        "Data retention for customer records is 5 years."
    ),
    5: (
        "Customer records are deleted after 3 years.\n"
        "Security monitoring alerts are reviewed daily by the on-call engineer.\n"
        "Alert review logs show 5 of 7 days reviewed in the sampled week.\n"
        "Endpoint protection is installed on all company laptops.\n"
        "Endpoint protection installed on 88 of 100 laptops.\n"
        "Secure coding training is provided to all developers annually.\n"
        "Secure coding training completed by 9 of 12 developers.\n"
        "Access provisioning follows the joiner-mover-leaver process.\n"
        "Leaver access revoked within 24 hours for 15 of 18 leavers in Q3.\n"
        "Penetration testing is performed annually by an external firm.\n"
        "The most recent penetration test report is dated 2025-06-30."
    ),
    6: (
        "Database backups are performed daily.\n"
        "Network segmentation separates production from development.\n"
        "Segmentation verified for the production network; development network segmentation not yet assessed.\n"
        "Supplier security clauses are included in all new contracts.\n"
        "Security clauses present in 11 of 14 new contracts signed in Q3.\n"
        "Business continuity plan is tested annually.\n"
        "The business continuity plan was last tested in 2025-11-20; the next test date is not recorded.\n"
        "Guest Wi-Fi access requires a sponsor and expires after 24 hours.\n"
        "All external services use TLS 1.2 or higher.\n"
        "Asset inventory is updated monthly.\n"
        "Asset inventory updated for 9 of 12 months in 2026.\n"
        "Risk assessments are performed annually.\n"
        "The risk assessment was completed 2025-09-01; the 2026 assessment is in progress.\n"
        "Data subject access requests are answered within 30 days.\n"
        "Three requests answered within 30 days; one request took 41 days with no documented reason."
    ),
}

POLICY_PAGES = [
    PageText(filename=DOC_NAME, page=page, text=text, document_id=DOC_NAME)
    for page, text in sorted(_POLICY_TEXT.items())
]

# ---------------------------------------------------------------------------
# Controls: (control_id, name, requirement)
# ---------------------------------------------------------------------------

CONTROLS = [
    ("NS-01", "Access review policy", "An access review policy defines scope and frequency for privileged accounts"),
    ("NS-02", "Multi-factor authentication", "Multi-factor authentication is required for all users"),
    ("NS-03", "Security awareness training", "Security awareness training is completed by all staff annually"),
    ("NS-04", "Backup restore testing", "Backup restore tests cover all production databases"),
    ("NS-05", "Vulnerability tracking", "Vulnerability findings are tracked to closure"),
    ("NS-06", "Patch management", "Security patches are applied to all servers within 14 days of release"),
    ("NS-07", "Audit log retention", "Audit log retention period is defined and consistently applied"),
    ("NS-08", "Encryption at rest", "Encryption at rest is enabled for all databases containing customer data"),
    ("NS-09", "Incident response review", "Incident response plan is reviewed annually"),
    ("NS-10", "Vendor assessment", "Third-party vendors are assessed before onboarding"),
    ("NS-11", "Data classification", "Data classification labels are applied to all documents"),
    ("NS-12", "Change approval", "Production changes require approval before deployment"),
    ("NS-13", "Finding remediation", "High findings are remediated within 30 days of identification"),
    ("NS-14", "Physical access logging", "Physical access to the server room is logged and reviewed monthly"),
    ("NS-15", "Customer record retention", "Customer record retention is defined and consistently applied"),
    ("NS-16", "Alert review", "Security monitoring alerts are reviewed daily"),
    ("NS-17", "Endpoint protection", "Endpoint protection is installed on all company devices"),
    ("NS-18", "Secure coding training", "Developers complete secure coding training annually"),
    ("NS-19", "Leaver access revocation", "Leaver access is revoked within 24 hours"),
    ("NS-20", "Penetration testing", "Penetration testing is performed annually by an external firm"),
    ("NS-21", "Backup restore testing (quarterly)", "Database backups must be restore-tested quarterly"),
    ("NS-22", "Network segmentation", "Production and development networks are segmented"),
    ("NS-23", "Supplier security clauses", "Supplier contracts include security clauses"),
    ("NS-24", "Business continuity testing", "Business continuity plan is tested annually"),
    ("NS-25", "Data centre biometric access", "Biometric authentication is required for data centre entry"),
    ("NS-26", "Encryption in transit", "Encryption in transit is required for all external services"),
    ("NS-27", "Asset inventory", "Asset inventory is updated monthly"),
    ("NS-28", "Risk assessment", "Risk assessments are performed annually"),
    ("NS-29", "Data subject access requests", "Data subject access requests are answered within 30 days"),
    ("NS-30", "Privileged access review records", "Privileged access reviews must be evidenced by signed review records and reviewed quarterly"),
]

EXPECTED = {
    "NS-01": "Needs Review",
    "NS-02": "Partially Compliant",
    "NS-03": "Partially Compliant",
    "NS-04": "Needs Review",
    "NS-05": "Needs Review",
    "NS-06": "Partially Compliant",
    "NS-07": "Conflicting Evidence",
    "NS-08": "Partially Compliant",
    "NS-09": "Partially Compliant",
    "NS-10": "Partially Compliant",
    "NS-11": "Partially Compliant",
    "NS-12": "Partially Compliant",
    "NS-13": "Non-Compliant",
    "NS-14": "Not Found",
    "NS-15": "Conflicting Evidence",
    "NS-16": "Partially Compliant",
    "NS-17": "Partially Compliant",
    "NS-18": "Partially Compliant",
    "NS-19": "Partially Compliant",
    "NS-20": "Needs Review",
    "NS-21": "Not Found",
    "NS-22": "Partially Compliant",
    "NS-23": "Partially Compliant",
    "NS-24": "Needs Review",
    "NS-25": "Not Found",
    "NS-26": "Conflicting Evidence",
    "NS-27": "Partially Compliant",
    "NS-28": "Needs Review",
    "NS-29": "Needs Review",
    "NS-30": "Not Found",
}

# ---------------------------------------------------------------------------
# Mocked Stage A payloads (one per control).  Every "quote" is verbatim
# from POLICY_PAGES above.  "status" is the model's provisional label;
# Stage B adjudication may adjust it — the regression asserts the final
# adjudicated status equals EXPECTED.
# ---------------------------------------------------------------------------


def _ev(quote, page, evidence_type):
    return {
        "quote": quote,
        "source_document": DOC_NAME,
        "page": page,
        "evidence_type": evidence_type,
    }


def _payload(control_id, status, coverage, evidence, reasoning, **extra):
    base = {
        "control_id": control_id,
        "status": status,
        "requirement_coverage": coverage,
        "evidence": evidence,
        "covered_scope": [],
        "uncovered_scope": [],
        "missing_elements": [],
        "conflicts": [],
        "exceptions": [],
        "reasoning": reasoning,
        "review_required": status in ("Needs Review", "Conflicting Evidence", "Non-Compliant"),
        "stale_is_violation": False,
    }
    base.update(extra)
    return base


MOCK_PAYLOADS = {
    "NS-01": _payload(
        "NS-01", "Needs Review", "Unknown",
        [_ev("Access reviews are performed periodically for all privileged accounts.", 1, "Policy")],
        "The policy states reviews are performed 'periodically' but gives no frequency or scope, so no definitive label is possible.",
        missing_elements=["Review frequency is not stated.", "Review scope is not defined."],
    ),
    "NS-02": _payload(
        "NS-02", "Partially Compliant", "Partial",
        [_ev("Multi-factor authentication is required for administrators.", 1, "Policy")],
        "MFA is required for administrators only; no evidence covers non-admin users.",
        covered_scope=["Administrators"],
        uncovered_scope=["Non-admin users"],
        missing_elements=["MFA evidence for non-admin users."],
    ),
    "NS-03": _payload(
        "NS-03", "Partially Compliant", "Partial",
        [
            _ev("All new joiners complete security awareness training within 30 days of starting.", 1, "Policy"),
            _ev("Training completion for Q3 2026 was 82% of staff.", 2, "Operational Record"),
        ],
        "Training completion is 82% of staff, below full coverage.",
        covered_scope=["82% of staff"],
        uncovered_scope=["18% of staff without completed training"],
        missing_elements=["Training records for the remaining 18% of staff."],
    ),
    "NS-04": _payload(
        "NS-04", "Needs Review", "Unknown",
        [_ev("Backup restore test completed successfully for the production database on 2026-09-14.", 2, "Operational Record")],
        "One database was restore-tested; whether other production databases were tested is not recorded.",
        missing_elements=["Restore-test evidence for production databases other than the one named."],
    ),
    "NS-05": _payload(
        "NS-05", "Needs Review", "Unknown",
        [_ev("Vulnerability scan completed 2026-10-01; 3 high findings open.", 2, "Operational Record")],
        "Three high findings are open but no due dates or closure tracking is shown, so closure cannot be assessed.",
        missing_elements=["Due dates and closure status for the 3 open high findings."],
    ),
    "NS-06": _payload(
        "NS-06", "Partially Compliant", "Partial",
        [
            _ev("Patching is applied to all servers within 14 days of release.", 2, "Policy"),
            _ev("Patching completed for 14 of 20 servers within 14 days; 6 servers patched late.", 2, "Operational Record"),
        ],
        "14 of 20 servers were patched within 14 days; 6 were patched late.",
        covered_scope=["14 of 20 servers patched on time"],
        uncovered_scope=["6 servers patched late"],
        missing_elements=["Evidence that the 6 late servers were remediated."],
    ),
    "NS-07": _payload(
        "NS-07", "Conflicting Evidence", "Unknown",
        [
            _ev("Audit logs are retained for 90 days.", 3, "Policy"),
            _ev("Audit logs are retained for one year.", 4, "Policy"),
        ],
        "Two pages state different retention periods for the same logs.",
        conflicts=["Page 3 states audit logs are retained for 90 days; page 4 states they are retained for one year."],
    ),
    "NS-08": _payload(
        "NS-08", "Partially Compliant", "Partial",
        [_ev("Encryption at rest is enabled for the customer database.", 3, "Policy")],
        "Encryption at rest is confirmed only for the customer database; other databases are not mentioned.",
        covered_scope=["Customer database"],
        uncovered_scope=["Other databases containing customer data"],
        missing_elements=["Encryption evidence for databases other than the customer database."],
    ),
    "NS-09": _payload(
        "NS-09", "Partially Compliant", "Partial",
        [
            _ev("Incident response plan is reviewed annually.", 3, "Policy"),
            _ev("Last review of the incident response plan was 2024-03-01.", 3, "Operational Record"),
        ],
        "The plan is reviewed annually in policy, but the last recorded review was 2024-03-01, which is overdue against the annual interval.",
        missing_elements=["A current annual review of the incident response plan."],
    ),
    "NS-10": _payload(
        "NS-10", "Partially Compliant", "Partial",
        [
            _ev("Third-party vendor assessments are completed before onboarding.", 3, "Policy"),
            _ev("Vendor assessments completed for 7 of 10 active vendors.", 3, "Operational Record"),
        ],
        "Assessments are recorded for 7 of 10 active vendors.",
        covered_scope=["7 of 10 active vendors"],
        uncovered_scope=["3 active vendors without recorded assessments"],
        missing_elements=["Assessments for the remaining 3 active vendors."],
    ),
    "NS-11": _payload(
        "NS-11", "Partially Compliant", "Partial",
        [
            _ev("Data classification labels are applied to all documents.", 4, "Policy"),
            _ev("Classification labels present on 60% of sampled documents.", 4, "Operational Record"),
        ],
        "Labels are present on 60% of sampled documents.",
        covered_scope=["60% of sampled documents"],
        uncovered_scope=["40% of sampled documents without labels"],
        missing_elements=["Labels on the remaining 40% of sampled documents."],
    ),
    "NS-12": _payload(
        "NS-12", "Partially Compliant", "Partial",
        [
            _ev("Change management approval is required for production changes.", 4, "Policy"),
            _ev("Change tickets show approval for 18 of 22 production changes in Q3.", 4, "Operational Record"),
        ],
        "Approval is recorded for 18 of 22 production changes in Q3.",
        covered_scope=["18 of 22 production changes"],
        uncovered_scope=["4 production changes without recorded approval"],
        missing_elements=["Approval records for the 4 changes without approval."],
    ),
    "NS-13": _payload(
        "NS-13", "Non-Compliant", "Partial",
        [
            _ev("Remediation of high findings is required within 30 days of identification.", 4, "Policy"),
            _ev("Finding F-22, identified 2026-01-15, remains open as of 2026-11-01 with no approved exception.", 4, "Operational Record"),
        ],
        "Finding F-22 was identified 2026-01-15 and remains open as of 2026-11-01, well beyond the 30-day remediation requirement, with no approved exception.",
        stale_is_violation=True,
        missing_elements=["Evidence that finding F-22 was remediated or is covered by an approved exception."],
    ),
    "NS-14": _payload(
        "NS-14", "Not Found", "None",
        [],
        "No passage addresses physical access logging for the server room.",
        missing_elements=["Server-room access logs and evidence of monthly review."],
    ),
    "NS-15": _payload(
        "NS-15", "Conflicting Evidence", "Unknown",
        [
            _ev("Data retention for customer records is 5 years.", 4, "Policy"),
            _ev("Customer records are deleted after 3 years.", 5, "Policy"),
        ],
        "One passage retains customer records for 5 years; another deletes them after 3 years.",
        conflicts=["Page 4 states customer records are retained for 5 years; page 5 states they are deleted after 3 years."],
    ),
    "NS-16": _payload(
        "NS-16", "Partially Compliant", "Partial",
        [
            _ev("Security monitoring alerts are reviewed daily by the on-call engineer.", 5, "Policy"),
            _ev("Alert review logs show 5 of 7 days reviewed in the sampled week.", 5, "Operational Record"),
        ],
        "Alert reviews are recorded for 5 of 7 days in the sampled week.",
        covered_scope=["5 of 7 days"],
        uncovered_scope=["2 days without recorded review"],
        missing_elements=["Review records for the 2 unreviewed days."],
    ),
    "NS-17": _payload(
        "NS-17", "Partially Compliant", "Partial",
        [
            _ev("Endpoint protection is installed on all company laptops.", 5, "Policy"),
            _ev("Endpoint protection installed on 88 of 100 laptops.", 5, "Operational Record"),
        ],
        "Endpoint protection is installed on 88 of 100 laptops.",
        covered_scope=["88 of 100 laptops"],
        uncovered_scope=["12 laptops without endpoint protection"],
        missing_elements=["Endpoint protection on the remaining 12 laptops."],
    ),
    "NS-18": _payload(
        "NS-18", "Partially Compliant", "Partial",
        [
            _ev("Secure coding training is provided to all developers annually.", 5, "Policy"),
            _ev("Secure coding training completed by 9 of 12 developers.", 5, "Operational Record"),
        ],
        "Secure coding training was completed by 9 of 12 developers.",
        covered_scope=["9 of 12 developers"],
        uncovered_scope=["3 developers without completed training"],
        missing_elements=["Training records for the remaining 3 developers."],
    ),
    "NS-19": _payload(
        "NS-19", "Partially Compliant", "Partial",
        [
            _ev("Access provisioning follows the joiner-mover-leaver process.", 5, "Policy"),
            _ev("Leaver access revoked within 24 hours for 15 of 18 leavers in Q3.", 5, "Operational Record"),
        ],
        "Leaver access was revoked within 24 hours for 15 of 18 leavers in Q3.",
        covered_scope=["15 of 18 leavers"],
        uncovered_scope=["3 leavers without timely revocation evidence"],
        missing_elements=["Revocation evidence for the remaining 3 leavers."],
    ),
    "NS-20": _payload(
        "NS-20", "Needs Review", "Unknown",
        [
            _ev("Penetration testing is performed annually by an external firm.", 5, "Policy"),
            _ev("The most recent penetration test report is dated 2025-06-30.", 5, "Third-Party Assurance"),
        ],
        "The most recent penetration test report is dated 2025-06-30; whether the annual cadence has been met depends on the exact test schedule, which is not stated.",
        missing_elements=["The current annual penetration test report or the scheduled test date."],
    ),
    "NS-21": _payload(
        "NS-21", "Not Found", "None",
        [_ev("Database backups are performed daily.", 6, "Policy")],
        "Only a policy statement that backups are performed daily was found; no restore-test record exists, and policy text alone is not proof of operation.",
        missing_elements=["Restore-test records for production databases."],
    ),
    "NS-22": _payload(
        "NS-22", "Partially Compliant", "Partial",
        [
            _ev("Network segmentation separates production from development.", 6, "Policy"),
            _ev("Segmentation verified for the production network; development network segmentation not yet assessed.", 6, "Operational Record"),
        ],
        "Segmentation is verified for production only; development segmentation has not been assessed.",
        covered_scope=["Production network"],
        uncovered_scope=["Development network segmentation not assessed"],
        missing_elements=["Segmentation assessment for the development network."],
    ),
    "NS-23": _payload(
        "NS-23", "Partially Compliant", "Partial",
        [
            _ev("Supplier security clauses are included in all new contracts.", 6, "Policy"),
            _ev("Security clauses present in 11 of 14 new contracts signed in Q3.", 6, "Operational Record"),
        ],
        "Security clauses are present in 11 of 14 new contracts signed in Q3.",
        covered_scope=["11 of 14 new contracts"],
        uncovered_scope=["3 new contracts without security clauses"],
        missing_elements=["Security clauses in the remaining 3 new contracts."],
    ),
    "NS-24": _payload(
        "NS-24", "Needs Review", "Unknown",
        [
            _ev("Business continuity plan is tested annually.", 6, "Policy"),
            _ev("The business continuity plan was last tested in 2025-11-20; the next test date is not recorded.", 6, "Operational Record"),
        ],
        "The plan was last tested 2025-11-20 and the next test date is not recorded, so currency against the annual interval cannot be confirmed.",
        missing_elements=["The next scheduled business continuity test date or a current test record."],
    ),
    "NS-25": _payload(
        "NS-25", "Not Found", "None",
        [],
        "No passage addresses biometric authentication for data centre entry.",
        missing_elements=["Biometric authentication evidence for data centre entry."],
    ),
    "NS-26": _payload(
        "NS-26", "Conflicting Evidence", "Unknown",
        [
            _ev("All external services use TLS 1.2 or higher.", 6, "Policy"),
            _ev("Two external services still use TLS 1.0.", 2, "Operational Record"),
        ],
        "Policy requires TLS 1.2 or higher for all external services, but records show two services still use TLS 1.0.",
        conflicts=["Policy requires TLS 1.2 or higher for all external services; records show two external services still use TLS 1.0."],
    ),
    "NS-27": _payload(
        "NS-27", "Partially Compliant", "Partial",
        [
            _ev("Asset inventory is updated monthly.", 6, "Policy"),
            _ev("Asset inventory updated for 9 of 12 months in 2026.", 6, "Operational Record"),
        ],
        "The asset inventory was updated in 9 of 12 months in 2026.",
        covered_scope=["9 of 12 months"],
        uncovered_scope=["3 months without an inventory update"],
        missing_elements=["Inventory updates for the 3 missing months."],
    ),
    "NS-28": _payload(
        "NS-28", "Needs Review", "Unknown",
        [
            _ev("Risk assessments are performed annually.", 6, "Policy"),
            _ev("The risk assessment was completed 2025-09-01; the 2026 assessment is in progress.", 6, "Operational Record"),
        ],
        "The 2025 assessment is complete and the 2026 assessment is in progress; its outcome and completion date are unknown.",
        missing_elements=["The completed 2026 risk assessment."],
    ),
    "NS-29": _payload(
        "NS-29", "Needs Review", "Unknown",
        [
            _ev("Data subject access requests are answered within 30 days.", 6, "Policy"),
            _ev("Three requests answered within 30 days; one request took 41 days with no documented reason.", 6, "Operational Record"),
        ],
        "One request took 41 days with no documented reason; whether this is an isolated case or a systemic failure is not established.",
        missing_elements=["The reason for the 41-day request and evidence of corrective action."],
    ),
    "NS-30": _payload(
        "NS-30", "Not Found", "None",
        [_ev("Access reviews are performed periodically for all privileged accounts.", 1, "Policy")],
        "Only a policy statement that reviews are performed was found; no signed review records exist, and policy text alone is not proof of operation.",
        missing_elements=["Signed privileged-access review records."],
    ),
}

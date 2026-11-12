"""Shared pytest fixtures for all tests (e.g. paths to tests/fixtures, a fake Gemini).

Tests must never call the real Gemini API and must not depend on ai_tool/data/,
which is not in Git. Use the small example files in tests/fixtures/ instead.
"""
import re

import pytest

# Jira (Xray) Test issues of user story 57 (proposals overview). A test whose name starts
# with test_tc_57_<nr>_ gets the key as "test_key" property in the JUnit report, so the
# results can be imported in Xray:  pytest --junitxml=test-results/pytest-junit.xml
XRAY_KEYS = {
    '01': 'IT2627T06-92',   # Ongeldige gegevens worden overgeslagen
    '02': 'IT2627T06-128',  # Overzicht toont per klant de laatste versie
    '03': 'IT2627T06-129',  # Nieuwste upload bovenaan
    '04': 'IT2627T06-130',  # Rij toont klant, versie, uploadtijd en status
    '05': 'IT2627T06-131',  # Statussen staan in het Nederlands
    '06': 'IT2627T06-132',  # "Openen" gaat naar het package van de klant
    '07': 'IT2627T06-133',  # Statuswijziging zichtbaar binnen 10 seconden
    '08': 'IT2627T06-134',  # Nieuwe proposal verschijnt na een upload
    '09': 'IT2627T06-135',  # Lege lijst als er nog geen proposals zijn
    '10': 'IT2627T06-136',  # Laden en foutmelding met "Opnieuw proberen"
}
_TC_57 = re.compile(r'^test_tc_57_(\d\d)_')


@pytest.fixture(autouse=True)
def _xray_test_key(request, record_property):
    match = _TC_57.match(request.node.originalname or request.node.name)
    if match and match.group(1) in XRAY_KEYS:
        record_property('test_key', XRAY_KEYS[match.group(1)])

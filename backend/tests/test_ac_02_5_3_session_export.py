"""spec 02-core-flows.md §5.3 / §8 items 3-4: GET /api/sessions/{id}/export.json
and .../export.csv, owner-only."""

from __future__ import annotations

from fipm.exporters import CSV_HEADER, SESSION_CSV_HEADER


def _make_session_with_fips(client_factory, owner_email):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={
            "email": owner_email,
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = owner.post(
        "/api/sessions",
        json={
            "title": "export session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    participant = client_factory()
    answers_a = [
        {
            "questionId": "F1-metadata",
            "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
        }
    ]
    fip_a = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "community": {"name": "Group A"},
            "answers": answers_a,
        },
    ).json()

    participant2 = client_factory()
    answers_b = [
        {
            "questionId": "F1-metadata",
            "declarations": [{"ferFreeText": "Our own registry", "status": "planned"}],
        }
    ]
    fip_b = participant2.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "community": {"name": "Group B"},
            "answers": answers_b,
        },
    ).json()

    return owner, session, [fip_a, fip_b]


def test_session_export_json_owner_ok_other_user_404_anon_401(client_factory):
    owner, session, fips = _make_session_with_fips(client_factory, "sessexp-owner@example.com")

    r = owner.get(f"/api/sessions/{session['id']}/export.json")
    assert r.status_code == 200
    doc = r.json()
    assert doc["exportVersion"] == 1
    assert doc["session"]["id"] == session["id"]
    assert doc["session"]["joinCode"] == session["joinCode"]
    assert doc["session"]["facilitatorName"] == "F"
    assert len(doc["fips"]) == 2
    # ordered by createdAt
    assert [f["fip"]["id"] for f in doc["fips"]] == [fips[0]["id"], fips[1]["id"]]
    for entry in doc["fips"]:
        # spec 07-mail-and-migration.md §6: exportVersion 2 for each FIP's
        # own document (the session wrapper's own exportVersion, above,
        # stays 1 -- unaffected by that spec).
        assert entry["exportVersion"] == 2
        assert entry["questionnaireRef"]["id"] == "test-km"
        assert len(entry["answers"]) == 2  # test-km fixture has 2 questions

    other_user = client_factory()
    other_user.post(
        "/api/auth/register",
        json={
            "email": "sessexp-other@example.com",
            "password": "correcthorsebattery",
            "displayName": "O",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert other_user.get(f"/api/sessions/{session['id']}/export.json").status_code == 404

    anon = client_factory()
    assert anon.get(f"/api/sessions/{session['id']}/export.json").status_code == 401


def test_session_export_csv_header_and_rows(client_factory):
    owner, session, fips = _make_session_with_fips(client_factory, "sessexp2-owner@example.com")

    r = owner.get(f"/api/sessions/{session['id']}/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")

    raw = r.content.decode("utf-8-sig")
    lines = raw.split("\r\n")
    header = lines[0].split(",")
    assert header == SESSION_CSV_HEADER
    # spec 08-workshop-picklists.md §3.3: `area` is the third prefix column.
    assert header[:3] == ["session_id", "fip_title", "area"]
    assert header[3:] == CSV_HEADER

    data_lines = [line for line in lines[1:] if line]
    # 2 FIPs x 2 questions (F1 answered with 1 declaration, F2 unanswered) = 4 rows.
    assert len(data_lines) == 4
    assert all(line.startswith(session["id"] + ",") for line in data_lines)
    titles = {line.split(",")[1] for line in data_lines}
    assert titles == {"Group A", "Group B"}
    # This session has a single questionnaireRef, so `area` is empty on
    # every row (non-null only for a FIP in a multi-ref session).
    areas = {line.split(",")[2] for line in data_lines}
    assert areas == {""}

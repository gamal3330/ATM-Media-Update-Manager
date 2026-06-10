import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from journal_reader import decode_journal_bytes, mask_card, parse_grg_journal_text, parse_ncr_journal_text


SAMPLE_EJ = """2026-06-09 17:41:17.637 TRANSACTION REQUEST ADBA  AC
2026-06-09 17:41:21.407 TRANSACTION SERIAL NUMBER:0058
2026-06-09 17:41:22.812 DISPENSE COMMAND FROM HOST:
[Type (A)], REQUESTED: 19
[Type (B)], REQUESTED: 21
2026-06-09 17:41:22.914 DISPENSE COMMAND TO CASSETTE:
[Type (A)][CAS 00001] REQUESTED: 19
[Type (B)][CAS 00002] REQUESTED: 21
2026-06-09 17:41:38.184 DISPENSE SUCCESS
2026-06-09 17:41:39.312 [CAS 00001] OUT: 19, REJECT: 00, DENO: 1000
2026-06-09 17:41:39.343 [CAS 00002] OUT: 21, REJECT: 00, DENO: 1000
2026-06-09 17:41:43.754 CARD TAKEN
2026-06-09 17:41:47.013 PRESENT SUCCESS.
2026-06-09 17:41:52.030 TAKE CASH TIMEOUT AND CONTINUE WAITTING.
2026-06-09 17:41:57.872 DELIVER MONEY...MONEY TAKEN=======
2026-06-09 17:42:00.099 TRANSACTION RECEIPT DATA
Transaction Type  : WID
DATE              : 08/06/2026 17:41:40
ATM               : 41
WORDING           : Qutaibi Shahn
CURRENCY          : YER
AMOUNT            : 40000
RRN               : 615914041698
STAN              : 041698
AUTH CODE         : 337309
CARD              : 9967009973421749
RESPONSE          : ERROR.ISSUER
2026-06-09 17:42:02.375 <---- TRANSACTION END
"""


SAMPLE_NCR_EJ = """     *0051*1*H*1,M-05,R-3111
*189*06/07/2026*19:50*
EJ LOG COPIED OK

AUTO INIT COPY DRIVE NOT CONFIGURED

DB4DFD01
 19:50:23 OPCODE = ADB   AD
 19:50:24 GENAC 1 : ARQC
 19:50:27 GENAC 2 : TC
 19:50:41 NOTES STACKED
 19:50:44 CARD TAKEN
===================================
Transaction Type  : WID
DATE              : 07/06/2026 19:50:04
ATM               : 12
WORDING           : QutaibiYAFE01
CURRENCY          : YER
AMOUNT            : 10000
RRN               : 615816007649
STAN              : 007649
AUTH CODE         : 211473
CARD              : 5312210107553478
RESPONSE          : ERROR.ISSUER
CASSETE 1       :
CASSETE 2       :
CASSETE 3       :
CASSETE 4       :
===================================
 19:50:46 NOTES PRESENTED 5,5,0,0
 19:50:46 NOTES TAKEN

CASH TOTAL       TYPE1 TYPE2 TYPE3 TYPE4
DENOMINATION         5    10    20    50
DISPENSED        01376 01377 00129 00000
REJECTED         00004 00003 00003 00003
REMAINING        01124 01123 00171 00050

     *0052*1*H*1,M-05,R-3111
     *0052*1*H*1,M-05,R-3111
 19:50:54 TRANSACTION END
"""


def by_type(events, event_type):
    return [event for event in events if event.event_type == event_type]


def test_mask_card_never_keeps_full_pan():
    assert mask_card("9967009973421749") == "996700******1749"
    assert mask_card("12345") is None


def test_parse_grg_journal_transaction_summary():
    events = parse_grg_journal_text(SAMPLE_EJ, file_path=r"D:\Log\EJ260609.log")

    assert by_type(events, "TRANSACTION_START")
    assert by_type(events, "TRANSACTION_SERIAL_NUMBER")[0].transaction_serial == "0058"
    assert by_type(events, "DISPENSE_SUCCESS")[0].occurred_at == "2026-06-09T17:41:38.184"
    assert by_type(events, "TAKE_CASH_TIMEOUT")[0].severity == "warning"

    cassette_events = by_type(events, "CASSETTE_OUT")
    assert len(cassette_events) == 2
    assert cassette_events[0].details == {"cassette_no": 1, "out": 19, "reject": 0, "denomination": 1000}
    assert cassette_events[1].details == {"cassette_no": 2, "out": 21, "reject": 0, "denomination": 1000}

    end = by_type(events, "TRANSACTION_END")[0]
    assert end.occurred_at == "2026-06-09T17:42:02.375"
    assert end.severity == "warning"
    assert end.transaction_type == "WID"
    assert end.amount == 40000
    assert end.currency == "YER"
    assert end.rrn == "615914041698"
    assert end.stan == "041698"
    assert end.auth_code == "337309"
    assert end.card_masked == "996700******1749"
    assert end.receipt_date == "08/06/2026 17:41:40"
    assert end.details["completed"] is True
    assert end.details["withdrawal"] is True
    assert end.details["take_cash_timeout"] is True
    assert end.cassette_outputs == [
        {"cassette_no": 1, "out": 19, "reject": 0, "denomination": 1000},
        {"cassette_no": 2, "out": 21, "reject": 0, "denomination": 1000},
    ]


def test_decode_utf16le_journal_without_bom():
    decoded = decode_journal_bytes(SAMPLE_EJ.encode("utf-16-le"))

    events = parse_grg_journal_text(decoded, file_path=r"D:\Log\EJ260610.log")

    assert by_type(events, "TRANSACTION_START")
    assert by_type(events, "TRANSACTION_END")[0].card_masked == "996700******1749"


def test_parse_ncr_journal_transaction_summary():
    events = parse_ncr_journal_text(
        SAMPLE_NCR_EJ,
        file_path=r"C:\Program Files (x86)\NCR APTRA\Advance NDC\Data\EJDATA.LOG",
    )

    start = by_type(events, "TRANSACTION_START")[0]
    assert start.source == "ncr_ej"
    assert start.occurred_at == "2026-06-07T19:50:23"

    assert by_type(events, "DISPENSE_SUCCESS")[0].message == "NOTES STACKED"
    presented = by_type(events, "PRESENT_SUCCESS")[0]
    assert presented.details == {"notes_presented": [5, 5, 0, 0]}
    assert by_type(events, "MONEY_TAKEN")[0].message == "NOTES TAKEN"

    end = by_type(events, "TRANSACTION_END")[0]
    assert end.source == "ncr_ej"
    assert end.occurred_at == "2026-06-07T19:50:54"
    assert end.transaction_type == "WID"
    assert end.amount == 10000
    assert end.currency == "YER"
    assert end.rrn == "615816007649"
    assert end.stan == "007649"
    assert end.auth_code == "211473"
    assert end.card_masked == "531221******3478"
    assert end.receipt_date == "07/06/2026 19:50:04"
    assert end.details["completed"] is True
    assert end.details["withdrawal"] is True
    assert end.details["notes_presented"] == [5, 5, 0, 0]

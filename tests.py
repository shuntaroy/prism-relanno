import pytest

from entity_types import Document
import visualise_time as vt

DOC = Document("data/sample001-r.ann")
vt.relate_dct(DOC)
vt.normalise_all_timex(DOC, "2014-03-20")
TCLIST = vt.make_time_containers([e for e in DOC.entities if e.tag == "TIMEX3"])


def test_parse_duration_value():
    assert vt.parse_duration_value("PT10M", "2014-03-20") == "2014-03-20T00:10:00"
    assert vt.parse_duration_value("P1Y", "2014-03-20") == "2015-03-20T00:00:00"
    assert vt.parse_duration_value("P6M", "2014-03-20") == "2014-09-20T00:00:00"
    assert (
        vt.parse_duration_value("P6M", "2014-10-20") == "2015-04-20T00:00:00"
    ), "月の足算で年に繰り越ししていない"
    assert (
        vt.parse_duration_value("P6M", "2014-03-20", neg=True) == "2013-09-20T00:00:00"
    ), "月の引き算で年を繰り下げしていない"
    assert vt.parse_duration_value("P1W", "2014-03-20") == "2014-03-27T00:00:00"
    assert vt.parse_duration_value("P5D", "2014-03-20") == "2014-03-25T00:00:00"
    assert (
        vt.parse_duration_value("PXX", "2014-03-20") == "2014-03-20T00:00:00"
    ), "should be no change if an invalid notation given"


# def test_tc_compare():
#     pass

"""The left-hand list: real DMS documents, read with System A's own read-only client."""
import pytest
from doubles import FakeReader, FakeSystemA

from webapp.catalog import Catalog, CatalogError, Doc


def _paper(doc_id, *, title=None, file_name=None, page_count=1, mime="application/pdf"):
    from system_a.adapters.paperless.reader import _doc
    return _doc({"id": doc_id, "created": "2026-10-01T00:00:00Z", "tags": [{"id": 7}], "mime_type": mime,
                 "title": f"SYNTHETIC INVOICE {doc_id}" if title is None else title,
                 "original_file_name": f"DMS-{doc_id}.pdf" if file_name is None else file_name,
                 "page_count": page_count})


@pytest.fixture(autouse=True)
def _with_system_a(harness):
    """Every test here builds DMS documents with System A's own parser, so the harness is always needed."""
    return harness


def make(tag="invoice", limit=50, **reader_kw):
    sa = FakeSystemA({})
    sa.reader = FakeReader(**reader_kw)                          # before the Catalog takes it
    return Catalog(sa, tag=tag, limit=limit), sa


def test_the_list_is_the_dms_list_filtered_by_tag():
    cat, sa = make()
    cat.refresh()
    assert cat.kind == "paperless" and cat.base_url == "http://dms.test"
    assert sa.reader.calls[0] == ("tags", ("invoice",)) and sa.reader.calls[1] == ("list", (7,), 50)
    assert cat.tag_ids == [7]
    assert [d.id for d in cat.docs] == [101, 102, 103]
    assert cat.dms_total == 3


def test_a_document_is_described_by_what_the_dms_knows():
    cat = make()[0]
    cat.refresh()
    d = cat.get(102)
    assert isinstance(d, Doc)
    assert (d.title, d.created, d.correspondent) == ("SYNTHETIC INVOICE 102", "2026-10-01", "SYNTHETIC SUPPLIER")
    assert (d.mime, d.file_class) == ("application/pdf", "pdf")
    assert d.pages_total == 1 and d.page_numbers == [1]
    assert d.dms_url == "http://dms.test/documents/102/" == cat.viewer_url(102)


def test_a_scan_gets_no_page_numbers_until_its_file_has_been_read():
    cat, sa = make(docs=[*[_paper(201, page_count=None)], _paper(202, page_count=3)])
    cat.refresh()
    assert cat.get(201).page_numbers == [] and cat.get(201).pages_total is None
    assert cat.get(202).page_numbers == [1, 2, 3]
    assert cat.stats()["pages"] == 3                             # only what is actually known


def test_ensure_asks_system_a_for_the_page_count_of_a_document():
    cat, sa = make(docs=[_paper(201, page_count=None)])
    cat.refresh()
    sa.pages = 4
    d = cat.ensure(201)
    assert (d.pages_total, d.page_numbers) == (4, [1, 2, 3, 4])
    assert cat.get(201).pages_total == 4                         # known from then on, without asking again
    sa.pages = 99
    assert cat.ensure(201).pages_total == 4


def test_show_page_widens_the_list_when_a_deeper_page_is_requested():
    cat = make(docs=[_paper(201, page_count=2)])[0]
    cat.refresh()
    cat.get(201).show_page(5)
    assert cat.get(201).page_numbers == [1, 2, 3, 4, 5] and cat.get(201).pages_total == 5


def test_a_dms_without_the_tag_still_lists_everything_and_says_so():
    cat, sa = make(tags=[("scan", 3)])
    cat.refresh()
    assert cat.tag_ids == [] and cat.unmatched_tags == ["invoice"]
    assert [d.id for d in cat.docs] == [101, 102, 103]           # unfiltered list
    assert "ไม่พบ tag" in cat.list_error and "invoice" in cat.list_error
    assert cat.stats()["unmatched_tags"] == ["invoice"]


def test_a_dms_that_cannot_be_listed_is_an_error_never_an_empty_list():
    cat, sa = make(list_raises=ConnectionError("dms down"))
    with pytest.raises(CatalogError, match="ConnectionError: dms down"):
        cat.refresh()
    assert cat.docs == [] and cat.list_error == "ConnectionError: dms down"


def test_a_refresh_that_fails_keeps_the_last_good_list():
    cat = make()[0]
    cat.refresh()
    before = [d.id for d in cat.docs]
    cat.reader.fail_list = ConnectionError("dms down")
    assert cat.refresh() is cat                                  # the old list survives
    assert [d.id for d in cat.docs] == before
    assert cat.list_error == "ConnectionError: dms down"
    assert cat.stats()["error"] == "ConnectionError: dms down" and cat.stats()["documents"] == 3


def test_an_unknown_document_id_is_not_a_document():
    cat = make()[0]
    cat.refresh()
    with pytest.raises(KeyError):
        cat.get(9999)
    assert cat.get(101).id == 101


def test_the_title_falls_back_to_the_file_name_then_the_dms_id():
    cat = make(docs=[_paper(301, title="   "), _paper(302, title="", file_name=""),
                     _paper(303, title="KEEP ME")])[0]
    cat.refresh()
    assert [cat.get(i).title for i in (301, 302, 303)] == ["DMS-301.pdf", "DMS-302", "KEEP ME"]


def test_health_and_stats_describe_the_source_for_the_screen():
    cat = make()[0]
    cat.refresh()
    assert cat.health() == {"base_url": "http://dms.test", "dms_total": 3, "tag": "invoice", "tag_ids": [7]}
    s = cat.stats()
    assert s == {"kind": "paperless", "documents": 3, "pages": 3, "tag": "invoice", "tag_ids": [7],
                 "dms_total": 3, "unmatched_tags": [], "error": None}


def test_the_reader_comes_from_system_a_itself(harness):
    """The portal has no Paperless client of its own: the reader is System A's, built with System A's settings."""
    import os

    from system_a.adapters.paperless.reader import PaperlessReader
    from webapp import sysa
    from webapp.config import Settings

    sa = sysa.init(Settings(system_a_home=harness, mode="sandbox"))
    assert sa.root == harness and callable(sa.process_pdf)
    reader = sa.container.build_paperless(sa.a_settings())       # System A builds it from System A's config
    assert isinstance(reader, PaperlessReader) and reader.base_url
    assert sa.a_settings().mode == "sandbox" and sa.a_settings().ai_mode == "sim"
    assert os.environ["SYSTEM_A_MODE"] == "sandbox"              # the harness, never the production Oracle

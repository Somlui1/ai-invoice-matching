import json
import time

import pytest

from webapp.batch import BatchError, BatchSource, parse_report


def test_reads_the_fixture(batch_dir):
    b = BatchSource(batch_dir)
    assert [d.id for d in b.docs] == [101, 102, 103, 104, 105, 106, 107]
    d = b.get(102)
    assert d.title == "SYN_ORIGINAL_COPY_PO" and d.page_numbers == [1, 2, 3] and d.pages[2].doc_type == "purchase_order"
    assert b.colors["header"] == "#d62728"
    assert all(i["bbox_norm"] and len(i["bbox_norm"]) == 4 for i in d.pages[0].kept)


def test_accepts_the_report_file_or_its_folder(batch_dir):
    assert BatchSource(batch_dir).report_path == BatchSource(batch_dir / "report.html").report_path


def test_stats_and_images(batch_dir):
    s = BatchSource(batch_dir).stats()
    assert s["documents"] == 7 and s["pages"] == 9 and s["images_missing"] == 1 and s["items_without_bbox"] == 0
    b = BatchSource(batch_dir)
    assert b.image_path(101, 1).is_file() and b.image_path(105, 1) is None
    assert b.viewer_url(101) == "/batch/docs/doc_101/viewer.html" and b.viewer_url(102) is None


@pytest.mark.parametrize("text,msg", [("<html>nothing</html>", "no 'const DATA='"),
                                      ("const DATA=[{broken", "not valid JSON"),
                                      ("const DATA={};", "not a list"),
                                      ('const DATA=[{"title":"x"}];', "no 'id'"),
                                      ('const DATA=[{"id":1},{"id":1}];', "duplicate")])
def test_bad_reports_fail_with_a_reason(text, msg):
    with pytest.raises(BatchError, match=msg):
        parse_report(text)


def test_missing_report(tmp_path):
    with pytest.raises(BatchError, match="not found"):
        BatchSource(tmp_path / "nope")


def test_image_paths_cannot_escape_the_batch_folder(tmp_path):
    (tmp_path / "secret.txt").write_text("x")
    sub = tmp_path / "batch"
    sub.mkdir()
    doc = {"id": 1, "title": "t", "pages": [{"page": 1, "image": "../secret.txt", "kept": []}]}
    (sub / "report.html").write_text("const DATA=" + json.dumps([doc]) + ";", encoding="utf-8")
    b = BatchSource(sub)
    assert b.image_path(1, 1) is None


def test_pdf_lookup(batch_dir, tmp_path):
    b = BatchSource(batch_dir)
    assert b.pdf_path(101) is None
    (tmp_path / "doc_101.pdf").write_bytes(b"%PDF-1.4")
    assert b.pdf_path(101, tmp_path).name == "doc_101.pdf"
    (tmp_path / "SYN_NO_SIGNATURE.pdf").write_bytes(b"%PDF-1.4")
    assert b.pdf_path(104, tmp_path).name == "SYN_NO_SIGNATURE.pdf"


def test_a_large_report_parses_quickly(tmp_path):
    item = {"type": "other", "label": "note", "text": "x" * 80, "bbox_norm": [0.1, 0.1, 0.2, 0.02], "bbox_px": [1, 2, 3, 4]}
    docs = [{"id": i, "title": f"d{i}", "pages": [{"page": 1, "image": f"docs/doc_{i}/page_1.jpg", "kept": [item] * 60}]}
            for i in range(1, 801)]
    f = tmp_path / "report.html"
    f.write_text("<script>const DATA=" + json.dumps(docs) + ", COLORS={};</script>", encoding="utf-8")
    t0 = time.perf_counter()
    b = BatchSource(f)
    assert len(b.docs) == 800 and time.perf_counter() - t0 < 5

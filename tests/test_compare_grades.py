import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("compare_grades", Path(__file__).resolve().parents[1] / "scripts" / "compare_grades.py")
compare_grades = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare_grades)


def test_reads_only_n_lines_and_ignores_the_rest():
    ns = compare_grades.read_ns("a15 P2 N:  TRX\nall others Y\nc4 q1 n: two questions\n")
    assert ns == {("a15", "P2"): "TRX", ("c4", "Q1"): "two questions"}


def test_disagreements_are_the_cells_only_one_grader_marked():
    a = compare_grades.read_ns("a04 P3 N: pull-ups\na15 P2 N: TRX")
    b = compare_grades.read_ns("a04 P3 N: hard\nd2 P1 N: wrong focus")
    result = compare_grades.compare(a, b)
    assert result["both"] == [("a04", "P3")]
    assert result["only_a"] == [("a15", "P2")] and result["only_b"] == [("d2", "P1")]
    assert result["agreement"] == round(100 * (135 - 2) / 135, 1)

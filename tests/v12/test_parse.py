"""Independent synthetic acceptance examples for the 53 adopted P05 IDs.

Expected values are literal test fixtures, not produced from parser/config
logic.  P05_RESULTS is populated only when a test actually executes; it also
retains a failed result before re-raising an assertion.
"""

import csv
import json
from pathlib import Path
import tempfile
import unittest

from src.steam_parse import (
    audit_keys, literal_csv, missing_class, parse_age, parse_appid, parse_date,
    parse_english, parse_rating, parse_ratings, parse_sequence, sequence_diagnostics,
    sequence_features,
)


P05_RESULTS = {}


def _record(identifier, operation):
    evidence = _acceptance_evidence(identifier)
    try:
        operation()
    except Exception as exc:
        P05_RESULTS[identifier] = {"status": "FAIL", "error": str(exc), "evidence": evidence}
        raise
    else:
        P05_RESULTS[identifier] = {"status": "PASS", "scope": "synthetic", "evidence": evidence}


# Each fixture binds an original assertion ID to an independent expected value.
_SCALARS = {
    "P05-APPID-01": (parse_appid, " 0012 ", "0012", "PRESENT", (), ("WARN_LEADING_ZERO",)),
    "P05-APPID-02": (parse_appid, "12", "12", "PRESENT", (), ()),
    "P05-APPID-04": (parse_appid, "0", "0", "PRESENT", (), ()),
    "P05-APPID-05": (parse_appid, "+12", None, "INVALID", ("ERR_APPID_ILLEGAL",), ()),
    "P05-APPID-06": (parse_appid, "12.0", None, "INVALID", ("ERR_APPID_ILLEGAL",), ()),
    "P05-APPID-07": (parse_appid, "１２", None, "INVALID", ("ERR_APPID_ILLEGAL",), ()),
    "P05-APPID-08": (parse_appid, "٠١", None, "INVALID", ("ERR_APPID_ILLEGAL",), ()),
    "P05-APPID-09": (parse_appid, "9223372036854775808", None, "INVALID", ("ERR_APPID_OUT_OF_INT64",), ()),
    "P05-APPID-10": (parse_appid, "", None, "MISSING_EMPTY", ("APPID_MISSING",), ()),
    "P05-APPID-11": (parse_appid, "   ", None, "MISSING_WHITESPACE", ("APPID_MISSING",), ()),
    "P05-APPID-12": (parse_appid, "9223372036854775807", "9223372036854775807", "PRESENT", (), ()),
    "P05-APPID-13": (parse_appid, "unknown", None, "INVALID", ("ERR_APPID_ILLEGAL",), ()),
    "P05-ENG-01": (parse_english, " 1 ", 1, "PRESENT", (), ()),
    "P05-ENG-02": (parse_english, "1.0", None, "INVALID", ("ERR_ENGLISH_ILLEGAL",), ()),
    "P05-ENG-03": (parse_english, " UNKNOWN ", None, "MISSING_DECLARED", (), ()),
    "P05-ENG-04": (parse_english, "", None, "MISSING_EMPTY", (), ()),
    "P05-ENG-05": (parse_english, "bad", None, "INVALID", ("ERR_ENGLISH_ILLEGAL",), ()),
    "P05-ENG-06": (parse_english, "+1", None, "INVALID", ("ERR_ENGLISH_ILLEGAL",), ()),
    "P05-ENG-07": (parse_english, "true", None, "INVALID", ("ERR_ENGLISH_ILLEGAL",), ()),
    "P05-ENG-08": (parse_english, "0", 0, "PRESENT", (), ()),
    "P05-AGE-01": (parse_age, "0", 0, "PRESENT", (), ()),
    "P05-AGE-02": (parse_age, "-1", None, "INVALID", ("ERR_AGE_NEGATIVE",), ()),
    "P05-AGE-03": (parse_age, "12.5", None, "INVALID", ("ERR_AGE_NON_INTEGER",), ()),
    "P05-AGE-04": (parse_age, "1e2", None, "INVALID", ("ERR_AGE_NON_INTEGER",), ()),
    "P05-AGE-05": (parse_age, "1e309", None, "INVALID", ("ERR_AGE_NON_INTEGER",), ()),
    "P05-AGE-06": (parse_age, "inf", None, "INVALID", ("ERR_AGE_NON_FINITE",), ()),
    "P05-AGE-07": (parse_age, "NaN", None, "MISSING_DECLARED", (), ()),
    "P05-AGE-08": (parse_age, " NA ", None, "INVALID", ("ERR_AGE_UNPARSEABLE",), ()),
    "P05-AGE-09": (parse_age, "", None, "MISSING_EMPTY", (), ()),
    "P05-AGE-10": (parse_age, "12", 12, "PRESENT", (), ()),
    "P05-AGE-11": (parse_age, "1e-999", None, "INVALID", ("ERR_AGE_NON_INTEGER",), ()),
    "P05-AGE-12": (parse_age, "-1e-999", None, "INVALID", ("ERR_AGE_NON_INTEGER",), ()),
}

_SEQUENCES = {
    "P05-ENT-01": [("developer", "A; B;A;; unknown ", ("A", "B"), "PRESENT", "S_LIST", (), {})],
    "P05-ENT-02": [("publisher", "A;a", ("A", "a"), "PRESENT", "S_LIST", (), {})],
    "P05-ENT-03": [("developer", "A,B", ("A,B",), "PRESENT", "S_LIST", ("WARN_SUSPECT_DELIMITER_PRESENT",), {})],
    # The adopted wire value is None. Derived history/count behavior uses ().
    "P05-ENT-04": [("developer", "unknown", None, "MISSING_DECLARED", "S_MISSING", (), {})],
    "P05-ENT-05": [("developer", "", None, "MISSING_EMPTY", "S_MISSING", (), {}),
                   ("publisher", "   ", None, "MISSING_WHITESPACE", "S_MISSING", (), {})],
    "P05-ENT-06": [("developer", "A;B;A", ("A", "B"), "PRESENT", "S_LIST", (), {})],
    "P05-MV-01": [("platforms", " windows ;mac;windows;; ", ("windows", "mac"), "PRESENT", "S_LIST", (),
                   {"platform_count": 2, "has_windows": True, "has_mac": True, "has_linux": False})],
    "P05-MV-02": [("platforms", "notwindows", ("notwindows",), "PRESENT", "S_LIST", (),
                   {"platform_count": 1, "has_windows": False, "has_mac": False, "has_linux": False})],
    "P05-MV-03": [("platforms", "Windows;LINUX", ("Windows", "LINUX"), "PRESENT", "S_LIST", (),
                   {"platform_count": 2, "has_windows": True, "has_mac": False, "has_linux": True})],
    "P05-MV-04": [("platforms", "windows|linux", ("windows|linux",), "PRESENT", "S_LIST", ("WARN_MIXED_DELIMITER",),
                   {"platform_count": 1, "has_windows": False, "has_mac": False, "has_linux": False})],
    "P05-MV-05": [("platforms", "[windows,mac]", ("[windows,mac]",), "PRESENT", "S_LIST", ("WARN_MIXED_DELIMITER",),
                   {"platform_count": 1, "has_windows": False, "has_mac": False, "has_linux": False})],
    "P05-MV-06": [("platforms", "unknown", None, "MISSING_DECLARED", "S_MISSING", (),
                   {"platform_count": 0, "has_windows": False, "has_mac": False, "has_linux": False})],
    "P05-MV-07": [("categories", "Action;Action;Indie;unknown", ("Action", "Indie"), "PRESENT", "S_LIST", (), {"category_count": 2})],
    "P05-MV-08": [("genres", "Action,Indie", ("Action,Indie",), "PRESENT", "S_LIST", ("WARN_MIXED_DELIMITER",), {"genre_count": 1})],
    "P05-MV-09": [("categories", "Action; action ", ("Action", "action"), "PRESENT", "S_LIST", (), {"category_count": 2})],
    "P05-MV-10": [("platforms", "", None, "MISSING_EMPTY", "S_MISSING", (),
                   {"platform_count": 0, "has_windows": False, "has_mac": False, "has_linux": False}),
                  ("platforms", "   ", None, "MISSING_WHITESPACE", "S_MISSING", (),
                   {"platform_count": 0, "has_windows": False, "has_mac": False, "has_linux": False})],
    "P05-MV-11": [("platforms", "Windows;windows", ("Windows", "windows"), "PRESENT", "S_LIST", (),
                   {"platform_count": 2, "has_windows": True, "has_mac": False, "has_linux": False})],
}

_DATES = {
    "P05-DATE-01": ("2016-12-31T23:30:00-05:00", "2017-01-01T04:30:00+00:00", 2017, ()),
    "P05-DATE-02": ("bad-date", None, None, ("DATE_NAT",)),
    "P05-DATE-03": ("2018-12-31", "2018-12-31T00:00:00+00:00", 2018, ()),
}

P05_TEST_IDS = frozenset(_SCALARS) | frozenset(_SEQUENCES) | frozenset(_DATES) | {"P05-APPID-03"}


def _acceptance_evidence(identifier):
    """Name the actually executed assertion and its independent fixture."""
    evidence = {"test_method": "AdoptedP05Tests.test_" + identifier.replace("-", "_")}
    if identifier in _SCALARS:
        parser, raw, value, source, errors, warnings = _SCALARS[identifier]
        evidence.update({
            "fixture": "tests/v12/test_parse.py:_SCALARS[" + identifier + "]",
            "parser": parser.__name__, "inputs": {"raw": raw},
            "expected": {"value": value, "source_class": source,
                         "errors": errors, "warnings": warnings,
                         "raw_preserved": raw, "state": None},
        })
    elif identifier in _SEQUENCES:
        evidence.update({
            "fixture": "tests/v12/test_parse.py:_SEQUENCES[" + identifier + "]",
            "parser": "parse_sequence plus sequence_features",
            "cases": [{"inputs": {"field": field, "raw": raw},
                       "expected": {"value": value, "source_class": source,
                                    "state": state, "warnings": warnings,
                                    "features": features, "raw_preserved": raw}}
                      for field, raw, value, source, state, warnings, features
                      in _SEQUENCES[identifier]],
        })
        if identifier == "P05-MV-05":
            evidence["additional_expected_diagnostics"] = {
                "rows_wrapped_in_brackets": 1,
                "rows_with_alternate_delimiter": 1,
                "unknown_tokens": ("[windows,mac]",),
            }
    elif identifier in _DATES:
        raw, utc, year, warnings = _DATES[identifier]
        evidence.update({
            "fixture": "tests/v12/test_parse.py:_DATES[" + identifier + "]",
            "parser": "parse_date", "inputs": {"raw": raw},
            "expected": {"utc_isoformat": utc, "release_year": year,
                         "warnings": warnings, "errors": (), "raw_preserved": raw},
        })
    elif identifier == "P05-APPID-03":
        evidence.update({
            "fixture": "tests/v12/test_parse.py:AdoptedP05Tests.test_P05_APPID_03",
            "parser": "audit_keys", "inputs": {"appid": [" 0012 ", "12"]},
            "expected": {"parsed_keys": ["0012", "12"], "raw_cardinality": 2,
                         "strip_cardinality": 2, "duplicate_keys": [],
                         "strip_collision_count": 0, "invalid_rows": [],
                         "blocking": False, "raw_rows_preserved": True},
        })
    else:
        raise KeyError(identifier)
    return evidence


class AdoptedP05Tests(unittest.TestCase):
    def _check_scalar(self, case):
        parser, raw, expected, source, errors, warnings = case
        parsed = parser(raw)
        self.assertEqual(parsed.raw, raw)
        self.assertEqual(parsed.value, expected)
        self.assertEqual(parsed.source_class, source)
        self.assertEqual(parsed.errors, errors)
        self.assertEqual(parsed.warnings, warnings)
        self.assertEqual(parsed.valid, not bool(errors))
        self.assertIsNone(parsed.state)
        if expected is not None:
            self.assertIs(type(parsed.value), type(expected))

    def _check_sequences(self, cases):
        for field, raw, expected, source, state, warnings, features in cases:
            parsed = parse_sequence(raw, field)
            self.assertEqual(parsed.raw, raw)
            self.assertEqual(parsed.value, expected)
            self.assertEqual(parsed.source_class, source)
            self.assertEqual(parsed.state, state)
            self.assertEqual(parsed.warnings, warnings)
            self.assertEqual(parsed.errors, ())
            self.assertTrue(parsed.valid)
            self.assertEqual(sequence_features(parsed, field), features)
            if raw == "[windows,mac]":
                diagnostic = sequence_diagnostics(parsed, field)
                self.assertEqual(diagnostic["rows_wrapped_in_brackets"], 1)
                self.assertEqual(diagnostic["unknown_tokens"], ("[windows,mac]",))
                self.assertEqual(diagnostic["rows_with_alternate_delimiter"], 1)

    def _check_date(self, case):
        raw, expected, year, warnings = case
        parsed = parse_date(raw)
        self.assertEqual(parsed.raw, raw)
        self.assertEqual(None if parsed.value is None else parsed.value.isoformat(), expected)
        self.assertEqual(None if parsed.value is None else parsed.value.year, year)
        self.assertEqual(parsed.warnings, warnings)
        self.assertEqual(parsed.errors, ())
        self.assertTrue(parsed.valid)

    def test_P05_APPID_03(self):
        def operation():
            rows = [{"appid": " 0012 "}, {"appid": "12"}]
            result = audit_keys(rows)
            self.assertEqual([entry.raw for entry in result["parsed"]], [" 0012 ", "12"])
            self.assertEqual([entry.value for entry in result["parsed"]], ["0012", "12"])
            self.assertEqual(result["raw_cardinality"], 2)
            self.assertEqual(result["strip_cardinality"], 2)
            self.assertEqual(result["duplicate_keys"], [])
            self.assertEqual(result["strip_collision_count"], 0)
            self.assertEqual(result["invalid_rows"], [])
            self.assertFalse(result["blocking"])
            self.assertEqual(rows, [{"appid": " 0012 "}, {"appid": "12"}])
        _record("P05-APPID-03", operation)


def _make_test(identifier, kind, fixture):
    def test(self):
        checker = {"scalar": self._check_scalar,
                   "sequence": self._check_sequences,
                   "date": self._check_date}[kind]
        _record(identifier, lambda: checker(fixture))
    return test


for _kind, _cases in (("scalar", _SCALARS), ("sequence", _SEQUENCES), ("date", _DATES)):
    for _identifier, _fixture in _cases.items():
        setattr(AdoptedP05Tests, "test_" + _identifier.replace("-", "_"),
                _make_test(_identifier, _kind, _fixture))


class ParseBoundaryTests(unittest.TestCase):
    def test_p05_manifest_is_exactly_53_independent_ids(self):
        index = Path(__file__).resolve().parents[2] / "docs/data_contract/assertion_index.json"
        declared = {item["id"] for item in json.loads(index.read_text())["P05"]}
        self.assertEqual(len(P05_TEST_IDS), 53)
        self.assertEqual(P05_TEST_IDS, declared)

    def test_long_integer_magnitudes_do_not_hit_interpreter_limit(self):
        zero_prefix = "0" * 5000
        self.assertEqual(parse_appid(zero_prefix + "12").value, zero_prefix + "12")
        self.assertEqual(parse_age(zero_prefix + "12").value, 12)
        self.assertEqual(parse_age("-" + zero_prefix).value, 0)
        self.assertEqual(parse_age("9" * 5000).errors, ("ERR_AGE_OUT_OF_INT64",))
        self.assertEqual(parse_age("-" + "9" * 5000).errors, ("ERR_AGE_NEGATIVE",))
        self.assertEqual(parse_appid("9" * 5000).errors, ("ERR_APPID_OUT_OF_INT64",))
        self.assertEqual(parse_rating(zero_prefix + "12").value, 12)
        self.assertEqual(parse_rating("9" * 5000).errors, ("RATINGS_OUT_OF_RANGE",))

    def test_age_unicode_signed_zero_and_storage_domain(self):
        for text, expected in (("１２", 12), ("٠١", 1), ("+۱۲", 12), ("-٠", 0),
                               ("9223372036854775807", 9223372036854775807), ("99", 99)):
            with self.subTest(text=text):
                parsed = parse_age(text)
                self.assertEqual(parsed.value, expected)
                self.assertTrue(parsed.valid)
        self.assertEqual(parse_age("9223372036854775808").errors, ("ERR_AGE_OUT_OF_INT64",))
        self.assertEqual(parse_age("-0.0").errors, ("ERR_AGE_NON_INTEGER",))
        self.assertEqual(parse_age("+Infinity").errors, ("ERR_AGE_NON_FINITE",))
        self.assertEqual(parse_age(" -inF ").errors, ("ERR_AGE_NON_FINITE",))
        self.assertEqual(parse_age("True").errors, ("ERR_AGE_UNPARSEABLE",))

    def test_each_table_duplicate_and_collision_audits_are_independent(self):
        first = audit_keys([{"appid": " 12"}, {"appid": "12 "}, {"appid": "13"}])
        self.assertEqual(first["raw_cardinality"], 3)
        self.assertEqual(first["strip_cardinality"], 2)
        self.assertEqual(first["duplicate_keys"], ["12"])
        self.assertEqual(first["strip_collision_count"], 1)
        self.assertEqual(first["invalid_rows"], [1, 2])
        self.assertTrue(first["blocking"])
        self.assertEqual([item.errors for item in first["parsed"]],
                         [("ERR_APPID_NORMALISATION_COLLISION",), ("ERR_APPID_NORMALISATION_COLLISION",), ()])
        same = audit_keys([{"steam_appid": "12"}, {"steam_appid": "12"}], "steam_appid")
        self.assertEqual(same["raw_cardinality"], 1)
        self.assertEqual(same["strip_collision_count"], 0)
        self.assertEqual(same["invalid_rows"], [1, 2])
        self.assertFalse(audit_keys([{"steam_appid": "12"}], "steam_appid")["blocking"])
        invalid = audit_keys([{"appid": "+1"}, {"appid": "+1"}])
        self.assertEqual(invalid["duplicate_keys"], ["+1"])
        self.assertEqual(invalid["parsed"][0].errors,
                         ("ERR_APPID_ILLEGAL", "ERR_APPID_NORMALISATION_COLLISION"))

    def test_sequence_source_missing_is_distinct_from_empty_list(self):
        for field in ("developer", "publisher", "platforms", "categories", "genres"):
            for text in ("unknown;NULL;; ", "; NaN ; NONE "):
                with self.subTest(field=field, text=text):
                    parsed = parse_sequence(text, field)
                    self.assertIsNone(parsed.value)
                    self.assertEqual(parsed.state, "S_MISSING")
                    self.assertEqual(parsed.source_class, "MISSING_DECLARED")
            empty = parse_sequence("; ;;; ", field)
            self.assertEqual(empty.value, ())
            self.assertEqual(empty.source_class, "PRESENT")
            self.assertEqual(empty.state, "S_EMPTY_LIST")
            self.assertEqual(parse_sequence("NA", field).value, ("NA",))
            self.assertEqual(parse_sequence("\"A\";(B)", field).value, ('"A"', "(B)"))

    def test_ratings_exact_domain_and_checked_sum(self):
        total = parse_ratings("9007199254740993", "1")
        self.assertEqual(total.value, 9007199254740994)
        self.assertTrue(total.valid)
        self.assertEqual(json.loads(total.raw), {"positive_ratings": "9007199254740993", "negative_ratings": "1"})
        self.assertEqual(parse_ratings("9223372036854775807", "0").value, 9223372036854775807)
        self.assertEqual(parse_ratings("9223372036854775807", "1").errors, ("RATINGS_SUM_OVERFLOW",))
        self.assertEqual(parse_ratings("9223372036854775808", "0").errors, ("RATINGS_OUT_OF_RANGE",))
        for invalid in ("", " ", "unknown", "+1", "-1", "1.0", "1e2", "１２", "٠١"):
            with self.subTest(invalid=invalid):
                self.assertEqual(parse_rating(invalid).errors, ("RATINGS_ILLEGAL_LITERAL",))
        self.assertEqual(parse_ratings("bad", "9223372036854775808").errors,
                         ("RATINGS_ILLEGAL_LITERAL", "RATINGS_OUT_OF_RANGE"))

    def test_literal_csv_preserves_empty_declared_na_and_multiline_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "literal.csv"
            rows = [["0012", "", "NA", "null", 'a\n"b",c'], [" 12 ", " ", "NaN", "None", "last"]]
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n", quoting=csv.QUOTE_ALL)
                writer.writerow(["appid", "empty", "na", "null", "text"])
                writer.writerows(rows)
            parsed = literal_csv(path)
            self.assertEqual(len(parsed), 2)
            self.assertEqual([list(row.values()) for row in parsed], rows)
            self.assertTrue(all(type(value) is str for row in parsed for value in row.values()))

    def test_literal_csv_preserves_fields_above_default_limit_and_restores_limit(self):
        original_limit = csv.field_size_limit()
        custom_limit = 1024
        zero_prefix = "0" * 140000
        record = {
            "appid": zero_prefix + "12",
            "required_age": zero_prefix + "12",
            "name": 'quoted,"name"\n' * 12000,
        }
        try:
            csv.field_size_limit(custom_limit)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "long.csv"
                with path.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(record),
                                            lineterminator="\n", quoting=csv.QUOTE_ALL)
                    writer.writeheader()
                    writer.writerow(record)
                self.assertEqual(literal_csv(path), [record])
                self.assertEqual(csv.field_size_limit(), custom_limit)
                self.assertEqual(parse_appid(record["appid"]).value, record["appid"])
                self.assertEqual(parse_age(record["required_age"]).value, 12)
        finally:
            csv.field_size_limit(original_limit)

    def test_literal_csv_restores_limit_after_long_malformed_record(self):
        original_limit = csv.field_size_limit()
        custom_limit = 1024
        try:
            csv.field_size_limit(custom_limit)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "long_bad_shape.csv"
                with path.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.writer(stream, lineterminator="\n", quoting=csv.QUOTE_ALL)
                    writer.writerow(["appid", "name"])
                    writer.writerow(["0" * 140000 + "12", "name", "extra"])
                with self.assertRaisesRegex(ValueError, "3 fields; expected 2"):
                    literal_csv(path)
                self.assertEqual(csv.field_size_limit(), custom_limit)
        finally:
            csv.field_size_limit(original_limit)

    def test_literal_csv_rejects_bad_header_or_record_shape(self):
        invalid_files = {
            "empty": "",
            "duplicate": "appid,appid\n1,1\n",
            "empty_header": "appid,\n1,a\n",
            "bom": "\ufeffappid\n1\n",
            "short": "appid,name\n1\n",
            "long": "appid,name\n1,x,y\n",
            "blank_record": "appid,name\n\n",
            "open_quote": 'appid,name\n1,"unterminated\n',
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, content in invalid_files.items():
                with self.subTest(name=name):
                    path = Path(directory) / (name + ".csv")
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        literal_csv(path)

    def test_nonliteral_inputs_are_rejected_and_missing_scope_is_field_specific(self):
        for parser in (parse_appid, parse_age, parse_english, parse_rating, parse_date):
            with self.subTest(parser=parser.__name__):
                with self.assertRaises(TypeError):
                    parser(None)
        self.assertEqual(missing_class("unknown", "appid"), "PRESENT")
        self.assertEqual(missing_class("unknown", "release_date"), "PRESENT")
        self.assertEqual(missing_class("NA", "english"), "PRESENT")
        self.assertEqual(missing_class(" UNKNOWN ", "english"), "MISSING_DECLARED")
        with self.assertRaises(ValueError):
            parse_sequence("1", "english")


if __name__ == "__main__":
    unittest.main()

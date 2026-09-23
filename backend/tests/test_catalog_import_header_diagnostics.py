"""Header-failure diagnostics for the bulk catalog importer.

WHY THIS FILE EXISTS
A brand tried three times to import a catalog and got 0 rows each time. Every
attempt returned the same sentence:

    "CSV needs unique headers including: title, category_slug, base_price,
     color_family, thumbnail_url"

That message restates the rule but never says which part of THEIR file broke
it. A one-character typo, an Excel file saved with semicolons, and a file the
user never meant to upload at all were all indistinguishable, so the only
recovery strategy left was guessing. The importer was behaving correctly and
still failing the user.

These tests pin the diagnosis, not the prose: each asserts that the message
names the actual offending column or the actual structural problem. They are
deliberately written against observable output rather than the source text of
the validator.

The privacy assertions matter as much as the usability ones. One of the files
uploaded in the real incident was a password manager export. Header text is
persisted to catalog_import_jobs.errors_json, so the diagnostics must name
COLUMNS and never echo cell values.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.models.catalog import Category
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.services.brand_catalog_service import BrandCatalogService

REQUIRED = "title,category_slug,base_price,color_family,thumbnail_url"
GOOD_ROW = '"Tailored Blazer",outerwear,299.99,Navy,https://example.com/blazer.jpg'


@pytest.fixture()
def svc():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="importer@confit-portal-qa.example.com", hashed_password="x",
                full_name="Importer", role=UserRole.BRAND_MANAGER,
                preferred_language="en", is_active=True, is_verified=True)
    db.add(user)
    db.flush()
    db.add(BrandProfile(user_id=user.id, brand_name="Import Brand", slug="import-brand"))
    db.add(Category(name="Outerwear", name_ar="ملابس خارجية", slug="outerwear"))
    db.commit()
    service = BrandCatalogService(db)
    service._test_brand_id = db.query(BrandProfile).first().id
    yield service
    db.close()


def _message(svc, csv_text):
    _valid, errors, _stats = svc.parse_csv(csv_text, svc._test_brand_id)
    assert errors, "expected the import to be rejected, but it was accepted"
    return errors[0].to_dict()["message"]


class TestHeaderDiagnosisNamesTheRealProblem:
    """Each distinct mistake must produce a distinct, actionable message."""

    def test_single_misspelled_column_is_named(self, svc):
        msg = _message(svc, f"title,category_slug,base_prices,color_family,thumbnail_url\n{GOOD_ROW}\n")
        assert "base_prices" in msg, f"the user's actual typo is not quoted back: {msg}"
        assert "base_price" in msg
        # It must not dump the full requirements list for a one-column typo.
        assert "color_family" not in msg, f"message buries the real fix in boilerplate: {msg}"

    def test_semicolon_delimiter_is_identified_as_such(self, svc):
        msg = _message(svc, "title;category_slug;base_price;color_family;thumbnail_url\na;b;1.00;N;https://e.com/a.jpg\n")
        assert "semicolon" in msg.lower(), f"Excel's semicolon export is not diagnosed: {msg}"
        assert "comma" in msg.lower(), "the message must say what to change it to"

    def test_wrong_case_headers_get_one_sentence_not_five(self, svc):
        msg = _message(svc, f"{REQUIRED.upper()}\n{GOOD_ROW}\n")
        assert "case" in msg.lower(), f"case problem not identified: {msg}"
        # One combined sentence, not one clause per column.
        assert msg.lower().count("wrong case") == 1, f"message repeats itself per column: {msg}"

    def test_surrounding_whitespace_is_identified(self, svc):
        msg = _message(svc, f"title ,category_slug,base_price,color_family,thumbnail_url\n{GOOD_ROW}\n")
        assert "space" in msg.lower(), f"invisible whitespace problem not explained: {msg}"

    def test_duplicate_column_names_are_listed(self, svc):
        msg = _message(svc, f"title,title,category_slug,base_price,color_family,thumbnail_url\na,b,c,1.00,N,https://e.com/a.jpg\n")
        assert "title" in msg
        assert "more than once" in msg.lower() or "unique" in msg.lower()

    def test_completely_unrelated_file_is_called_out(self, svc):
        """The real incident: a password export and a form-submissions file."""
        msg = _message(svc, "name,url,username,password\nGitHub,https://gh.com,omar,pw\n")
        assert "does not look like a product catalog" in msg.lower(), (
            f"an entirely wrong file should be identified as such, not reported as a "
            f"missing-column problem: {msg}"
        )

    def test_empty_file_says_so(self, svc):
        msg = _message(svc, "")
        assert "no header row" in msg.lower() or "header" in msg.lower()

    def test_distinct_mistakes_produce_distinct_messages(self, svc):
        """The core regression: five failures must not collapse to one sentence."""
        messages = {
            _message(svc, f"title,category_slug,base_prices,color_family,thumbnail_url\n{GOOD_ROW}\n"),
            _message(svc, "title;category_slug;base_price;color_family;thumbnail_url\na;b;1.00;N;https://e.com/a.jpg\n"),
            _message(svc, f"{REQUIRED.upper()}\n{GOOD_ROW}\n"),
            _message(svc, "name,url,username,password\nGitHub,https://gh.com,omar,pw\n"),
            _message(svc, ""),
        }
        assert len(messages) == 5, (
            "different header failures collapsed to the same text, which is the exact "
            f"bug this file exists to prevent. Got {len(messages)} distinct messages:\n"
            + "\n".join(f"  - {m}" for m in sorted(messages))
        )


class TestDiagnosticsNeverLeakFileContents:
    """errors_json is persisted; the uploaded file may be anything at all."""

    def test_password_export_values_are_never_echoed(self, svc):
        secret = "hunter2-TOP-SECRET"
        csv_text = f"name,url,username,password\nGitHub,https://gh.com,omar,{secret}\n"
        _valid, errors, _stats = svc.parse_csv(csv_text, svc._test_brand_id)
        blob = " ".join(str(e.to_dict()) for e in errors)
        assert secret not in blob, (
            "a cell value from an accidentally-uploaded file reached the persisted "
            "error payload. Header diagnostics must reference column NAMES only."
        )

    def test_no_data_rows_are_parsed_when_the_header_is_rejected(self, svc):
        """Rejection must happen before row processing, so nothing is stored."""
        csv_text = "name,url,username,password\nGitHub,https://gh.com,omar,pw\n"
        _valid, _errors, stats = svc.parse_csv(csv_text, svc._test_brand_id)
        assert stats["total"] == 0, (
            "rows from a non-catalog file were read into the import pipeline; "
            "the header gate must short-circuit first"
        )
        assert stats["accepted"] == 0


class TestValidFilesStillImport:
    """Better error messages must not make the happy path stricter."""

    def test_the_documented_sample_is_accepted(self, svc):
        csv_text = (f"{REQUIRED},size,color,stock_level\n"
                    f'"Tailored Blazer",outerwear,299.99,Navy,'
                    f"https://example.com/blazer.jpg,M,Navy,20\n")
        _valid, errors, stats = svc.parse_csv(csv_text, svc._test_brand_id)
        assert stats["accepted"] == 1, f"the documented sample no longer imports: {[e.to_dict() for e in errors]}"

    def test_utf8_bom_is_tolerated(self, svc):
        """Excel writes a BOM; the downloadable template ships one deliberately."""
        csv_text = "\ufeff" + f"{REQUIRED}\n{GOOD_ROW}\n"
        _valid, errors, stats = svc.parse_csv(csv_text, svc._test_brand_id)
        assert stats["accepted"] == 1, f"BOM-prefixed file rejected: {[e.to_dict() for e in errors]}"

    def test_extra_optional_columns_do_not_break_the_header(self, svc):
        csv_text = (f"{REQUIRED},material,currency\n"
                    f"{GOOD_ROW},wool,USD\n")
        _valid, _errors, stats = svc.parse_csv(csv_text, svc._test_brand_id)
        assert stats["accepted"] == 1

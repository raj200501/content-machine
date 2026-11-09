from app.source_ingest.pay import from_greenhouse, from_lever, from_text


def test_hourly_range_from_escaped_html() -> None:
    pay = from_text("&lt;p&gt;The hourly pay range for this role is $47.00 - $58.00 USD&lt;/p&gt;")
    assert pay and pay.display == "$47–$58/hr" and pay.spoken == "47 to 58 dollars an hour"


def test_annual_and_monthly_ranges() -> None:
    assert from_text("Base salary: $120,000 – $150,000 per year").display == "$120K–$150K/yr"
    assert from_text("Monthly stipend of $8,000 to $9,500.").spoken == "8,000 to 9,500 dollars a month"
    assert from_text("We pay £3,200 - £3,600 per month").display == "£3,200–£3,600/mo"


def test_rejects_numbers_that_are_not_pay() -> None:
    assert from_text("Revenue grew $5 to $10 billion") is None
    assert from_text("No pay info here.") is None


def test_structured_board_fields() -> None:
    greenhouse = {"pay_input_ranges": [{"min_cents": 4700, "max_cents": 5800, "currency_type": "USD", "title": "US Hourly Range"}]}
    assert from_greenhouse(greenhouse).display == "$47–$58/hr"
    lever = {"salaryRange": {"currency": "USD", "interval": "per-hour-wage", "min": 40, "max": 52}}
    assert from_lever(lever).display == "$40–$52/hr"
    assert from_greenhouse({"content": "Pay: $50 - $60 per hour"}).display == "$50–$60/hr"


def test_greenhouse_items_keep_the_hosted_page_for_pay(monkeypatch) -> None:
    import app.source_ingest.jobs_ingest as ingest
    from app.config import Settings
    from app.models import SourceDefinition

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    board = {"jobs": [{"id": 8209134, "title": "Software Engineering Intern", "absolute_url": "https://www.mongodb.com/careers/job/?gh_jid=8209134", "location": {"name": "Austin"}, "updated_at": "2026-11-01T00:00:00Z"}]}
    detail = {"pay_input_ranges": [{"min_cents": 8700000, "max_cents": 12400000, "currency_type": "USD"}]}
    monkeypatch.setattr(ingest.requests, "get", lambda url, **_: Response(detail if url.endswith("8209134") else board))
    source = SourceDefinition(name="mongodb", source_type="job_board", url="https://boards-api.greenhouse.io/v1/boards/mongodb/jobs", board_type="greenhouse")
    items = ingest._greenhouse(source, Settings())
    assert items and items[0].metadata["hosted_url"] == "https://job-boards.greenhouse.io/mongodb/jobs/8209134"

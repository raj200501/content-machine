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

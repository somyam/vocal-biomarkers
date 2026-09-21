from app.auth import consume_stream_ticket, mint_stream_ticket


def test_stream_ticket_is_scoped_and_one_use():
    ticket = mint_stream_ticket("checkin-a", "mvp-user")
    assert consume_stream_ticket(ticket, "checkin-b") is None
    assert consume_stream_ticket(ticket, "checkin-a") == "mvp-user"
    assert consume_stream_ticket(ticket, "checkin-a") is None

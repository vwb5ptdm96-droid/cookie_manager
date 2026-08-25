from app.core.response import success_response


def test_success_response_returns_expected_shape():
    payload = {"status": "ok"}

    result = success_response(payload, message="done")

    assert result == {
        "success": True,
        "data": payload,
        "message": "done",
        "error_code": None,
    }


def success_response(data: object, message: str = "ok") -> dict[str, object]:
    return {
        "success": True,
        "data": data,
        "message": message,
        "error_code": None,
    }


def error_response(message: str, error_code: str) -> dict[str, object]:
    return {
        "success": False,
        "data": None,
        "message": message,
        "error_code": error_code,
    }


from dataclasses import dataclass


@dataclass
class AppError(Exception):
    error_code: str
    message: str
    hint: str

    def to_json(self) -> dict:
        return {
            "ok": False,
            "error_code": self.error_code,
            "message": self.message,
            "hint": self.hint,
        }

from app.security import generate_license_key


def test_generated_key_format_and_entropy_surface() -> None:
    values = {generate_license_key() for _ in range(100)}
    assert len(values) == 100
    for value in values:
        parts = value.split("-")
        assert parts[0] == "HT"
        assert len(parts) == 7
        assert all(len(group) == 4 for group in parts[1:])

import pytest

from app.services.vehicle_fleet_category import CARS, MOTORCYCLES, vehicle_category


@pytest.mark.parametrize(
    ("brand", "model", "expected"),
    [
        ("HONDA", "CG 160 FAN", MOTORCYCLES),
        ("HONDA", "BIZ 125 ES", MOTORCYCLES),
        ("HONDA", "NXR160 BROS ESDD", MOTORCYCLES),
        ("HONDA", "CIVIC LXS FLEX", CARS),
        ("HONDA", "CITY LX", CARS),
        ("HONDA", "HR-V EXL CVT", CARS),
        ("YAMAHA", "FZ25 FAZER", MOTORCYCLES),
        ("SUZUKI", "EN125 YES", MOTORCYCLES),
        ("SUZUKI", "V-STROM 650 XT", MOTORCYCLES),
        ("SUZUKI", "JIMNY 4 ALL", CARS),
        ("BMW", "G310 GS", MOTORCYCLES),
        ("BMW", "R1250GS A", MOTORCYCLES),
        ("BMW", "X1 S20I", CARS),
        ("BMW", "320I ACTIVE FLEX", CARS),
        ("PEUGEOT", "208 ACTIVE", CARS),
    ],
)
def test_fleet_vehicle_category(brand: str, model: str, expected: str) -> None:
    assert vehicle_category(brand, model) == expected

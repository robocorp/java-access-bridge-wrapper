def pytest_addoption(parser):
    parser.addoption(
        "--simple", action="store_true", help="Test a single title-based scenario, where callbacks are off."
    )

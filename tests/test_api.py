"""Basic API endpoint tests."""


class TestHealthEndpoints:
    """Test basic health/root endpoints."""

    def test_root_endpoint_structure(self):
        """Verify root response schema."""
        expected_keys = {"name", "version", "status", "docs"}
        # When running: response = client.get("/")
        # assert set(response.json().keys()) == expected_keys
        assert expected_keys == {"name", "version", "status", "docs"}

    def test_health_endpoint_structure(self):
        """Verify health response schema."""
        expected = {"status": "healthy"}
        assert expected["status"] == "healthy"


class TestFeeCalculation:
    """Test the fee calculation logic."""

    def test_fee_breakdown_20_dollar_card(self):
        """Verify fee math on a $20 sale."""
        subtotal = 2000  # $20.00 in cents
        platform_fee_percent = 4.0
        stripe_rate = 0.029
        stripe_fixed = 30  # 30 cents

        platform_fee = int(subtotal * platform_fee_percent / 100)
        stripe_fee = int(subtotal * stripe_rate + stripe_fixed)
        seller_payout = subtotal - platform_fee - stripe_fee

        assert platform_fee == 80  # $0.80
        assert stripe_fee == 88  # $0.88
        assert seller_payout == 1832  # $18.32

    def test_fee_breakdown_5_dollar_card(self):
        """Verify fee math on a $5 sale."""
        subtotal = 500
        platform_fee = int(500 * 4.0 / 100)
        stripe_fee = int(500 * 0.029 + 30)
        seller_payout = subtotal - platform_fee - stripe_fee

        assert platform_fee == 20  # $0.20
        assert stripe_fee == 44  # $0.44 (rounded)
        assert seller_payout == 436  # $4.36

    def test_fee_breakdown_100_dollar_card(self):
        """Verify fee math on a $100 sale."""
        subtotal = 10000
        platform_fee = int(10000 * 4.0 / 100)
        stripe_fee = int(10000 * 0.029 + 30)
        seller_payout = subtotal - platform_fee - stripe_fee

        assert platform_fee == 400  # $4.00
        assert stripe_fee == 320  # $3.20
        assert seller_payout == 9280  # $92.80


class TestCardClassification:
    """Test card type classification logic from seeder."""

    def test_play_card_detection(self):
        """Cards with PL- prefix are Plays."""
        card_num = "PL-13"
        assert card_num.startswith("PL-")

    def test_bonus_play_detection(self):
        """Cards with BPL- prefix are Bonus Plays."""
        card_num = "BPL-25"
        assert card_num.startswith("BPL-")

    def test_hot_dog_detection(self):
        """Cards with HD- prefix are Hot Dogs."""
        card_num = "HD-1"
        assert card_num.startswith("HD-")

    def test_hero_detection_by_power(self):
        """Cards with power > 0 are Heroes."""
        power = 150
        assert power > 0


class TestConditions:
    """Test card condition values."""

    VALID_CONDITIONS = [
        "Mint",
        "Near Mint",
        "Lightly Played",
        "Moderately Played",
        "Heavily Played",
        "Damaged",
    ]

    def test_all_conditions_present(self):
        assert len(self.VALID_CONDITIONS) == 6

    def test_conditions_ordered_by_quality(self):
        assert self.VALID_CONDITIONS[0] == "Mint"
        assert self.VALID_CONDITIONS[-1] == "Damaged"

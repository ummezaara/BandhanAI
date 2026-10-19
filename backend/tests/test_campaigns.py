import unittest

from backend.app.campaigns.schemas import CampaignCreate, CampaignRecipient, CampaignSendBatchResponse
from backend.app.campaigns.service import serialize_campaign, serialize_recipient


class CampaignTests(unittest.TestCase):
    def test_campaign_create_schema_validation(self):
        req = CampaignCreate(name="Summer Sale 2026", type="re-engagement", description="20% off for inactive users")
        self.assertEqual(req.name, "Summer Sale 2026")
        self.assertEqual(req.type, "re-engagement")

    def test_serialize_campaign_dict(self):
        raw_row = {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "org_id": "98765432-e89b-12d3-a456-426614174000",
            "name": "VIP Reward Campaign",
            "type": "loyalty",
            "description": "Exclusive perks for VIPs",
            "status": "draft",
            "created_at": None,
            "total_recipients": 15,
            "sent_recipients": 5,
            "pending_recipients": 10,
        }
        serialized = serialize_campaign(raw_row)
        self.assertEqual(serialized["name"], "VIP Reward Campaign")
        self.assertEqual(serialized["total_recipients"], 15)
        self.assertEqual(serialized["sent_recipients"], 5)
        self.assertEqual(serialized["pending_recipients"], 10)

    def test_serialize_recipient_dict(self):
        raw_recipient = {
            "recipient_id": "11111111-e89b-12d3-a456-426614174000",
            "campaign_id": "123e4567-e89b-12d3-a456-426614174000",
            "org_id": "98765432-e89b-12d3-a456-426614174000",
            "customer_name": "Alex Johnson",
            "customer_email": "alex@example.com",
            "subject": "Special offer for Alex",
            "body": "<p>Hi Alex</p>",
            "recommended_products": "[]",
            "status": "pending",
            "sent_at": None,
            "created_at": None,
        }
        serialized = serialize_recipient(raw_recipient)
        self.assertEqual(serialized["customer_name"], "Alex Johnson")
        self.assertEqual(serialized["status"], "pending")
        self.assertEqual(serialized["customer_email"], "alex@example.com")


if __name__ == "__main__":
    unittest.main()

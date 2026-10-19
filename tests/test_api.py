import unittest
from httpx import AsyncClient, ASGITransport
from datetime import date, timedelta
from app.main import app, trade_service, expiration_job, queue, exception_logger, Base, engine
from app.api.routes import set_dependencies

class TestTradeAPI(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        Base.metadata.create_all(bind=engine)
        set_dependencies(trade_service, expiration_job, queue, exception_logger)
        # Clear any leftover queue items and reset queue config
        while not queue._queue.empty():
            queue._queue.get_nowait()
        queue.is_paused = False
        queue.delay_seconds = 0.0

    async def test_root_serves_html(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/")
            self.assertEqual(res.status_code, 200)

    async def test_queue_config_endpoints(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Get queue config
            res_get = await client.get("/api/v1/trades/queue/config")
            self.assertEqual(res_get.status_code, 200)
            self.assertIn("delay_seconds", res_get.json())

            # Update queue config (pause queue)
            res_post = await client.post("/api/v1/trades/queue/config", json={"is_paused": True, "delay_seconds": 1.5})
            self.assertEqual(res_post.status_code, 200)
            data = res_post.json()
            self.assertTrue(data["is_paused"])
            self.assertEqual(data["delay_seconds"], 1.5)

            # Unpause queue
            await client.post("/api/v1/trades/queue/config", json={"is_paused": False, "delay_seconds": 0.0})

    async def test_batch_stream_and_validations(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            today = date.today()
            future_date = (today + timedelta(days=20)).isoformat()

            # Pause queue to test queue batch inspection
            await client.post("/api/v1/trades/queue/config", json={"is_paused": True})

            # Submit batch of 3 trades
            batch = [
                {"trade_id": "BATCH_1", "version": 1, "counter_party_id": "CP-1", "book_id": "B1", "maturity_date": future_date},
                {"trade_id": "BATCH_2", "version": 1, "counter_party_id": "CP-2", "book_id": "B2", "maturity_date": future_date},
                {"trade_id": "BATCH_3", "version": 1, "counter_party_id": "CP-3", "book_id": "B1", "maturity_date": future_date}
            ]
            res_batch = await client.post("/api/v1/trades/stream/batch", json=batch)
            self.assertEqual(res_batch.status_code, 202)
            self.assertEqual(res_batch.json()["count"], 3)

            # Inspect queued trades
            res_queue = await client.get("/api/v1/trades/queue")
            self.assertEqual(res_queue.status_code, 200)
            self.assertEqual(len(res_queue.json()), 3)

            # Unpause queue to let consumer process
            await client.post("/api/v1/trades/queue/config", json={"is_paused": False, "delay_seconds": 0.0})

    async def test_api_submit_trade_and_validations(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            today = date.today()
            future_date = (today + timedelta(days=20)).isoformat()
            past_date = (today - timedelta(days=5)).isoformat()

            # 1. Successful submission
            payload = {
                "trade_id": "T10",
                "version": 1,
                "counter_party_id": "CP-1",
                "book_id": "B1",
                "maturity_date": future_date
            }
            res = await client.post("/api/v1/trades", json=payload)
            self.assertEqual(res.status_code, 201)
            data = res.json()
            self.assertEqual(data["trade_id"], "T10")
            self.assertEqual(data["version"], 1)

            # 2. Lower version rejection
            payload_lower = {
                "trade_id": "T10",
                "version": 0,
                "counter_party_id": "CP-1",
                "book_id": "B1",
                "maturity_date": future_date
            }
            res_lower = await client.post("/api/v1/trades", json=payload_lower)
            self.assertEqual(res_lower.status_code, 422)
            self.assertIn("lower than existing version", res_lower.json()["detail"]["message"])

            # 3. Invalid maturity date rejection
            payload_past = {
                "trade_id": "T11",
                "version": 1,
                "counter_party_id": "CP-1",
                "book_id": "B1",
                "maturity_date": past_date
            }
            res_past = await client.post("/api/v1/trades", json=payload_past)
            self.assertEqual(res_past.status_code, 400)
            self.assertIn("maturity date", res_past.json()["detail"]["message"])

            # 4. Stream endpoint queueing
            res_stream = await client.post("/api/v1/trades/stream", json=payload)
            self.assertEqual(res_stream.status_code, 202)
            self.assertEqual(res_stream.json()["status"], "queued")

            # 5. List all trades in DB
            res_list = await client.get("/api/v1/trades")
            self.assertEqual(res_list.status_code, 200)
            self.assertTrue(len(res_list.json()) >= 1)

            # 6. List queued trades
            res_queue = await client.get("/api/v1/trades/queue")
            self.assertEqual(res_queue.status_code, 200)

            # 7. List exceptions log
            res_exc = await client.get("/api/v1/trades/exceptions")
            self.assertEqual(res_exc.status_code, 200)
            self.assertTrue(len(res_exc.json()) >= 2)

            # 8. Clear exceptions log
            res_clear = await client.delete("/api/v1/trades/exceptions")
            self.assertEqual(res_clear.status_code, 200)

if __name__ == "__main__":
    unittest.main()

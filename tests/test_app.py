import unittest
from types import SimpleNamespace

from dd1_rpc import app
from dd1_rpc.saves import Snapshot

HAMLET = Snapshot(
    game={"inraid": False, "raiddungeon": "none", "estatename": "E"},
    campaign_log={"total_weeks": 5},
)
RAID = Snapshot(
    game={"inraid": True, "raiddungeon": "weald"},
    raid={"raid_instance": {"id": "q1", "dungeon": "weald", "type": "explore"}, "torchlight": 50},
)


class FakeRpc:
    def __init__(self, fail_connect=False):
        self.calls = []
        self.fail_connect = fail_connect

    def connect(self):
        if self.fail_connect:
            raise ConnectionError("no discord")
        self.calls.append(("connect",))

    def update(self, **kwargs):
        self.calls.append(("update", kwargs))

    def clear(self):
        self.calls.append(("clear",))

    def close(self):
        self.calls.append(("close",))


class FakeReader:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def read(self):
        return self.snapshot


class Harness:
    def __init__(self, snapshot=HAMLET):
        self.now = 10_000.0
        self.proc = SimpleNamespace(pid=1, create_time=lambda: 9_000.0)
        self.reader = FakeReader(snapshot)
        self.rpcs = []
        self.app = app.PresenceApp(
            self.reader, self._factory, find_process=lambda: self.proc, clock=lambda: self.now
        )

    def _factory(self):
        rpc = FakeRpc()
        self.rpcs.append(rpc)
        return rpc

    def updates(self):
        return [c[1] for r in self.rpcs for c in r.calls if c[0] == "update"]

    def tick(self, advance=0.0):
        self.now += advance
        self.app.tick()


class PresenceAppTests(unittest.TestCase):
    def test_first_hamlet_update_counts_from_game_launch(self):
        h = Harness()
        h.tick()
        (update,) = h.updates()
        self.assertEqual(update["details"], "In the Hamlet")
        self.assertEqual(update["state"], "E · Week 5")
        self.assertEqual(update["start"], 9_000)

    def test_unchanged_state_is_not_resent(self):
        h = Harness()
        h.tick()
        h.tick(60)
        self.assertEqual(len(h.updates()), 1)

    def test_phase_change_restarts_timer(self):
        h = Harness()
        h.tick()
        h.reader.snapshot = RAID
        h.tick(60)
        raid_update = h.updates()[-1]
        self.assertEqual(raid_update["details"], "Exploring the Weald")
        self.assertEqual(raid_update["start"], int(h.now))

    def test_updates_are_rate_limited_then_delivered(self):
        h = Harness()
        h.tick()
        h.reader.snapshot = RAID
        h.tick(5)
        self.assertEqual(len(h.updates()), 1)
        h.tick(app.MIN_UPDATE_INTERVAL)
        self.assertEqual(len(h.updates()), 2)

    def test_game_close_clears_and_next_launch_restarts(self):
        h = Harness()
        h.tick()
        h.proc = None
        h.tick(10)
        self.assertEqual(h.rpcs[0].calls[-2:], [("clear",), ("close",)])
        h.proc = SimpleNamespace(pid=2, create_time=lambda: 9_900.0)
        h.tick(10)
        self.assertEqual(len(h.rpcs), 2)
        self.assertEqual(h.updates()[-1]["start"], 9_900)

    def test_unreadable_saves_show_generic_presence(self):
        h = Harness(snapshot=None)
        h.tick()
        self.assertEqual(h.updates()[0]["details"], "Playing Darkest Dungeon")

    def test_discord_unavailable_retries_after_delay(self):
        h = Harness()
        failing = FakeRpc(fail_connect=True)
        h.app.rpc_factory = lambda: (h.rpcs.append(failing), failing)[1]
        h.tick()
        h.tick(1)
        self.assertEqual(len(h.rpcs), 1)  # no hammering within the delay
        self.assertIn(("close",), failing.calls)  # the failed client is released
        h.app.rpc_factory = h._factory
        h.tick(app.RECONNECT_DELAY)
        self.assertEqual(len(h.updates()), 1)

    def test_invalid_client_id_is_fatal(self):
        h = Harness()

        class Rejecting(FakeRpc):
            def connect(self):
                raise app.InvalidID()

        h.app.rpc_factory = Rejecting
        with self.assertRaises(app.InvalidID):
            h.tick()

    def test_failed_update_reconnects_and_resends(self):
        h = Harness()
        h.tick()
        h.rpcs[0].update = lambda **kw: (_ for _ in ()).throw(BrokenPipeError())
        h.reader.snapshot = RAID
        h.tick(app.MIN_UPDATE_INTERVAL)
        self.assertIsNone(h.app._rpc)
        h.tick(app.RECONNECT_DELAY)
        self.assertEqual(h.updates()[-1]["details"], "Exploring the Weald")

    def test_payload_omits_empty_fields(self):
        activity = app.generic_activity()
        payload = app.presence_payload(activity, 1)
        for key in ("state", "large_text", "small_image", "small_text"):
            self.assertNotIn(key, payload)

    def test_payload_includes_small_image(self):
        activity = app.build_activity({"inraid": False, "game_mode": "new_game_plus"})
        payload = app.presence_payload(activity, 1)
        self.assertEqual(payload["small_image"], "mode_stygian")
        self.assertEqual(payload["small_text"], "Stygian")


if __name__ == "__main__":
    unittest.main()

import os
import sys
import threading
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from servidor.game_state import ENDED, PLAYING, GameState


class GameStateTest(unittest.TestCase):
    def test_concurrent_same_letter_only_one_valid_result(self):
        for _ in range(100):
            state = GameState("BANANA")
            state.add_player(1, "Ana")
            state.add_player(2, "Bia")
            results = []
            results_lock = threading.Lock()
            barrier = threading.Barrier(2)

            def guess(player_id):
                barrier.wait()
                result = state.process_guess(player_id, "a")
                with results_lock:
                    results.append(result)

            threads = [
                threading.Thread(target=guess, args=(1,)),
                threading.Thread(target=guess, args=(2,)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            valid_results = [result for result in results if result["valid"]]
            invalid_results = [result for result in results if not result["valid"]]

            self.assertEqual(1, len(valid_results))
            self.assertEqual(1, len(invalid_results))
            self.assertEqual({"A"}, state.guessed_letters)
            self.assertEqual([1, 3, 5], valid_results[0]["positions"])

    def test_repeated_letter_returns_invalid(self):
        state = GameState("CASA")
        state.add_player(1, "Ana")

        first = state.process_guess(1, "c")
        second = state.process_guess(1, "C")

        self.assertTrue(first["valid"])
        self.assertFalse(second["valid"])
        self.assertEqual({"C"}, state.guessed_letters)

    def test_broadcast_uses_socket_snapshot(self):
        state = GameState("CASA")

        class MutatingSocket:
            def __init__(self, callback=None):
                self.callback = callback
                self.sent = []

            def sendall(self, data):
                self.sent.append(data)
                if self.callback is not None:
                    self.callback()

        first_sock = MutatingSocket(lambda: state.remove_player(2))
        second_sock = MutatingSocket()
        state.add_player(1, "Ana", first_sock)
        state.add_player(2, "Bia", second_sock)

        state.broadcast("STATE_UPDATE", {"revealed": "C___"})

        self.assertEqual(1, len(first_sock.sent))
        self.assertEqual(1, len(second_sock.sent))
        self.assertNotIn(2, state.sockets)

    def test_remove_player_marks_spectator_while_playing(self):
        state = GameState("CASA")
        state.phase = PLAYING
        state.add_player(1, "Ana")
        state.add_player(2, "Bia")
        state.add_player(3, "Caio")

        result = state.remove_player(2)

        self.assertIsNone(result)
        self.assertTrue(state.players[2].is_spectator)
        self.assertEqual(PLAYING, state.phase)

    def test_remove_player_returns_survivor_when_one_active_remains(self):
        state = GameState("CASA")
        state.phase = PLAYING
        state.add_player(1, "Ana")
        state.add_player(2, "Bia")
        state.players[2].score = 99

        result = state.remove_player(2)

        self.assertIsNotNone(result)
        self.assertTrue(result["trigger_game_over"])
        self.assertEqual(1, result["winner_id"])
        self.assertEqual("Ana", result["winner_name"])
        self.assertEqual(ENDED, state.phase)


if __name__ == "__main__":
    unittest.main()

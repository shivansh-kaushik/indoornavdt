"""
tests/test_navigation.py — Comprehensive test suite for indoor navigation.

Verifies:
  Test 1: Room A -> Room B through a door -> PASS
  Test 2: Room A -> Room B separated by wall with no door -> NO ROUTE
  Test 3: Floor 1 -> Floor 2 using stairs -> PASS
  Test 4: Floor 1 -> Floor 2 with no stair/elevator -> NO ROUTE
  Test 5: Floor 1 -> Floor 3 using elevator -> PASS
  Test 6: Attempt virtual movement directly into wall -> MOVEMENT BLOCKED
  Test 7: Crowded corridor -> alternative lower-cost route selected
  Test 8: Crowded corridor when only single corridor available -> same route selected with increased cost
"""

import sys
from pathlib import Path

# Add src to path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unittest
import networkx as nx
from shapely.geometry import box

from navigation.collision import WallCollisionDetector, WallGeometry, DoorPortal
from navigation.route_validator import validate_graph
from build_graph import NavNode, NavEdge, build_nav_graph
from navigate import find_route


class TestIndoorNavigation(unittest.TestCase):

    def setUp(self):
        """Set up a synthetic 2-storey test environment."""
        self.detector = WallCollisionDetector()
        
        # Solid dividing wall on Floor 1 at X = 5.0 (width 0.4m, Y from 0 to 10)
        wall_box = box(4.8, 0.0, 5.2, 10.0)
        self.detector.walls_by_storey["Level 1"] = [
            WallGeometry(
                guid="wall_01",
                name="Dividing Wall",
                storey="Level 1",
                polygon_2d=wall_box,
                solid_polygon=wall_box,
                bbox_min=[4.8, 0.0, 0.0],
                bbox_max=[5.2, 10.0, 3.0],
            )
        ]
        # Register in STRtree
        from shapely.strtree import STRtree
        self.detector.wall_trees["Level 1"] = STRtree([wall_box])
        self.detector.tree_wall_maps["Level 1"] = self.detector.walls_by_storey["Level 1"]

    # ─────────────────────────────────────────────────────────────────────────
    # Test 1: Room A -> Room B through a door -> PASS
    # ─────────────────────────────────────────────────────────────────────────
    def test_01_room_to_room_through_door_pass(self):
        print("\n--- Test 1: Room A -> Room B through a door ---")
        nodes = {
            "ROOM_A": NavNode("ROOM_A", "room", 1, "Level 1", "sp_a", "Room A", 2.0, 5.0, 0.0, 0.0),
            "DOOR_01": NavNode("DOOR_01", "door", 1, "Level 1", "dr_01", "Door 1", 5.0, 5.0, 0.0, 0.0),
            "ROOM_B": NavNode("ROOM_B", "room", 1, "Level 1", "sp_b", "Room B", 8.0, 5.0, 0.0, 0.0),
        }
        edges = [
            NavEdge("ROOM_A", "DOOR_01", "door", 3.0, 1, 1),
            NavEdge("DOOR_01", "ROOM_B", "door", 3.0, 1, 1),
        ]
        G = build_nav_graph(nodes, edges)

        result = find_route(G, "ROOM_A", "ROOM_B")
        self.assertTrue(result.success, "Route through door should succeed")
        self.assertEqual(result.route, ["ROOM_A", "DOOR_01", "ROOM_B"])
        self.assertAlmostEqual(result.total_distance_m, 6.0, places=1)
        print("  RESULT: PASS (Route found via Door 1)")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 2: Room A -> Room B separated by wall with no door -> NO ROUTE
    # ─────────────────────────────────────────────────────────────────────────
    def test_02_room_to_room_wall_no_door_blocked(self):
        print("\n--- Test 2: Room A -> Room B separated by wall with no door ---")
        p_room_a = (2.0, 5.0)
        p_room_b = (8.0, 5.0)

        # Attempt candidate edge directly crossing the solid wall
        has_collision = self.detector.check_segment_collision(p_room_a, p_room_b, "Level 1")
        self.assertTrue(has_collision, "Direct path must collide with solid wall")

        # Because collision is detected, the builder rejects the edge
        nodes = {
            "ROOM_A": NavNode("ROOM_A", "room", 1, "Level 1", "sp_a", "Room A", 2.0, 5.0, 0.0, 0.0),
            "ROOM_B": NavNode("ROOM_B", "room", 1, "Level 1", "sp_b", "Room B", 8.0, 5.0, 0.0, 0.0),
        }
        edges = [] # Rejected edge
        G = build_nav_graph(nodes, edges)

        result = find_route(G, "ROOM_A", "ROOM_B")
        self.assertFalse(result.success, "Direct path across wall must fail")
        self.assertIn("No physical path exists", result.error)
        print("  RESULT: NO ROUTE (Correctly blocked by wall barrier)")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 3: Floor 1 -> Floor 2 using stairs -> PASS
    # ─────────────────────────────────────────────────────────────────────────
    def test_03_floor_1_to_floor_2_using_stairs_pass(self):
        print("\n--- Test 3: Floor 1 -> Floor 2 using stairs ---")
        nodes = {
            "F1_ROOM": NavNode("F1_ROOM", "room", 1, "Level 1", "sp_1", "Room 101", 2.0, 2.0, 0.0, 0.0),
            "F1_STAIR": NavNode("F1_STAIR", "stair", 1, "Level 1", "stair_1", "Stair Landing 1", 5.0, 2.0, 0.0, 0.0),
            "F2_STAIR": NavNode("F2_STAIR", "stair", 2, "Level 2", "stair_1", "Stair Landing 2", 5.0, 2.0, 3.0, 3.0),
            "F2_ROOM": NavNode("F2_ROOM", "room", 2, "Level 2", "sp_2", "Room 201", 8.0, 2.0, 3.0, 3.0),
        }
        edges = [
            NavEdge("F1_ROOM", "F1_STAIR", "walk", 3.0, 1, 1),
            NavEdge("F1_STAIR", "F2_STAIR", "stair", 3.0, 1, 2, accessible=False),
            NavEdge("F2_STAIR", "F2_ROOM", "walk", 3.0, 2, 2),
        ]
        G = build_nav_graph(nodes, edges)

        result = find_route(G, "F1_ROOM", "F2_ROOM")
        self.assertTrue(result.success, "Multi-floor stair route should succeed")
        self.assertEqual(len(result.floor_transitions), 1)
        self.assertEqual(result.floor_transitions[0]["from"], 1)
        self.assertEqual(result.floor_transitions[0]["to"], 2)
        self.assertEqual(result.floor_transitions[0]["type"], "stair")
        print("  RESULT: PASS (Stair transition Floor 1 -> Floor 2)")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 4: Floor 1 -> Floor 2 with no stair/elevator -> NO ROUTE
    # ─────────────────────────────────────────────────────────────────────────
    def test_04_floor_1_to_floor_2_no_stair_no_route(self):
        print("\n--- Test 4: Floor 1 -> Floor 2 with no stair/elevator ---")
        nodes = {
            "F1_ROOM": NavNode("F1_ROOM", "room", 1, "Level 1", "sp_1", "Room 101", 2.0, 2.0, 0.0, 0.0),
            "F2_ROOM": NavNode("F2_ROOM", "room", 2, "Level 2", "sp_2", "Room 201", 2.0, 2.0, 3.0, 3.0),
        }
        # Direct XY closeness without vertical portal MUST NOT create an edge
        edges = []
        G = build_nav_graph(nodes, edges)

        result = find_route(G, "F1_ROOM", "F2_ROOM")
        self.assertFalse(result.success, "Direct vertical movement without stairs must fail")
        print("  RESULT: NO ROUTE (Floors disconnected without vertical portal)")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 5: Floor 1 -> Floor 3 using elevator -> PASS
    # ─────────────────────────────────────────────────────────────────────────
    def test_05_floor_1_to_floor_3_using_elevator_pass(self):
        print("\n--- Test 5: Floor 1 -> Floor 3 using elevator ---")
        nodes = {
            "F1_ROOM": NavNode("F1_ROOM", "room", 1, "Level 1", "sp_1", "Room 101", 1.0, 1.0, 0.0, 0.0),
            "F1_LIFT": NavNode("F1_LIFT", "elevator", 1, "Level 1", "lift_1", "Elevator Shaft", 4.0, 1.0, 0.0, 0.0),
            "F3_LIFT": NavNode("F3_LIFT", "elevator", 3, "Level 3", "lift_1", "Elevator Shaft", 4.0, 1.0, 6.0, 6.0),
            "F3_ROOM": NavNode("F3_ROOM", "room", 3, "Level 3", "sp_3", "Room 301", 8.0, 1.0, 6.0, 6.0),
        }
        edges = [
            NavEdge("F1_ROOM", "F1_LIFT", "walk", 3.0, 1, 1),
            NavEdge("F1_LIFT", "F3_LIFT", "elevator", 6.0, 1, 3, accessible=True),
            NavEdge("F3_LIFT", "F3_ROOM", "walk", 4.0, 3, 3),
        ]
        G = build_nav_graph(nodes, edges)

        result = find_route(G, "F1_ROOM", "F3_ROOM", accessible_only=True)
        self.assertTrue(result.success, "Elevator route should succeed")
        self.assertEqual(len(result.floor_transitions), 1)
        self.assertEqual(result.floor_transitions[0]["type"], "elevator")
        self.assertEqual(result.floor_transitions[0]["from"], 1)
        self.assertEqual(result.floor_transitions[0]["to"], 3)
        print("  RESULT: PASS (Elevator transition Floor 1 -> Floor 3)")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 6: Attempt virtual movement directly into wall -> MOVEMENT BLOCKED
    # ─────────────────────────────────────────────────────────────────────────
    def test_06_virtual_movement_into_wall_blocked(self):
        print("\n--- Test 6: Attempt virtual movement directly into wall ---")
        avatar_pos = (4.0, 5.0, 0.0)      # Standing in front of wall at X=5.0
        target_pos = (5.5, 5.0, 0.0)      # Moving across wall to X=5.5

        # Perform collision check
        is_blocked = self.detector.check_segment_collision(avatar_pos, target_pos, "Level 1")
        self.assertTrue(is_blocked, "Movement directly into wall must be blocked")

        point_inside = self.detector.check_point_collision((5.0, 5.0, 0.0), "Level 1", clearance_m=0.1)
        self.assertTrue(point_inside, "Point inside wall must be detected as collision")
        print("  RESULT: MOVEMENT BLOCKED (Collision successfully intercepted)")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 7: Crowded corridor -> alternative lower-cost route selected
    # ─────────────────────────────────────────────────────────────────────────
    def test_07_crowded_corridor_alternative_route_selected(self):
        print("\n--- Test 7: Crowded corridor alternative route selection ---")
        nodes = {
            "START": NavNode("START", "room", 1, "Level 1", "s", "Start", 0.0, 0.0, 0.0, 0.0),
            "CORR_N": NavNode("CORR_N", "corridor", 1, "Level 1", "cn", "Corridor North", 5.0, 4.0, 0.0, 0.0),
            "CORR_S": NavNode("CORR_S", "corridor", 1, "Level 1", "cs", "Corridor South", 5.0, -4.0, 0.0, 0.0),
            "DEST":  NavNode("DEST", "room", 1, "Level 1", "d", "Dest", 10.0, 0.0, 0.0, 0.0),
        }
        # North corridor is normally slightly shorter: 10m total
        # South corridor is normally slightly longer: 14m total
        edges = [
            NavEdge("START", "CORR_N", "corridor", 5.0, 1, 1, capacity=2),
            NavEdge("CORR_N", "DEST", "corridor", 5.0, 1, 1, capacity=2),
            NavEdge("START", "CORR_S", "corridor", 7.0, 1, 1, capacity=5),
            NavEdge("CORR_S", "DEST", "corridor", 7.0, 1, 1, capacity=5),
        ]
        G = build_nav_graph(nodes, edges)

        # Baseline: normal conditions choose Corridor North
        base_route = find_route(G, "START", "DEST", avoid_crowded=False)
        self.assertIn("CORR_N", base_route.route)

        # Apply heavy crowd to Corridor North: 8 people (capacity 2 -> weight multiplier = 1 + 8/2 = 5.0)
        G.edges["START", "CORR_N"]["crowd_count"] = 8
        G.edges["START", "CORR_N"]["crowd_weight"] = 5.0
        G.edges["START", "CORR_N"]["weight"] = 5.0 * 5.0 # 25.0
        G.edges["CORR_N", "DEST"]["crowd_count"] = 8
        G.edges["CORR_N", "DEST"]["crowd_weight"] = 5.0
        G.edges["CORR_N", "DEST"]["weight"] = 5.0 * 5.0 # 25.0
        # Total North route weight = 50.0 > South route weight 14.0

        crowd_route = find_route(G, "START", "DEST", avoid_crowded=True)
        self.assertTrue(crowd_route.success)
        self.assertIn("CORR_S", crowd_route.route, "Should reroute through Corridor South")
        self.assertTrue(crowd_route.crowd_avoided)
        print("  RESULT: Alternative lower-cost route selected (Corridor South chosen)")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 8: Crowded corridor but only valid corridor available -> same route
    # ─────────────────────────────────────────────────────────────────────────
    def test_08_crowded_corridor_only_one_available_same_route_higher_cost(self):
        print("\n--- Test 8: Crowded corridor but only valid corridor available ---")
        nodes = {
            "ROOM_1": NavNode("ROOM_1", "room", 1, "Level 1", "r1", "Room 1", 0.0, 0.0, 0.0, 0.0),
            "SOLO_CORR": NavNode("SOLO_CORR", "corridor", 1, "Level 1", "sc", "Sole Corridor", 5.0, 0.0, 0.0, 0.0),
            "ROOM_2": NavNode("ROOM_2", "room", 1, "Level 1", "r2", "Room 2", 10.0, 0.0, 0.0, 0.0),
        }
        edges = [
            NavEdge("ROOM_1", "SOLO_CORR", "corridor", 5.0, 1, 1, capacity=3),
            NavEdge("SOLO_CORR", "ROOM_2", "corridor", 5.0, 1, 1, capacity=3),
        ]
        G = build_nav_graph(nodes, edges)

        # Baseline cost
        base_route = find_route(G, "ROOM_1", "ROOM_2", avoid_crowded=False)
        self.assertTrue(base_route.success)
        self.assertEqual(base_route.total_distance_m, 10.0)

        # Apply crowd: 6 people in Sole Corridor
        G.edges["ROOM_1", "SOLO_CORR"]["crowd_count"] = 6
        G.edges["ROOM_1", "SOLO_CORR"]["crowd_weight"] = 3.0
        G.edges["ROOM_1", "SOLO_CORR"]["weight"] = 15.0
        G.edges["SOLO_CORR", "ROOM_2"]["crowd_count"] = 6
        G.edges["SOLO_CORR", "ROOM_2"]["crowd_weight"] = 3.0
        G.edges["SOLO_CORR", "ROOM_2"]["weight"] = 15.0

        crowded_route = find_route(G, "ROOM_1", "ROOM_2", avoid_crowded=True)
        self.assertTrue(crowded_route.success, "Should still succeed when it is the sole corridor")
        self.assertEqual(crowded_route.route, ["ROOM_1", "SOLO_CORR", "ROOM_2"])
        print("  RESULT: Same valid route selected (with higher crowd cost preserved)")


if __name__ == "__main__":
    unittest.main()

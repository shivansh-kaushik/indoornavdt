"""Quick end-to-end test: build graph -> find route -> simulate crowd -> reroute."""
import sys; sys.path.insert(0, 'src')
import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s -- %(message)s')

import ifcopenshell
from build_graph import build_graph_from_ifc
from navigate import find_route, find_route_by_name, update_crowd_weights
from cctv_integration import (
    create_default_camera_config, map_cameras_to_graph, print_coverage_report
)
from crowd_detection import simulate_crowd_counts

# ── 1. Build graph ────────────────────────────────────────────────────────────
ifc = ifcopenshell.open('data/raw/Grethes-hus-bok-2.ifc')
G, nodes, edges = build_graph_from_ifc(ifc, output_dir='outputs')

# ── 2. List all nodes ─────────────────────────────────────────────────────────
print("\n--- All graph nodes ---")
for guid, data in G.nodes(data=True):
    print(f"  [{data.get('storey','?')}]  {data.get('name','?')}  ({data.get('ifc_type','')})")

# ── 3. Find a route (first space -> last space) ───────────────────────────────
guids = list(G.nodes)
if len(guids) >= 2:
    result = find_route(G, guids[0], guids[-1])
    print()
    result.print_summary()

# ── 4. CCTV setup ─────────────────────────────────────────────────────────────
cameras = create_default_camera_config(G, 'outputs/cameras.json', cameras_per_storey=2)
camera_node_map = map_cameras_to_graph(cameras, G)
print_coverage_report(cameras, camera_node_map, G)

# ── 5. Simulate crowd and re-route ────────────────────────────────────────────
crowd_counts = simulate_crowd_counts(camera_node_map, max_per_cam=8, seed=42)
update_crowd_weights(G, crowd_counts, camera_node_map)

print("\n--- Route with crowd avoidance ---")
if len(guids) >= 2:
    result2 = find_route(G, guids[0], guids[-1], avoid_crowded=True)
    result2.print_summary()
    result2.save_json('outputs/route_result.json')
    print("Route saved -> outputs/route_result.json")

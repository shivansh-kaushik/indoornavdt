"""
create_documentation_docx.py — Generates a comprehensive, professionally styled
DOCX document for the IndoorNav project.
"""

import os
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls

OUTPUT_DOCX_PATH = Path("docs/IndoorNav_System_Documentation.docx")
OUTPUT_DOCX_PATH.parent.mkdir(parents=True, exist_ok=True)

doc = docx.Document()

# ── Set Margins ─────────────────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)

# ── Color Palette ───────────────────────────────────────────────────────────
HEX_PRIMARY = "0B2545"      # Deep Navy
HEX_SECONDARY = "134074"    # Navy Accent
HEX_TEAL = "009688"         # Teal highlight
HEX_DARK = "1D2A44"         # Text dark
HEX_MUTED = "607D8B"        # Gray muted
HEX_BG_LIGHT = "F4F6F9"     # Table light bg
HEX_BORDER = "CFD8DC"       # Border gray

COLOR_PRIMARY = RGBColor(11, 37, 69)
COLOR_SECONDARY = RGBColor(19, 64, 116)
COLOR_DARK = RGBColor(29, 42, 68)
COLOR_MUTED = RGBColor(96, 125, 139)

# ── XML Shading & Border Helpers ───────────────────────────────────────────
def set_cell_background(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tc_pr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tc_pr.append(tc_mar)

def add_heading_1(text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(18)
    h.paragraph_format.space_after = Pt(6)
    h.paragraph_format.keep_with_next = True
    run = h.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = COLOR_PRIMARY
    return h

def add_heading_2(text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(14)
    h.paragraph_format.space_after = Pt(4)
    h.paragraph_format.keep_with_next = True
    run = h.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(13)
    run.font.bold = True
    run.font.color.rgb = COLOR_SECONDARY
    return h

def add_heading_3(text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(10)
    h.paragraph_format.space_after = Pt(2)
    h.paragraph_format.keep_with_next = True
    run = h.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.color.rgb = COLOR_DARK
    return h

def add_body(text, bold_prefix=None, space_after=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.font.name = "Arial"
        r_pre.font.size = Pt(10)
        r_pre.font.bold = True
        r_pre.font.color.rgb = COLOR_DARK
    r = p.add_run(text)
    r.font.name = "Arial"
    r.font.size = Pt(10)
    r.font.color.rgb = COLOR_DARK
    return p

def add_bullet(text, bold_prefix=None):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.font.name = "Arial"
        r_pre.font.size = Pt(10)
        r_pre.font.bold = True
        r_pre.font.color.rgb = COLOR_DARK
    r = p.add_run(text)
    r.font.name = "Arial"
    r.font.size = Pt(10)
    r.font.color.rgb = COLOR_DARK
    return p

def add_code_block(code_text):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, "F1F3F5")
    set_cell_margins(cell, top=100, bottom=100, left=150, right=150)
    
    # Border
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:left w:val="single" w:sz="24" w:space="0" w:color="{HEX_PRIMARY}"/><w:top w:val="none"/><w:right w:val="none"/><w:bottom w:val="none"/></w:tcBorders>')
    tc_pr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.05
    run = p.add_run(code_text)
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(33, 37, 41)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def add_callout(title, text):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, "EBF8FF")
    set_cell_margins(cell, top=120, bottom=120, left=180, right=180)
    
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:left w:val="single" w:sz="36" w:space="0" w:color="0284C7"/><w:top w:val="none"/><w:right w:val="none"/><w:bottom w:val="none"/></w:tcBorders>')
    tc_pr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(3)
    r_title = p.add_run(f"NOTE: {title}\n")
    r_title.font.name = "Arial"
    r_title.font.size = Pt(10)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(2, 132, 199)
    
    r_text = p.add_run(text)
    r_text.font.name = "Arial"
    r_text.font.size = Pt(9.5)
    r_text.font.color.rgb = COLOR_DARK
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def format_styled_table(tbl, col_widths, headers, data):
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_cells = tbl.rows[0].cells
    for i, title in enumerate(headers):
        hdr_cells[i].text = title
        set_cell_background(hdr_cells[i], HEX_PRIMARY)
        set_cell_margins(hdr_cells[i], top=120, bottom=120, left=140, right=140)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for r in p.runs:
            r.font.name = "Arial"
            r.font.size = Pt(9.5)
            r.font.bold = True
            r.font.color.rgb = RGBColor(255, 255, 255)

    for row_idx, row_data in enumerate(data):
        row_cells = tbl.add_row().cells
        bg_color = HEX_BG_LIGHT if row_idx % 2 == 1 else "FFFFFF"
        for i, val in enumerate(row_data):
            row_cells[i].text = str(val)
            set_cell_background(row_cells[i], bg_color)
            set_cell_margins(row_cells[i], top=90, bottom=90, left=140, right=140)
            p = row_cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for r in p.runs:
                r.font.name = "Arial"
                r.font.size = Pt(9)
                r.font.color.rgb = COLOR_DARK

    for row in tbl.rows:
        for i, w in enumerate(col_widths):
            row.cells[i].width = Inches(w)

# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENT CONTENT GENERATION
# ══════════════════════════════════════════════════════════════════════════════

# ── Title & Cover Block ───────────────────────────────────────────────────────
p_title = doc.add_paragraph()
p_title.paragraph_format.space_before = Pt(36)
p_title.paragraph_format.space_after = Pt(6)
r_title = p_title.add_run("IndoorNav: Physically Constrained Multi-Floor Indoor Navigation & 3D Building Digital Twin")
r_title.font.name = "Arial"
r_title.font.size = Pt(22)
r_title.font.bold = True
r_title.font.color.rgb = COLOR_PRIMARY

p_sub = doc.add_paragraph()
p_sub.paragraph_format.space_after = Pt(16)
r_sub = p_sub.add_run("Complete Technical Architecture, Physical Collision Constraints, Spatial Graph Extraction, Multi-Floor Routing, and Interactive Three.js Dashboard Documentation")
r_sub.font.name = "Arial"
r_sub.font.size = Pt(12)
r_sub.font.color.rgb = COLOR_MUTED

# Metadata table
meta_tbl = doc.add_table(rows=4, cols=2)
meta_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
meta_data = [
    ("Institution / Project:", "IIT Kharagpur — Digital Twin & Indoor Navigation Pipeline"),
    ("System Pipeline:", "Phase 1 (3D BIM Model Reconstruction) + Phase 2 (Physically Constrained Graph Navigation)"),
    ("Primary Technologies:", "Python (IfcOpenShell, Shapely, NetworkX, NumPy, Trimesh), Three.js WebGL, YOLOv8, OpenCV"),
    ("Date & Status:", "September 2026 — Phase 1 & 2 Fully Implemented, Verified, and Tested (8/8 Tests Passing)"),
]
for i, (k, v) in enumerate(meta_data):
    r_cells = meta_tbl.rows[i].cells
    r_cells[0].text = k
    r_cells[1].text = v
    set_cell_background(r_cells[0], "F8F9FA")
    set_cell_background(r_cells[1], "FFFFFF")
    set_cell_margins(r_cells[0], top=60, bottom=60, left=100, right=100)
    set_cell_margins(r_cells[1], top=60, bottom=60, left=100, right=100)
    r_cells[0].paragraphs[0].runs[0].font.bold = True
    r_cells[0].paragraphs[0].runs[0].font.size = Pt(9)
    r_cells[1].paragraphs[0].runs[0].font.size = Pt(9)
    r_cells[0].width = Inches(2.0)
    r_cells[1].width = Inches(4.5)

doc.add_page_break()

# ── 1. Executive Summary & Problem Formulation ──────────────────────────────
add_heading_1("1. Executive Summary & Problem Formulation")

add_body(
    "Standard Global Positioning System (GPS) signals are rapidly attenuated and scattered by building materials (concrete, steel, and masonry), rendering outdoor satellite navigation completely ineffectual inside multi-storey structures. Indoor navigation requires high-precision topological and geometric representations of the interior architectural environment. Building Information Modeling (BIM), specifically standardized through Industry Foundation Classes (IFC), encapsulates the definitive geometry, semantics, and relationships of architectural spaces, structural walls, doorway portals, and vertical circulation shafts."
)

add_body(
    "The IndoorNav system bridges the gap between raw BIM architectural files and real-time indoor wayfinding. It ingests IFC files, performs 3D geometry and spatial extraction, enforces rigorous physical wall barrier constraints, samples walkable corridor networks, connects multi-floor stairwells and elevators, dynamically re-weights routes based on live CCTV camera crowd feeds, and renders interactive 3D navigation paths inside a WebGL/Three.js building viewer."
)

add_callout(
    "The Fundamental Physical Invariant",
    "A user may move only through explicitly defined navigation nodes and physically valid connections. Walls are absolute physical barriers. Doors and gates are explicit horizontal passage points. Stairs and elevators are explicit vertical passage points between storeys. No shortcuts or wall-crossings are permitted under any geometric condition."
)

# ── 2. System Architecture ──────────────────────────────────────────────────
add_heading_1("2. End-to-End System Architecture")

add_body(
    "The IndoorNav pipeline is architected into two seamlessly integrated layers: Phase 1 (BIM Parsing, 3D Reconstruction, and Export) and Phase 2 (Physically Constrained Spatial Graph Building, Dynamic Pathfinding, CCTV AI Crowd Ingestion, and Interactive Dashboard)."
)

add_heading_2("2.1 Module Structure & Responsibilities")

arch_headers = ["Module Path", "Layer", "Primary Purpose / Output"]
arch_data = [
    ("src/load_ifc.py", "Phase 1", "Loads and validates IFC files via IfcOpenShell; detects schema (IFC2X3/IFC4) and extracts project hierarchy."),
    ("src/extract_geometry.py", "Phase 1", "Extracts triangulated 3D mesh vertices and faces in world coordinates; organizes elements into a storey-keyed scene graph."),
    ("src/export_model.py", "Phase 1", "Transforms Z-up IFC geometry to standard Y-up convention; exports model.obj, model.glb, and lightweight elements.json."),
    ("src/visualize.py", "Phase 1", "PyVista/VTK off-screen rendering engine generating automated color-coded render.png screenshots."),
    ("src/navigation/collision.py", "Phase 2", "Extracts 2D wall boundary footprints, subtracts door openings, and builds Shapely STRtree spatial indices for collision testing."),
    ("src/navigation/route_validator.py", "Phase 2", "Validates candidate graphs for physical constraint violations, wall penetrations, and invalid floor transitions."),
    ("src/build_graph.py", "Phase 2", "Generates explicit multi-floor navigation nodes, samples corridor walking networks, links doors and stairs, exports nav_graph.json."),
    ("src/navigate.py", "Phase 2", "Multi-floor A* and Dijkstra pathfinding engine with dynamic crowd weight penalties and turn-by-turn guidance."),
    ("src/cctv_integration.py", "Phase 2", "Registers physical CCTV cameras in 3D world space, calculates field-of-view viewing cones, and maps cameras to graph nodes."),
    ("src/crowd_detection.py", "Phase 2", "Computer vision pipeline (YOLOv8 nano / OpenCV HOG) providing real-time person counts per camera feed."),
    ("src/main.py", "CLI", "Main command-line orchestrator linking stages 1 through 6 with the --build-nav flag."),
    ("dashboard/index.html", "Frontend", "Single-file Three.js web application with 3D model loading, graph layer debug toggles, route visualization, collision-safe walk mode, and graph editor."),
    ("tests/test_navigation.py", "Verification", "Automated test suite verifying all 8 required navigation, collision, multi-floor, and crowd rerouting scenarios.")
]
tbl_arch = doc.add_table(rows=1, cols=3)
format_styled_table(tbl_arch, [1.6, 0.9, 4.0], arch_headers, arch_data)

# ── 3. Coordinate Conventions & Geometric Transformation ─────────────────────
add_heading_1("3. Coordinate Systems & Mathematical Conventions")

add_body(
    "A critical architectural requirement in multi-disciplinary BIM systems is absolute coordinate consistency across the pipeline: raw IFC files, extracted numpy meshes, exported WebGL GLB/OBJ models, NetworkX graph nodes, and the Three.js viewport must remain aligned."
)

add_bullet("IFC Coordinate System: Follows the civil/architectural standard of Z-up coordinates (X = East/Length, Y = North/Width, Z = Elevation). All vertices extracted by ifcopenshell.geom.create_shape() with USE_WORLD_COORDS=True are preserved in this system.")
add_bullet("Graphics / WebGL Standard: WebGL, Three.js, and glTF standards mandate Y-up coordinates (X = Right, Y = Elevation/Up, Z = Depth).")
add_bullet("Forward Transformation (IFC → GLB/OBJ): Applied during export in export_model.py: X_glb = X_ifc, Y_glb = Z_ifc, Z_glb = -Y_ifc.")
add_bullet("Dashboard Scene Centering: In Three.js, models are centered on the ground plane at (-center_X, -box_min_Y, -center_Z).")
add_bullet("Navigation Node Projection: To position an IFC navigation node (x, y, z) into the 3D scene without coordinate drift: X_scene = x + modelGroup.position.x, Y_scene = z + modelGroup.position.y, Z_scene = -y + modelGroup.position.z.")

# ── 4. Physical Wall Collision & Geometry Layer ──────────────────────────────
add_heading_1("4. Physical Wall Collision & Spatial Layer")

add_body(
    "To satisfy the non-negotiable requirement that walls must never be traversable, src/navigation/collision.py introduces a physical boundary extraction and collision detection engine."
)

add_heading_2("4.1 2D Planar Footprint Extraction from 3D IFC Meshes")
add_body(
    "Architectural indoor navigation is fundamentally multi-storey 2D planar navigation interconnected by vertical portals. For each wall entity (IfcWall and IfcWallStandardCase), the 3D mesh is extracted and its triangular faces are projected onto the horizontal XY plane. The exact boundary footprint of the wall is constructed by taking the geometric unary union of the projected 2D triangles:"
)
add_code_block("""# Construction of exact 2D wall footprint polygon
triangles = [Polygon([verts[face[0]][:2], verts[face[1]][:2], verts[face[2]][:2]]) for face in faces]
wall_footprint = shapely.ops.unary_union(triangles)
""")

add_heading_2("4.2 Construction of Solid Wall Boundaries")
add_body(
    "Because doorway openings represent valid physical passages, doors (IfcDoor and IfcOpeningElement) on the same storey have their aperture footprints calculated. The traversable solid wall geometry is defined mathematically as:"
)
add_code_block("""# Solid wall geometry excludes authorized door openings
SolidWall = WallFootprint.difference(DoorAperturesUnion)
""")

add_heading_2("4.3 Segment Raycasting & Penetration Testing")
add_body(
    "For every candidate edge proposed between node P1 and node P2, a LineString segment is tested against the solid wall STRtree spatial index. If the segment intersects the solid wall polygon with a penetration depth exceeding the tolerance (0.08m), the candidate edge is rejected immediately at graph generation time:"
)
add_code_block("""def check_segment_collision(self, p1, p2, storey, penetration_tolerance_m=0.08) -> bool:
    seg_line = LineString([(p1[0], p1[1]), (p2[0], p2[1])])
    candidate_indices = self.wall_trees[storey].query(seg_line)
    for idx in candidate_indices:
        solid_poly = self.tree_wall_maps[storey][idx].solid_polygon
        inter = seg_line.intersection(solid_poly)
        if inter.length > penetration_tolerance_m:
            return True  # COLLISION DETECTED (BLOCKED)
    return False # CLEAR (PASS)
""")

# ── 5. Multi-Floor Navigation Graph Modeling ─────────────────────────────────
add_heading_1("5. Multi-Floor Navigation Graph Modeling")

add_body(
    "The upgraded src/build_graph.py transforms the building model into an explicit, multi-floor topological graph where rooms, corridors, doors, and stairs are distinct node entities."
)

add_heading_2("5.1 Explicit Node Schema & Taxonomy")
add_body("Every navigation node contains full spatial and level metadata:")
add_code_block("""{
  "id": "node_0BTBFw_01",
  "type": "corridor",
  "floor": 1,
  "storey_id": "Level 1",
  "space_id": "0BTBFw9p907x1G5lCpt19a",
  "name": "Corridor A (W1)",
  "x": 6.42,
  "y": -8.15,
  "z": 0.10,
  "elevation": 0.0,
  "clearance_m": 0.30
}
""")

add_body("Supported Node Types:", bold_prefix="Node Taxonomy: ")
add_bullet("room: Represents room centroids or representative interior points.", bold_prefix="Room Nodes: ")
add_bullet("corridor / walk: Intermediate walking grid nodes sampled across corridors and lobbies at 1.5m intervals.", bold_prefix="Walking Nodes: ")
add_bullet("door / gate: Explicit doorway threshold nodes placed at physical openings.", bold_prefix="Portal Nodes: ")
add_bullet("stair: Linked bottom and top landing nodes representing vertical stair flights.", bold_prefix="Stair Landings: ")
add_bullet("elevator: Elevator car and shaft nodes servicing discrete floors.", bold_prefix="Elevator Nodes: ")
add_bullet("junction: Branching convergence points in corridors and hall intersections.", bold_prefix="Junction Nodes: ")

add_heading_2("5.2 Intermediate Walkable Node Generation in Corridors")
add_body(
    "Rather than relying on isolated space centroids, corridors and large open spaces have their 2D footprints buffered inward by a wall clearance margin (0.30m). A 2D regular grid with configurable spacing (default: 1.5m) is sampled across the interior. Grid points within the buffered polygon that do not collide with walls are instantiated as walking nodes, connected to their immediate neighbors via unobstructed lines of sight."
)

add_heading_2("5.3 Explicit Door Portals & Topological Integrity")
add_body(
    "A direct connection between Room A and Room B is strictly prohibited. If Room A and Room B share a doorway, the graph must form the exact sequence: ROOM A <--> DOOR 1 <--> CORRIDOR <--> DOOR 2 <--> ROOM B. Door nodes only link to candidate spaces located on the same storey and within 1.8m vertical elevation."
)

add_heading_2("5.4 Multi-Floor Vertical Circulation")
add_body(
    "Direct connections between different storeys based on XY proximity are completely barred. For every IfcStairFlight or IfcStair entity, two landing nodes are generated: a bottom landing node on the lower floor, and a top landing node on the upper floor. A vertical edge of type 'stair' (accessible: false) connects the bottom landing to the top landing. Each landing then connects to the nearest reachable corridor or space node on its own floor."
)

# ── 6. Dynamic Routing Engine & CCTV Crowd AI ────────────────────────────────
add_heading_1("6. Dynamic Routing Engine & CCTV Crowd Integration")

add_body(
    "The upgraded src/navigate.py provides multi-floor A* and Dijkstra pathfinding operating directly on the physically constrained graph."
)

add_heading_2("6.1 Admissible 3D A* Heuristic")
add_body(
    "To guarantee optimal route selection across storeys, the A* search uses an admissible 3D Euclidean distance heuristic augmented with a storey-transition penalty:"
)
add_code_block("""def heuristic(u, target):
    euclidean_3d = sqrt((u.x - target.x)**2 + (u.y - target.y)**2 + (u.z - target.z)**2)
    floor_penalty = abs(u.floor - target.floor) * 3.5
    return euclidean_3d + floor_penalty
""")

add_heading_2("6.2 Dynamic CCTV Crowd Weight Formula")
add_body(
    "Physical CCTV cameras registered in src/cctv_integration.py map viewing frustum cones onto graph nodes. When src/crowd_detection.py detects occupants (via YOLOv8 nano or OpenCV HOG), the person count updates edge costs dynamically without violating physical barriers:"
)
add_code_block("""weight = distance_m * (1.0 + (crowd_count / max(capacity, 1)))
""")
add_body(
    "If a corridor is congested, its weight multiplier increases proportionally. The A* algorithm automatically redirects navigators through clear alternative corridors. If only one corridor exists, the algorithm retains the valid route but accurately reflects the increased travel time."
)

add_heading_2("6.3 Structured Navigation Output")
add_body("Routing results are returned in a comprehensive JSON schema including turn-by-turn guidance and floor transitions:")
add_code_block("""{
  "success": true,
  "start": "node_1gY9E27$",
  "destination": "stair_top_19RA9P",
  "distance_m": 6.5,
  "estimated_time_s": 5.4,
  "route": [
    "node_1gY9E27$",
    "walk_1gY9E2_06",
    "walk_1gY9E2_08",
    "stair_bot_19RA9P",
    "stair_top_19RA9P"
  ],
  "floor_transitions": [
    {
      "from": 2,
      "to": 3,
      "type": "stair",
      "via_node": "stair_top_19RA9P",
      "distance_m": 2.12
    }
  ]
}
""")

# ── 7. Three.js 3D Dashboard & Virtual Walk Mode ─────────────────────────────
add_heading_1("7. Interactive Three.js Dashboard & Virtual Walk Mode")

add_body(
    "The client-side dashboard in dashboard/index.html has been upgraded into a full-featured 3D building viewer, route planner, collision-constrained walkthrough simulator, and graph authoring editor."
)

add_heading_2("7.1 3D Graph Visualization & Node Taxonomy")
add_body("Navigation nodes are rendered with distinct geometric markers and color coding:")
add_bullet("Corridor & Walking Nodes: Cyan spheres (radius 0.22m, color #00C8FF)", bold_prefix="Corridors: ")
add_bullet("Room Centroid Nodes: Blue cubes (0.35m box, color #3B82F6)", bold_prefix="Rooms: ")
add_bullet("Door & Gate Portals: Orange tori / rings (outer radius 0.26m, color #F97316)", bold_prefix="Doors: ")
add_bullet("Stair Landing Nodes: Yellow 4-sided pyramids / wedges (height 0.45m, color #EAB308)", bold_prefix="Stairs: ")
add_bullet("Elevator Nodes: Purple vertical cylinders (height 0.50m, color #A855F7)", bold_prefix="Elevators: ")
add_bullet("Junction Nodes: Amber octahedrons (radius 0.25m, color #F59E0B)", bold_prefix="Junctions: ")

add_heading_2("7.2 Constrained Virtual Walk Mode with Wall Collision")
add_body(
    "The first-person Walk Mode (WASD keyboard + mouse look) now enforces physical wall collision detection. Before moving the camera by the velocity vector (move), a raycast sweep of distance move.length() + AVATAR_RADIUS (0.35m) is tested against all wall meshes in the scene. If an obstruction is detected, motion along the surface normal is clamped to zero, a floating warning badge ('WALL COLLISION — MOVEMENT BLOCKED') is displayed, and avatar wall-clipping is completely prevented."
)

add_heading_2("7.3 Automated 'Follow Route' Mode")
add_body(
    "When a route is computed, the user can click 'Follow Route (Auto-Walk)'. The virtual camera smoothly animates along the calculated 3D path at walking speed (1.2 m/s). An on-screen HUD displays turn-by-turn directions ('Pass through Door 1', 'Ascend stairs to Floor 2'), current floor, and remaining distance."
)

add_heading_2("7.4 In-Browser Graph Authoring Editor")
add_body(
    "A dedicated Graph Authoring Editor allows users to click on any 3D model surface to place new nodes, select pairs of nodes to connect with walking, door, or stair edges, delete incorrect nodes, and click 'Save navigation_graph.json' to download an updated graph."
)

# ── 8. Verification & Automated Test Suite ───────────────────────────────────
add_heading_1("8. Verification & Automated Test Suite")

add_body(
    "To rigorously certify that all physical constraints, routing rules, and crowd rerouting behaviors are strictly satisfied, tests/test_navigation.py implements an automated test suite covering all 8 required verification scenarios."
)

test_headers = ["Test ID", "Scenario Description", "Expected Behavior", "Automated Result"]
test_data = [
    ("Test 1", "Room A to Room B through valid doorway", "Path proceeds via door node; distance ~6.0m", "PASS (Route found via Door 1)"),
    ("Test 2", "Room A to Room B separated by solid wall without door", "Raycast intercepts wall; edge rejected; no route", "PASS (Blocked by wall barrier: NO ROUTE)"),
    ("Test 3", "Floor 1 to Floor 2 using stairs", "Path traverses bottom landing to top landing", "PASS (Stair transition Floor 1 -> Floor 2)"),
    ("Test 4", "Floor 1 to Floor 2 with no stair/elevator", "Disallowed vertical leap; graph disconnected", "PASS (Floors disconnected: NO ROUTE)"),
    ("Test 5", "Floor 1 to Floor 3 using elevator", "Path traverses elevator shaft nodes vertically", "PASS (Elevator transition Floor 1 -> Floor 3)"),
    ("Test 6", "Virtual avatar movement directly into wall", "Raycaster flags collision; movement clamped", "PASS (MOVEMENT BLOCKED)"),
    ("Test 7", "Crowded corridor with alternative route", "North corridor penalized; South chosen", "PASS (Alternative lower-cost route selected)"),
    ("Test 8", "Crowded corridor when only single corridor exists", "Sole corridor retained with increased crowd cost", "PASS (Same valid route selected with crowd cost)")
]
tbl_test = doc.add_table(rows=1, cols=4)
format_styled_table(tbl_test, [0.8, 2.2, 2.2, 1.8], test_headers, test_data)

# ── 9. Generated Artifacts & File Reference ──────────────────────────────────
add_heading_1("9. Generated Artifacts & Output Reference")

add_body("Running the pipeline generates the following outputs in the outputs/ directory:")

out_headers = ["File Name", "Format", "Contents & Purpose"]
out_data = [
    ("model.obj", "Wavefront OBJ", "Triangulated 3D mesh grouped by storey and IFC element type; Y-up orientation."),
    ("model.glb", "Binary glTF", "Optimized WebGL 3D model with per-element vertex colors matching IFC palettes."),
    ("elements.json", "JSON Index", "Lightweight linkage layer mapping GUID -> {ifc_type, storey, bbox} without mesh data."),
    ("render.png", "PNG Image", "High-resolution off-screen PyVista visualization screenshot of the building."),
    ("nav_graph.json", "JSON Graph", "Complete NetworkX navigation graph serialization with node coordinates, storeys, and edges."),
    ("nav_graph.gexf", "GEXF XML", "Gephi-compatible graph format for topological analysis and external graph viewers."),
    ("navigation_nodes.json", "JSON Array", "Dedicated array of all extracted navigation nodes with explicit IDs, floors, and XYZ coords."),
    ("navigation_edges.json", "JSON Array", "Dedicated array of all physically-validated walking, door, and vertical edges."),
    ("navigation_validation.json", "JSON Diagnostics", "Comprehensive validation report detailing wall collision tests and connectivity metrics.")
]
tbl_out = doc.add_table(rows=1, cols=3)
format_styled_table(tbl_out, [1.8, 1.2, 4.0], out_headers, out_data)

# ── 10. CLI Reference & Quick Start Guide ────────────────────────────────────
add_heading_1("10. User Guide & CLI Quick Start")

add_body("To execute the full pipeline from raw IFC to 3D models and navigation graph:")
add_code_block("""# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the end-to-end pipeline on an IFC model with navigation graph generation
python src/main.py --input data/raw/Grethes-hus-bok-2.ifc --no-display --build-nav

# 3. Run the automated 8-scenario navigation test suite
python tests/test_navigation.py

# 4. View in 3D Browser Dashboard
# Double-click dashboard/index.html in any browser.
# Drag and drop outputs/model.glb onto the window.
# Click 'Load Graph' to load outputs/nav_graph.json, calculate routes, and test Walk Mode.
""")

# Save document
doc.save(str(OUTPUT_DOCX_PATH))
print(f"Documentation generated successfully at: {OUTPUT_DOCX_PATH.resolve()}")

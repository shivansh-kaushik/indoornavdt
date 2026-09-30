"""Debug: understand why spaces are Unassigned and how far doors are from spaces."""
import sys; sys.path.insert(0, 'src')
import ifcopenshell, ifcopenshell.geom
import numpy as np

ifc = ifcopenshell.open('data/raw/Grethes-hus-bok-2.ifc')
settings = ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)

# Find what contains the spaces
spaces = ifc.by_type('IfcSpace')
print("=== SPACE CONTAINERS ===")
for s in spaces[:4]:
    # walk up the decomposition tree
    for rel in ifc.by_type('IfcRelContainedInSpatialStructure'):
        if s in rel.RelatedElements:
            print(f"  Space {s.Name} -> container {rel.RelatingStructure.is_a()} '{rel.RelatingStructure.Name}'")

    for rel in ifc.by_type('IfcRelAggregates'):
        for part in rel.RelatedObjects:
            if part == s:
                print(f"  Space {s.Name} -> aggregate of {rel.RelatingObject.is_a()} '{rel.RelatingObject.Name}'")

# Centroid of spaces
print("\n=== SPACE CENTROIDS ===")
for s in spaces[:4]:
    try:
        shape = ifcopenshell.geom.create_shape(settings, s)
        verts = np.array(shape.geometry.verts).reshape(-1,3)
        c = verts.mean(axis=0)
        print(f"  Space {s.Name}: centroid=({c[0]:.1f}, {c[1]:.1f}, {c[2]:.1f})")
    except Exception as e:
        print(f"  Space {s.Name}: NO GEOMETRY ({e})")

# Centroid of doors  
print("\n=== DOOR CENTROIDS ===")
doors = ifc.by_type('IfcDoor')
for d in doors[:6]:
    try:
        shape = ifcopenshell.geom.create_shape(settings, d)
        verts = np.array(shape.geometry.verts).reshape(-1,3)
        c = verts.mean(axis=0)
        print(f"  Door {d.Name}: centroid=({c[0]:.1f}, {c[1]:.1f}, {c[2]:.1f})")
    except Exception as e:
        print(f"  Door {d.Name}: NO GEOMETRY ({e})")

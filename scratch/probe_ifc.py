import sys; sys.path.insert(0, 'src')
import ifcopenshell
from ifcopenshell.util.element import get_container

ifc = ifcopenshell.open('data/raw/Grethes-hus-bok-2.ifc')

spaces = ifc.by_type('IfcSpace')
doors  = ifc.by_type('IfcDoor')
stairs = ifc.by_type('IfcStair') + ifc.by_type('IfcStairFlight')
rels   = ifc.by_type('IfcRelSpaceBoundary')

print(f'IfcSpace        : {len(spaces)}')
print(f'IfcDoor         : {len(doors)}')
print(f'IfcStair+Flight : {len(stairs)}')
print(f'SpaceBoundary   : {len(rels)}')

print('\n--- First 3 spaces ---')
for s in spaces[:3]:
    c = get_container(s)
    print(f'  {s.GlobalId[:14]}  name={s.Name}  storey={c.Name if c else None}')

print('\n--- First 3 doors ---')
for d in doors[:3]:
    c = get_container(d)
    print(f'  {d.GlobalId[:14]}  name={d.Name}  storey={c.Name if c else None}')

if rels:
    print('\n--- First SpaceBoundary ---')
    r = rels[0]
    rs = getattr(r, 'RelatingSpace', None)
    rb = getattr(r, 'RelatedBuildingElement', None)
    print(f'  RelatingSpace  : {rs.Name if rs else None}')
    print(f'  RelatedElement : {rb.is_a() if rb else None}')
else:
    print('\nNo IfcRelSpaceBoundary -- will use proximity method')

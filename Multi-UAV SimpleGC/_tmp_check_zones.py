import json, pathlib
pilot = pathlib.Path('F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_p1_20261014T093058Z_5860b099')
scene_file = next(pilot.rglob('public_scene.json'))
s = json.loads(scene_file.read_text())
fac = next(e for e in s['entities'] if e['type'] == 'facility')
print('facility geometry:', fac['geometry']['type'])
if fac['geometry']['type'] == 'Circle':
    print('  radius_m:', fac['geometry'].get('radius_m', 'N/A'))
zones = {e['layer']: e for e in s['entities'] if e.get('facility_id') == fac['id'] and 'layer' in e}
for name, z in sorted(zones.items()):
    print(f"  {name}: offset_m={z['offset_m']}  geom_radius={z['geometry'].get('radius_m','N/A')}")

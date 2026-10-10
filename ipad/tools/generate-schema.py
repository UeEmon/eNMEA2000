"""Extract declarative AIS layouts from the MIT-licensed pyais v3.2.3 messages.py.
Run: python3 ipad/tools/generate-schema.py /path/to/messages.py
No upstream Python code is executed. Corrected binary layouts live in AIS.swift.
"""
import ast, json, sys
from pathlib import Path
classes = {n.name: n for n in ast.parse(Path(sys.argv[1]).read_text()).body if isinstance(n, ast.ClassDef)}
def fields(name):
    node = classes[name]
    result = []
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id.startswith('MessageType'):
            result += fields(base.id)
    for a in node.body:
        if not isinstance(a, ast.Assign) or not isinstance(a.value, ast.Call): continue
        c = a.value
        if not isinstance(c.func, ast.Name) or c.func.id != 'bit_field': continue
        opts = {k.arg: k.value for k in c.keywords}
        f = dict(name=a.targets[0].id, width=ast.literal_eval(c.args[0]), kind=c.args[1].id,
                 signed=ast.literal_eval(opts.get('signed', ast.Constant(False))),
                 variable=ast.literal_eval(opts.get('variable_length', ast.Constant(False))),
                 spare=ast.literal_eval(opts.get('is_spare', ast.Constant(False))),
                 converter=getattr(opts.get('to_converter'), 'id', ''))
        if f['name'] in [v['name'] for v in result]: result[[v['name'] for v in result].index(f['name'])] = f
        else: result.append(f)
    offset = 0
    for f in result:
        f['offset'] = offset; offset += f['width']
        if name in ('MessageType17','MessageType22Broadcast','MessageType23') and f['name'] in ('lon','lat','ne_lon','ne_lat','sw_lon','sw_lat'):
            f['signed'] = True; f['converter'] = 'to_lat_lon_600'
    return result
names = ['MessageType' + str(t) for t in range(1,29) if t not in (8,16,22,24,25,26)] + ['MessageType8Default','MessageType16DestinationA','MessageType16DestinationAB','MessageType22Addressed','MessageType22Broadcast','MessageType24PartA','MessageType24PartB','MessageType24PartBAuxiliaryCraft']
output = Path(__file__).resolve().parents[1] / 'Sources/NMEACore/Resources/ais-schema.json'
output.write_text(json.dumps({name: fields(name) for name in names}, ensure_ascii=False, indent=2) + '\n')
print(f'{len(names)} AIS layouts generated')

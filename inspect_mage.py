import urllib.request
import json
import sys

url = 'https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/image_mage_flow_edit_int8.json'
req = urllib.request.urlopen(url)
data = json.loads(req.read().decode('utf-8'))

print('=== Top nodes ===')
for n in data.get('nodes', []):
    print(n.get('id'), n.get('type'), n.get('title'))

defs = data.get('definitions', {}).get('subgraphs', [])
for sg in defs:
    print('=== Subgraph:', sg.get('name'), '===')
    for sn in sg.get('nodes', []):
        print('  ', sn.get('id'), sn.get('type'), sn.get('title'), 'inputs:', [i.get('name') for i in sn.get('inputs', [])], 'widgets:', sn.get('widgets_values'))

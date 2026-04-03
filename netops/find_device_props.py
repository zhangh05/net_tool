#!/usr/bin/env python3
with open('/root/nettool/netops/index.html', 'r') as f:
    content = f.read()

idx = content.find('function showProps')
print(f"showProps at: {idx}")

# Find the structure of showProps
searches = [
    "d.isShape",
    "d.isTextBox",
    "nodes && !d",
    "nodes && d.type",
    "ele.group() === 'nodes' && !d",
]

for pattern in searches:
    pos = content.find(pattern, idx)
    if pos > 0 and pos < idx + 60000:
        print(f"Found '{pattern}' at {pos}:")
        print(repr(content[pos-30:pos+100]))
        print()

# Also find what's at 92319 (the p-ip we found earlier)
print("Context around p-ip (92319):")
print(repr(content[91800:92900]))

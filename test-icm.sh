#!/bin/bash
echo "=== ICM Agentic Loop Test ==="

for f in agentic_loop.py extractor.py sprockets_graph_builder.py cogs_updater.py input_processor.py; do
    if [ ! -f "$f" ]; then
        echo "❌ Missing $f"
        exit 1
    else
        echo "✅ Found $f ($(wc -c < "$f") bytes)"
    fi
done

mkdir -p Artifacts/Input
cat > Artifacts/Input/test_voice.json << 'JSON'
{"timestamp":"2026-04-06T15:00:00","source":"voice","raw_text":"Create a new goal called Finish Second Brain and a task to test the agentic loop today."}
JSON

echo "✅ Test input created"

echo "Service status:"
sudo systemctl is-active icm-agent && echo "✅ icm-agent is running" || echo "❌ icm-agent is NOT running"

echo ""
echo "=== Test complete. Check Obsidian for new Sprockets/Cogs files. ==="

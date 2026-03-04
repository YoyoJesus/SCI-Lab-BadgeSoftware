# Real-Time Labeling

Live badge data collection combined with real-time speaker detection — auto-labeling while you collect.

## Files

| File | Purpose |
|------|---------|
| `live_collection_graph.py` | **Main app** — scans for BLE badges, collects data, labels in real-time, shows live graph with active speaker |
| `realtime_labeler.py` | Streaming auto-labeling engine (same algorithm as `auto_label.py` but works on live data) |
| `demo_replay.py` | Test mode — replays an existing CSV through the labeler + graph without needing live badges |

## Quick Start

### Live collection (with badges)
```
cd "Real-Time Labeling"
python live_collection_graph.py
```

### Demo / test mode (replay a CSV)
```
cd "Real-Time Labeling"
python demo_replay.py
```

## Requirements
```
pip install bleak matplotlib numpy
```

## What It Shows

- **Left panel**: Active speaker name displayed prominently, plus all badges with their status (speaking / silent) and speech score
- **Right panel**: Live sound + acceleration graphs, active speaker highlighted with thicker lines and background shading
- **CSV output**: Saved to `badge_data/` with an extra `RT_Label` column for the real-time label

## How It Works

The `RealtimeLabeler` maintains rolling buffers of recent data per badge and continuously runs the same peak-comparison algorithm used in the batch auto-labeler:

1. Per-badge IQR normalization of sound and acceleration
2. Combined speech score (sound + weighted acceleration)
3. Per-bin winner selection
4. Sliding window majority vote to smooth results

The active speaker is updated every 500ms time bin.

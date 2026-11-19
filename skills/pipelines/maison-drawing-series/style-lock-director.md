# Style-Lock Director

Build the **style-lock sheet**: `image_crop` montage of every plate beside plate No. 1, labelled.
Check line weight, palette, paper tone and density against No. 1 (look at it yourself; the local vision
model can rate "same hand 1-5" per pair). A plate that drifts is re-made, never silently kept; the drift
version moves to `components/`. Write `quality_gate` with the sheet path.

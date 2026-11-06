# MyPC Attendance — P02-HF1 shared AI budget + frame identity

**Baseline (P02 / PR #22 tip):** `d0a6b3cf3c974e6ac953db16efce5393e3d4cbd2`  
**Branch:** `cursor/p02-hf1-ai-budget-83a8`  
**Download:** `MYPC-P02-HF1-COMPLETE-AUDIT.zip`

Fixes: (1) per-camera monotonic AI budget across distinct frame_ids; (2) never return/label another frame’s boxes/pixels as the current frame. Detection+quality only.

**Do not merge to main. Physical gates remain BLOCKED.**

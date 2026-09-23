# Palette verification — the study's samples re-measured

Source: `assets/references/handdrawn/work/study/image-measurements.json` (companion to forensic-illustration-study.md).
Frames re-read from `assets/references/handdrawn/work/anchors` at the study's own `box_xyxy` boxes.

**35 of 35 samples reproduce within 3 levels per channel.** 0 flagged, 0 anchors unavailable.

A flagged row means the playbook must not quote that value as measured.
The `luma sd` column is the study's value against the re-measured one; it uses the
study's definition (arithmetic channel mean, not calibrated luminance).

| Anchor | Frame : region | Study hex | Re-measured | Max channel delta | luma sd study / now | Result |
|---|---|---|---|---|---|---|
| A1 | `video1_frame_0198.png:paper` | #E7D6BE | #E7D6BE | 0 | 2.254 / 2.254 | match |
| A1 | `video1_frame_0198.png:sweater` | #B3978A | #B3978A | 0 | 1.467 / 1.467 | match |
| A1 | `video1_frame_0198.png:trousers` | #6C6766 | #6C6766 | 0 | 2.082 / 2.082 | match |
| A1 | `video1_frame_0198.png:skin` | #E6C5AF | #E6C5AF | 0 | 31.617 / 31.617 | match |
| A2 | `video1_frame_1973.png:paper` | #E5DBDB | #E5DBDB | 0 | 1.910 / 1.910 | match |
| A2 | `video1_frame_1973.png:teal_jacket` | #4C6771 | #4C6771 | 0 | 25.279 / 25.279 | match |
| A2 | `video1_frame_1973.png:red_jacket` | #E8E4E0 | #E8E4E0 | 0 | 67.491 / 67.491 | match |
| A2 | `video1_frame_1973.png:purple_skirt` | #594154 | #594154 | 0 | 2.513 / 2.513 | match |
| A3 | `video1_frame_2828.png:hair` | #7E7E7E | #7E7E7E | 0 | 8.819 / 8.819 | match |
| A3 | `video1_frame_2828.png:shirt` | #181818 | #181818 | 0 | 5.234 / 5.234 | match |
| A3 | `video1_frame_2828.png:skin` | #F9E1D1 | #F9E1D1 | 0 | 27.440 / 27.440 | match |
| B1 | `video2_frame_0001.png:black_figure` | #000000 | #000000 | 0 | 0.034 / 0.034 | match |
| B1 | `video2_frame_0001.png:sky` | #CBECCF | #CBECCF | 0 | 3.240 / 3.240 | match |
| B1 | `video2_frame_0001.png:ground` | #73433E | #73433E | 0 | 10.714 / 10.714 | match |
| B2 | `video2_frame_0012.png:orange_jug` | #E48529 | #E48529 | 0 | 16.535 / 16.535 | match |
| B2 | `video2_frame_0012.png:red_meat` | #7B0000 | #7B0000 | 0 | 0.000 / 0.000 | match |
| B2 | `video2_frame_0012.png:black_head` | #000000 | #000000 | 0 | 53.912 / 53.912 | match |
| B3 | `video2_frame_0023.png:sky` | #D3EBDB | #D3EBDB | 0 | 3.764 / 3.764 | match |
| B3 | `video2_frame_0023.png:green_plain` | #57905A | #57905A | 0 | 7.698 / 7.698 | match |
| B3 | `video2_frame_0023.png:hill` | #3B7673 | #3B7673 | 0 | 15.934 / 15.934 | match |
| C1 | `video3_frame_0049.png:sky` | #94C0B9 | #94C0B9 | 0 | 5.771 / 5.771 | match |
| C1 | `video3_frame_0049.png:water` | #69A2A1 | #69A2A1 | 0 | 6.716 / 6.716 | match |
| C1 | `video3_frame_0049.png:trunk` | #1E4146 | #1E4146 | 0 | 0.410 / 0.410 | match |
| C1 | `video3_frame_0049.png:olive` | #5D5E1E | #5D5E1E | 0 | 1.086 / 1.086 | match |
| C2 | `video3_frame_0145.png:orange` | #D74300 | #D74300 | 0 | 55.613 / 55.613 | match |
| C2 | `video3_frame_0145.png:leaf` | #5E8678 | #5E8677 | 1 | 67.376 / 67.376 | match |
| C2 | `video3_frame_0145.png:pale_ground` | #D6E1E0 | #D6E1E0 | 0 | 2.485 / 2.485 | match |
| C3 | `video3_frame_0205.png:blue_field` | #416C7B | #416C7B | 0 | 0.613 / 0.613 | match |
| C3 | `video3_frame_0205.png:cream_disc` | #DADFC9 | #DADFC9 | 0 | 46.749 / 46.749 | match |
| C3 | `video3_frame_0205.png:green_icon` | #34624D | #34624D | 0 | 0.730 / 0.730 | match |
| C4 | `video3_frame_0302.png:skin` | #E9783C | #E9783C | 0 | 0.194 / 0.194 | match |
| C4 | `video3_frame_0302.png:nose` | #ED6134 | #ED6134 | 0 | 0.157 / 0.157 | match |
| C4 | `video3_frame_0302.png:hair` | #000000 | #000000 | 0 | 0.000 / 0.000 | match |
| C5 | `video3_frame_0398.png:salmon` | #EDA094 | #EDA094 | 0 | 18.342 / 18.342 | match |
| C5 | `video3_frame_0398.png:brown` | #A68A67 | #A68A67 | 0 | 1.260 / 1.260 | match |

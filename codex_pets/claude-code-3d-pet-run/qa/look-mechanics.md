# Claude Code 3D look mechanics

## Natural motion

This pet is one rigid rounded rectangular toy whose body is also its head. It has two square white inset eye panels without pupils, two short attached side arms, and four short feet. The four feet and lower body remain the stable screen-space anchor. Looking is expressed by a small physical yaw or pitch of the molded body around that anchored base, plus coherent perspective changes in the front face, top bevel, side planes, eye panels, and attached arms. Do not rotate, skew, or tilt the whole raster cell.

The square eye panels stay the same molded square design. They move with the front face as rigid inserts; no pupils, irises, googly eyes, replacement whites, or extra facial layer. The nearer eye may appear slightly larger and the farther eye slightly narrower/partly occluded through perspective, but neither detaches from the orange face.

## Anchors and follow-through

- Anchored: four feet, lower-body center, baseline, overall scale.
- Leads: front face orientation and the two square eye panels as part of that rigid face.
- Follows: upper body bevel and attached arms with a very small continuous lag.
- Lighting: fixed in screen coordinates from the upper-left; it never flips with direction.
- No props, shadows, floor, glow, labels, arrows, detached effects, or whole-sprite rotation.

## Cardinal pose families

- `000 up`: feet stay planted; body pitches subtly backward around the lower anchor. More of the top bevel is visible, the eye panels sit visually higher on the receding front face, and both arms follow slightly backward. Front face remains readable.
- `090 screen-right`: body yaws subtly toward the screen-right edge. The screen-left side plane becomes a little more visible, the front face foreshortens toward screen-right, the eye panels translate together toward screen-right in perspective, and the far eye narrows slightly. The rightward direction must read without labels.
- `180 down`: feet stay planted; body pitches subtly forward. Less top bevel and more lower/front bevel are visible, eye panels sit visually lower, and the upper body compresses slightly without scaling the whole pet.
- `270 screen-left`: body yaws subtly toward the screen-left edge. The screen-right side plane becomes a little more visible, the front face foreshortens toward screen-left, the eye panels translate together toward screen-left in perspective, and the far eye narrows slightly. This must visibly oppose `090`.

## Motion budget

Each 22.5-degree step changes body yaw/pitch, side-plane visibility, eye-panel perspective, and arm follow-through by roughly one equal increment. The feet, lower-body center, baseline, scale, orange material, and screen-upper-left lighting remain stable. Diagonals blend the adjacent cardinal families; no adjacent pair may flip the visible side, jump the anchor, change the number of feet, or pop in scale. `157.5 -> 180` and `337.5 -> 000` must each be one ordinary step.

## Convergence revision after row-9 cycle

The first two coherent row-9 attempts showed that broad body yaw/pitch causes semantic reversal or collapses the wide rectangular body into a narrow profile. Use a more constrained screen-face mechanism from this point forward:

- Keep the orange body front-face width at least 80% of the neutral front-face width in every direction; never show a near-profile pose.
- Keep overall body height, arm span, four-foot spacing, body volume, and baseline within a small visual tolerance of neutral. Direction must not come from narrowing, stretching, or scaling the whole body.
- The two square white panels act as embedded display panels on the front face. They remain identical squares and aligned on one horizontal row. Vertical translation plus top/lower bevel visibility carries up/down; horizontal translation plus only a small side-plane thickness change carries left/right. Near `090` or `270`, perspective may compress their separation to about 47% of neutral spacing, but it must change monotonically in equal increments and never snap between adjacent cells.
- Limit side-plane reveal to a modest bevel/side strip comparable to the approved 090 and 270 anchors. Preserve most of the wide front face.
- `000` and `180` retain the same wide silhouette as neutral. `000` moves both panels clearly upward and shows more top bevel; `180` moves both panels clearly downward and shows more lower/front bevel.
- `090` and `270` retain the wide silhouette and use opposite panel translation plus opposite modest side-plane reveal. From a vertical cardinal to a horizontal cardinal, panel separation eases `100% -> 87% -> 74% -> 60% -> 47%`; from a horizontal cardinal to the next vertical cardinal it eases back `47% -> 60% -> 74% -> 87% -> 100%`. Pair-center position, panel height, and bevel cues follow the same monotonic schedule without lateral backtracking.

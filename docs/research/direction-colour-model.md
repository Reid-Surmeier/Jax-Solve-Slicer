# How a multi-colour filament's colour follows travel direction

Research for [Establish how a multi-colour filament's colour follows travel direction](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/18), 2026-10-07. It feeds the preview being built under [the reconstruction map](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/17).

This is research. Nothing was printed. The photos of the reference plate are other people's work and are not in this repository; the numbers below were measured from local copies.

**How to read it.** Every statement is tagged by where it comes from:

- **Source** — text on a fetched page, linked inline. All pages were fetched on 2026-10-07. A background pass read them first; every quote used here was then fetched again and found on the page.
- **Published image** — my reading or measurement of a picture or video frame on such a page. Numbers taken from pixels are mine, not the author's.
- **Photos** — measured or seen in the two photos of the reference plate (front, and bed side).
- **Inference** — reasoning of this note. No source says it outright.
- **From the owner** — what the owner saw holding the plate.
- **Unknown** — could not be settled.

**Frame used throughout.** The plate seen from the front, long side horizontal, the way the picture reads. x points right, y points up. A heading is the direction the nozzle travelled: 0° is rightwards, 90° is upwards, counter-clockwise positive. Tone runs from 0 (the dark colour) to 1 (the light colour). Bed-side numbers use the same convention looking at the bed side.

## Short answer

1. **The first guess holds, with the axis turned.** Tone follows `0.5 + 0.5·cos(heading − axis)`. A full turn of heading measured round one ring of loops on the front fits a cosine to within 0.10 of the dark-to-light span. A step with a narrow transition is ruled out everywhere: going from 10% to 90% light takes about 100° of heading. Nobody has published the curve. One published photo of a single bead favours a straight line in angle over a cosine; the two never differ by more than 0.10, and the plate's own photos sit on the cosine. (Photos, published image, sources.)
2. **A sideways bead is two stripes.** Travelling across the colour axis, one bead shows both colours side by side along its length. The stripes are visible in the photos on both faces. The cosine is what the eye gets when it averages them. (Photos, with a geometric reason under inference.)
3. **Opposite headings give opposite tones, and the curve is symmetric.** On the flat bed side the four sides are four distinct tones: black, black-grey, mid grey, light. The two in-between tones average to the same value as the black and the light, to within 2% to 5% in linear light. A cosine whose axis is turned 34° from the plate's edges reproduces all four; the curve does not need to be lopsided. (Photos, and from the owner.)
4. **Travel sense is not "every loop the same way round".** On the front, tone flips across each outline while the lines stay parallel. That fits loops travelled with the uphill side of the distance field always on the same hand, which makes the picture read as a relief lit from one side. (Photos and inference.)
5. **The axis is not the same on the two faces.** It sits about 8° off the plate's long edge on the front and about 34° off on the bed side. The preview needs one axis per face. (Photos; cause unknown.)
6. **Top face against bed face: probably opposite colours, not confirmed.** The sources' picture of the bead says so. The photos alone cannot tell, because turning the plate over and reversing the colours look the same. The way the owner holds the plate points to opposite colours if he turned it over like a page. (Sources, inference, from the owner.)
7. **Sheen** adds a term that depends on which way the lines run, not on which way they were travelled: about ±0.11 of the span in the front photo. It belongs in the renderer's lighting, not in the tone curve. (Photos; renderer values are inference.)

## What the sources say

### Nobody has published the curve

- **Source.** The one study of this effect is about a hotend that merges three filaments in one nozzle without blending them, not factory-made two-colour filament. It gives a geometric model and no measured curve. Its last sentence: "we suggest a more precise quantification of the effects of both printing direction and change of the mixing ratio in future work." [Tonello et al., accepted manuscript](https://people.compute.dtu.dk/jerf/papers/hotend.pdf) of the [Springer chapter](https://link.springer.com/chapter/10.1007/978-981-99-9666-7_7)
- **Source.** It checked the model by eye on one test print: "we found a reasonable correlation", and "opposite print directions have slightly different colors". Its filaments were translucent. [same manuscript](https://people.compute.dtu.dk/jerf/papers/hotend.pdf)
- **Source.** Makers state only the rule: "Depending on the direction in which you're printing, one or the other color is on top." [CNC Kitchen, 2021](https://www.cnckitchen.com/blog/dual-color-dichromatic-3d-printing-filament)
- **Not found.** Any published tone-against-heading curve, table or fit for two-colour or three-colour filament. Any colour-wheel or spiral test disc with measurements. Any micrograph of a real two-colour bead cut across. Reddit threads and one project page could not be fetched and were not read.

### Which half ends up on top

- **Source.** "the material in the rear part of the nozzle tip with respect to the printing direction comes out on top." The same paper gives the reason, with a warning: the rear part "receives a slight upward pressure that covers the front part. However, this is not always consistent". [Tonello et al.](https://people.compute.dtu.dk/jerf/papers/hotend.pdf)
- **Published image.** CNC Kitchen's two diagrams show the same thing. The page's own caption for one: "Diagram of the nozzle printing to the left, laying the blue half underneath and the orange half on top". [CNC Kitchen, 2021](https://www.cnckitchen.com/blog/dual-color-dichromatic-3d-printing-filament)
- **Source, forum user.** "one side of the print will be mainly red, one mainly black and top and bottom dependant on the direction of the surface pattern." [Bambu forum](https://forum.bambulab.com/t/how-to-manage-silk-dual-color-finishes/139398)

### A single bead, all the way round

- **Published image.** CNC Kitchen's article has a photo of a one-bead-wide ring in pink and blue, taken from above and captioned "Circular Extrusion". At 9 o'clock the bead is blue on its outer half and pink on its inner half. At 3 o'clock it is the other way round, so blue is on the same side of the machine both times. At the top it is nearly all pink, at the bottom nearly all blue. [CNC Kitchen, 2021](https://www.cnckitchen.com/blog/dual-color-dichromatic-3d-printing-filament)
- **Published image, measured twice.** I sorted the bead's pixels into pink and blue by hue and took the pink share of the bead's width every 10° round the ring. The background pass and my own repeat agree. There is one boundary across the bead everywhere, and it moves across at a steady rate: about 0.05 of the width per 10°. The share runs from about 0.15 to about 1.0.
- **Published image, measured.** A straight line in angle (a triangle wave) fits that with an rms error of 0.020, a cosine with 0.028, both with the range left free. With the range pinned to 0 to 1, the errors are 0.06 and 0.12. A curve with a flat stretch of 60° or more fits worse than either.
- **Limits.** One photo, one filament, a bead with nothing beside it, travel sense unknown. The pink-to-blue hue cut-off moves the numbers a little (0.020 and 0.028 become 0.028 and 0.039 at another cut-off) but not the order.

### A dense concentric top

- **Source.** A Prusa forum post shows two round plates with a concentric top in pink and blue. For one, "the nozzle printed half of the plate clockwise, and the other half counter-clockwise." [Prusa forum](https://forum.prusa3d.com/forum/prusaslicer/arachne-concentric-top-fill-pattern-dual-color-filament-failure-visual-only)
- **Published image.** The plate whose loops all run one way shows one smooth sweep round the disc, pink through purple to blue, with no sharp edge. The other shows bands that alternate, pink beside blue, which is what reversing the travel does.
- **Published image, measured by the background pass, not repeated by me.** The colour share round three bands follows straight ramps: 0.74 to 0.77 at 45° from the purest heading, where a cosine gives 0.85 and a straight line 0.75. That verdict depends on how colour is turned into a share; cruder conversions make the cosine fit as well. Every conversion rules out a step.

### Sideways beads and neighbours

- **Published image.** In CNC Kitchen's photo of a striped top, the two perimeter beads that cross the infill direction each show a pink half and a blue half, and both halves stay visible on both beads. The neighbour does not cover a stripe. [CNC Kitchen, 2021](https://www.cnckitchen.com/blog/dual-color-dichromatic-3d-printing-filament)
- **Source.** A neighbour can do something else: "The borders and the proximity between lines can dirty the tip and drag undesired color onto other parts of the prints." [Tonello et al.](https://people.compute.dtu.dk/jerf/papers/hotend.pdf)

### Top face against bed face

- **Published image.** CNC Kitchen's diagram stacks the two halves, so the top and the underside of one bead are opposite colours. It is a drawing, not a photo. [CNC Kitchen, 2021](https://www.cnckitchen.com/blog/dual-color-dichromatic-3d-printing-filament)
- **Source and published image.** The designer of a four-filament hotend shows it on a real part: a square with a concentric fill, four triangles of different tone, turned over on camera. "Have a look at how great this works if I flip this piece. So, it's black here and it's brownish orange like on the other side." On the top face the left triangle is brownish gold and the right is black. On the bed face the right is bright gold and the left is black. [video, 07:55 to 08:10](https://youtu.be/6pM_ltAM7_s); the quote is from automatic captions.
- **Inference.** That is opposite colours if he rolled the part top over bottom, which is how the frames look to me and to the background pass. Confidence in the roll: medium. The hotend held three black filaments and one orange, so it is not a two-colour strand.
- **Published image.** The bed face in that video is cleaner than the top: one bright triangle and three near-black ones, against in-between browns on top.
- **Inference from the paper's simulation, low confidence.** In its computed bead sections (its figure 8) the material at the leading edge of the nozzle lies as a floor under almost the whole bead, while the material at the trailing edge caps only part of the top. The background pass read the shares off the figure as 85% to 98% of the underside against 49% to 61% of the top; I looked at the figure and agree in kind, and did not re-measure. If two-colour silk does the same, the bed face has a steeper curve than the top face. The simulation is three-colour and idealised.

### The axis is not lined up with the printer

- **Source.** "one color runs along one side of the strand, and the other color sits on the opposite side." If the strand rotates in the drive gears "it can flip 180 degrees, causing the colors to reverse mid-print." [Polymaker wiki](https://wiki.polymaker.com/printing-tips/common-printing-issues/dual-color-filament-swapping-flipping)
- **Source.** "there is a small chance of filament rotation, potentially causing uneven color transitions." [Bambu store](https://us.store.bambulab.com/products/pla-silk-multi-color)
- **Source, a maker's test piece.** Multi-colour filaments "tend to maintain their orientation once a few hundred millimetres have been extruded but they rarely align perfectly with the cardinal points of your printer's bed". [Printables model 370949](https://www.printables.com/model/370949), read through the site's API.

### Sheen

- **Source.** Sheen cannot tell a line from its reverse: "going to the right or the left when extruding material gives the same anisotropic appearance." The paper uses a standard reflectance model, a "microfacet BSDF with anisotropic Beckmann distribution", set by a roughness along the bead and one across it. [Chermain et al., 2023](https://xavierchermain.github.io/data/pdf/Chermain2023Orientable.pdf)
- **Source.** They measured printed top faces with a stylus and found the "lowest roughness along the printing direction". Their table gives (along, across) for a 0.4 mm nozzle: Blue PLA 2.36 and 17.32, Grey PLA 4.46 and 15.81. The unit is not stated. [same paper](https://xavierchermain.github.io/data/pdf/Chermain2023Orientable.pdf)
- **Source.** Their code lists the filaments measured: a "Silk Gloss PLA Brillant Blue" and an ordinary "PLA+ Bleu/Gris". [repository README](https://github.com/mfx-inria/anisotropic_appearance_fabrication)
- **Inference.** So the blue row is a silk PLA and the grey row an ordinary one. Along the bead the silk is about half as rough. Across the bead they are alike, because that figure is mostly the bead's own rounded shape. Silk's shine is a smoother skin along the line on the same ridge.
- **Source, weak.** What makes it shine: "it's elastomers that leave your prints looking glossy and gorgeous." [Raspberry Pi magazine](https://magazine.raspberrypi.com/articles/silk-filament-printing). No maker's statement of the additive, and no gloss measurement, was found.

## What the photos show

### How they were measured

- **Photos.** Two phone photos, 4284 × 5712 pixels, tagged Display P3, no exposure data. Pixels were linearised with the sRGB curve and converted from P3 to sRGB primaries. All luminance values below are that linear value (Y, 0 to 1). "Tone" is a linear position between a dark and a light reference named each time.
- **Photos.** Each photo was warped to the plate's own rectangle from its four corners, read by eye to about 5 pixels. Line direction was taken from the image gradient over small blocks (a structure tensor), checked first on synthetic stripes at known angles. Lines are about 6.9 pixels apart on the front, so about 364 lines cross the plate's short side. On the bed side they are about 10% wider apart.
- **Limits, not corrected.** A phone photo is tone-mapped, so "linear" is approximate. Lighting is uneven in both. The front is glossy and slightly raised, so facets catch highlights. The bed-side photo is dim, strongly yellow, and has screen glare across its dark triangle. No grey card or known white is in either frame. I did not correct for any of this; where a comparison escapes it, the text says how.

### Front: one full turn of heading

- **Photos.** One form on the front is surrounded by a ring of a dozen or more near-elliptical loops. Round the ring the line direction turns through 360° within a small area, so lighting changes little. 691 blocks were sampled. Each was given a heading by taking the loops counter-clockwise as seen; whether the nozzle really went that way is not visible.

| Heading from the lightest heading | Measured tone | Cosine | Difference |
| --- | --- | --- | --- |
| 0° | 0.92 | 1.00 | −0.08 |
| +30° | 0.90 | 0.93 | −0.03 |
| +60° | 0.80 | 0.75 | +0.05 |
| +90° | 0.59 | 0.50 | +0.09 |
| +120° | 0.31 | 0.25 | +0.06 |
| +150° | 0.00 | 0.07 | −0.07 |
| ±180° | −0.08 | 0.00 | −0.08 |
| −150° | −0.01 | 0.07 | −0.07 |
| −120° | 0.33 | 0.25 | +0.08 |
| −90° | 0.65 | 0.50 | +0.15 |
| −60° | 0.78 | 0.75 | +0.03 |
| −30° | 0.81 | 0.93 | −0.12 |

Tone here is measured between the fitted cosine's own dark (Y 0.144) and light (Y 0.433), which is why the ends fall slightly outside 0 to 1.

- **Photos.** Fits, each heading bin weighted equally:

| Curve | Misfit (rms, share of span) | What it says |
| --- | --- | --- |
| Cosine | 0.100 | Lightest heading 171.5°, ±0.7° from resampling alone. |
| Cosine with a sharpness knob (`tanh(k·cos)`; k = 0 is a cosine, large k is a step) | 0.100 | k = 0.31, 95% range 0 to 0.63. No better than the cosine. 10% to 90% light takes 99° to 106° of heading; a pure cosine takes 106°. |
| Cosine plus a term that repeats every 180° | 0.065 | The extra term is ±0.11 of the span, brightest where lines run at about 77°, that is near vertical. |

- **Inference.** A term that repeats every 180° cannot tell a line from the same line travelled backwards, so it is not pigment. It is sheen and lighting: near-vertical ridges caught more light in this photo. With it removed, what is left is a cosine.
- **Photos, cosine against straight line.** A shape knob that bends the cosine towards a straight line in angle (`cos d + c3·cos 3d`; c3 = 0 is the cosine, c3 = 0.11 is close to a triangle wave) fits at c3 = −0.01, 95% range −0.03 to +0.02, in linear light. Done on the encoded pixel values instead it gives +0.03. So this plate's top sits on the cosine, not on the straight line the published single-bead photo shows.
- **Limit.** The phone's tone curve flattens highlights and shadows, which would push a straight line towards a cosine. I cannot rule that out. The two shapes are at most 0.10 apart.
- **Photos.** The darkest heading is not exactly opposite the lightest: the raw bins put them about 165° apart. The cosine fit splits the difference. I treat ±5° as the real uncertainty of the axis, not the ±0.7° above.

### Front: the border

- **Photos.** The outer part of the front is concentric rectangles, as on the bed side. Tones, measured between the border's own dark (bottom band, Y 0.075) and light (top band, Y 0.410):

| Band | Line direction | Tone | Cosine with axis 171.5° |
| --- | --- | --- | --- |
| Top | horizontal | 1 (reference) | 0.99 |
| Bottom | horizontal | 0 (reference) | 0.01 |
| Right | vertical | 0.79 to 0.90 | 0.57 |
| Left | vertical | 0.35 to 0.54 | 0.43 |

- **Photos.** The right band is the worst miss in the whole set, 0.2 to 0.3 too light. It is strongly striped, and its light stripes peak at Y 0.50, above the plain light level of 0.41 to 0.46. The left band is at the soft edge of the photo and shows almost no stripes.
- **Inference.** The right band's excess is highlight on ridges, the same effect as the 180° term above but stronger at that spot. I could not separate it from pigment.

### Bed side: four tones

- **From the owner.** The four sides of the bed-side fill are four distinct tones: a black, a black-grey, a mid grey and a light side. Held the way he holds it, the left side is the black-grey. A cosine lined up with the plate's edges is wrong for this face: it makes the two in-between sides the same.
- **Photos.** The photo agrees on all of that. Turned upright it shows black along the top, black-grey on the left, light along the bottom and mid grey on the right. Lines in each side run parallel to that side's edge.
- **Photos.** Sampled next to the centre, where the four sides meet and share the same light:

| Side, as the owner holds it | Lines | Y (linear) | Grey level in the photo (0 to 255) | Tone between black and light |
| --- | --- | --- | --- | --- |
| Top: black | parallel to long edge | 0.053 to 0.054 | 65 | 0 |
| Left: black-grey | parallel to short edge | 0.085 to 0.087 | 83 | 0.16 to 0.18 |
| Right: mid grey | parallel to short edge | 0.219 to 0.225 | 130 | 0.77 to 0.89 |
| Bottom: light | parallel to long edge | 0.246 to 0.254 | 137 | 1 |

- **Photos.** Is a turned cosine enough? A cosine with a free axis passes through four headings 90° apart only if the two pairs of opposite sides have the same mean. They do: black and light average Y 0.149 to 0.154, black-grey and mid grey average 0.152 to 0.156. The same check done with ratios across the diagonal seams, where both sides share the light exactly, gives 0.607 against 0.592. So the curve is symmetric to within 2% to 5%, and a lopsided curve is not needed.
- **Photos.** The axis that fits is 34° from the plate's long-edge direction, ±3° (32° from seam ratios, 34° to 36° from the centre samples; wider sampling drifts to 40° as the lighting gradient comes in). The preview's stand-in of 30° is close to it.
- **Inference.** With the axis turned that far, none of the four sides shows a pure colour. Their tones on the cosine are 0.085, 0.22, 0.78 and 0.915. The pigment ends lie beyond the black and the light sides: the fit puts the light colour about 8 times brighter than the dark in linear light.
- **Inference, why it looks lopsided.** The tones are symmetric in linear light, but the eye and an sRGB screen stretch the dark end. In the photo's own grey levels the two dark sides are 18 apart and the two light sides 7 apart. A preview that mixes the two colours in linear light gets this for free. One that mixes encoded values, or views through a tone-compressing transform, will not.
- **Photos against the owner.** The photo puts the mid grey side only about 10% to 20% below the light side in linear light. If it looks further from the light side in the hand, the photo does not show it; glare and the yellow light may be hiding it. I could not check.
- **Photos, error scale.** Away from the centre the black side reads up to three times lighter because of screen glare. Ratios across the four seams, taken along their whole length, should multiply to 1 and multiply to 0.82. Treat each tone as good to about ±0.05, and the black level as the least certain.
- **Inference, limit.** Four headings cannot test the curve's shape. A steeper curve with a smaller turn would pass through the same four points, and the sources hint the bed side may be steeper than the top.
- **Photos and inference, one shape it does exclude.** A straight line in angle would put the axis at about 36° and need a dark colour that reflects nothing at all (the fit lands slightly below zero, at −2% to −5% of the light). The cosine needs a dark about 8 times dimmer than the light, which matches the front. So the bed side is at least as rounded as a cosine.

### What a sideways bead looks like

- **Photos, front.** Where lines run across the axis (the right band, and the left and right sides of the ring), each line is a light stripe beside a dark stripe, about half and half, at the same spacing as the lines elsewhere. Where lines run along the axis, the surface is one even tone with only faint line marks. Round a curve the light stripe widens or narrows smoothly; it does not jump.
- **Photos, bed side.** Both short-side triangles are striped too: one mostly dark with thin light stripes, the other mostly light with thin dark stripes. Both long-side triangles are even.
- **Photos, limit.** The stripes are too close to the camera's sharpness limit to measure their widths. A folded average across one bead comes out as a smooth wave for every patch. So the share of each colour is taken from mean tone, not from stripe width.
- **Unknown.** Whether the next bead's overlap hides part of one stripe on this plate. It would make the two sideways headings differ, and they do differ on both faces, but an axis that is not square to the lines does the same thing. The published photos show both stripes surviving next to a neighbour, so the turned axis is the likelier cause. In the model below both are absorbed by the axis angle.

### Which way round the loops go

- **Photos.** Inside the ring the top arc is light and the bottom arc is dark. Just outside the ring's outline, with the lines still parallel, the top arc is dark and the bottom arc is light. The same flip happens across the long outline that crosses the plate: a dark band and a light band lie side by side with the same line direction.
- **Inference.** The colour can only flip between parallel lines if the travel direction flips. So the loops are not all travelled the same way round. The pattern fits lines that are contours of "distance to the nearest outline", travelled with the uphill side always on the same hand. Distance rises on both sides of an outline, so the sense reverses across it.
- **Inference.** Under that rule tone depends only on which way the field's slope points: `tone = 0.5 + 0.5·cos(slope direction − 261.5°)`, lightest where the slope points down the plate and slightly to the left. That is the shading of a relief lit from one side, which is how the plate reads.
- **Photos.** The border loops and the ring's inner loops have the same sense: both are light along their top run.
- **Unknown.** Which of the two hands it is. "Uphill on the left, lightest heading 171.5°" and "uphill on the right, lightest heading 351.5°" give the same picture. A weak hint for the first: the plate's right edge ends on a bright stripe and its left edge does not, which is what a light half facing right would give. An edge highlight would look the same.

### Top face against bed face, from the photos

- **Photos.** Front: light along the top long edge, dark along the bottom. Bed side: light along one long edge, dark along the other.
- **Unknown.** Which bed-side long edge is the back of which front edge. Nothing in either photo marks an edge.
- **Inference.** Without that, the photos cannot answer. Reversing the colours of this pattern is the same as turning it half a turn, so "opposite colours, plate turned over like a page" and "same colours, plate turned over top to bottom" give the same two pictures.
- **From the owner, and inference.** As he holds the bed side, black is along the top. The front reads upright with light along the top. If he got from one view to the other by turning the plate like a page, the same physical edge is light on the top face and black on the bed face: opposite colours, as the sources' picture predicts. Whether he turned it that way is not recorded, so this is a pointer, not a confirmation.
- **Photos.** The two faces differ in one way that no turning explains: the axis is about 8° off the long edge on the front and about 34° off on the bed side. If the plate was turned like a page and the colours are opposite, the gap is 25°. The other reading gives 41°.
- **Unknown.** Why the axes differ. Two candidates: the strand turned in the nozzle between the first layer and the last, which makers report happens, or the bed side has a steeper curve than the top.

### Colours, as photographed

- **Photos.** Front photo, five light patches and six dark patches across the plate:

| Colour | sRGB | Spread across patches | Linear Y |
| --- | --- | --- | --- |
| Light | 172, 177, 177 | ±6 per channel | 0.433 (0.39 to 0.46) |
| Dark | 90, 86, 82 | ±12 per channel | 0.094 (0.057 to 0.128) |

- **Honest error bars.** The spread above is only patch-to-patch. Exposure and tone mapping are unknown, so the pair could move together by ±15 per channel. The dark value includes reflected room light and is the less certain, ±20.
- **Photos.** Light is 4.6 times brighter than dark in linear light on the front on average (3.1 to 8.1 depending on the pair of patches). The darkest front patch gives 7.6.
- **Inference, the dark pigment.** Reflections only add light, so the pigment is at the dark end of that range. The bed-side fit agrees: it puts light about 8 times brighter than dark. A base colour for a renderer that adds its own reflections is therefore nearer sRGB 68, 66, 63 (linear Y 0.055) than the average above.
- **Unknown, colour cast.** The light colour reads as a faintly blue silver-grey and the dark as a neutral charcoal. The table and wall behind the plate read cream. If they are really white, the photo is warm and the light colour is distinctly blue (about 157, 177, 213). If they are really cream, it is not. The bed-side photo is too yellow to help. The filament's name would settle it.

## Why a cosine, or a straight line (inference)

No source gives the curve. Two simple pictures of the bend give two curves.

- The strand is a round rod split in two along a diameter. It leaves the nozzle downwards and is bent flat onto the surface, trailing behind the nozzle. The trailing side of the rod becomes the top of the bead and the leading side the underside (sourced above). The rod's left and right stay the bead's left and right.
- **Picture one: looking straight down.** Each point across the bead's top shows the trailing rim point directly above it. The colour boundary then sits at `cos(heading − axis)` across the bead, in units of half its width, and the light share of the top is exactly `0.5 + 0.5·cos(heading − axis)`.
- **Picture two: the rim unrolled.** The trailing half of the rim is laid flat, each degree of rim becoming an equal width of bead. The boundary then crosses the bead at a constant rate and the light share is a straight line in angle, `1 − d/180`, where d is the angle from the lightest heading. The published single-bead ring looks like this.
- Both give the same stripes: all light when the light half trails, all dark when it leads, half and half when travelling across the axis. They differ most at 30° from the pure headings, by 0.10.

| Angle from lightest heading | Cosine | Straight line |
| --- | --- | --- |
| 0° | 1.00 | 1.00 |
| 30° | 0.93 | 0.83 |
| 60° | 0.75 | 0.67 |
| 90° | 0.50 | 0.50 |
| 120° | 0.25 | 0.33 |
| 150° | 0.07 | 0.17 |
| 180° | 0.00 | 0.00 |

- Both pictures say which side: when the heading is counter-clockwise from the lightest heading, the light stripe is on the left of travel; when clockwise, on the right. The published ring agrees that each colour stays on its own side of the machine, and matches the left-and-right rule if it was printed counter-clockwise. Its travel sense is not stated; counter-clockwise is the usual slicer default as I recall, not checked.
- Both put the leading half on the underside, so the bed face of a first-layer bead would show the complement, `1 − tone`, at least roughly.

A real bead is squashed and smeared by the nozzle's flat tip, so neither picture is a law. The cosine is kept below because it fits the reference plate on both faces, and the plate is what the preview is judged against.

## Sheen (photos, then inference)

- **Photos.** Tone in the front photo carries a part that depends only on which way the lines run: ±0.11 of the span over the ring, more at the right border. Light stripes on sideways beads peak about 10% to 25% above the plain light level. Nothing is blown out except single beads at sharp corners. The bed side shows no such term: its two pairs of opposite regions have the same mean.
- **Inference, for a renderer.** Treat the pigment tone as base colour only, and let the lighting make the sheen. The roughness numbers come from the stylus table quoted above, read as degrees of slope, which is my assumption:
  - Each bead is a rounded ridge. Model the ridges as real geometry or a normal map, not as a flat colour.
  - With the ridges modelled: roughness about 0.25, little or no anisotropy. The ridge shape already supplies the difference between along and across; adding anisotropy on top counts it twice.
  - Without the ridges, on a flat surface: roughness about 0.4, anisotropy close to 1, tangent along the travel direction. That stands in for a skin that is smooth along the line (slope 2.4) and ridged across it (slope 17).
  - Not metallic. The silver look comes from the pigment and the gloss.
  - The bed side takes the bed's texture instead: rougher (about 0.6), no anisotropy.
  - The conversion from slope to a Blender roughness value is from memory of how the Principled BSDF squares its roughness, and was not checked in Blender.
- **Inference.** On a sideways bead the two colours sit on opposite flanks of the ridge. Light from one side then favours one colour, so the two sideways headings can look different under raking light even when both are half and half. This may be part of why the front's right band reads so light.
- **Unknown.** How these numbers suit this filament. None was measured on the plate; they are starting values to tune against the front photo.

## What stayed unknown

- The curve's shape on the bed side. Four headings fit a turned cosine but cannot rule out a steeper curve.
- Whether the top and bed faces of one bead show opposite colours on this plate. One look settles it: hold the plate front towards you with the light band at the top, turn it over like a page, and see whether the bed side's light side is at the top or the bottom. Opposite colours predict the bottom, which is where the owner's hold puts it if he turned it that way.
- Which way round the nozzle really went. Only the product of sense and axis is fixed.
- Why the front and bed side put the axis 25° (or 41°) apart.
- The stripe widths on a sideways bead, and whether a neighbouring bead hides part of one.
- The true colours. Values are as photographed; the cast is not known.
- How much of the front's right-band brightness is pigment.
- How steady the axis is across a print. The front sweep covers one small area of one layer.

## Model to use

One curve, one axis per face.

```
tone(heading) = 0.5 + 0.5 · cos(heading − axis)      # 1 = light colour, 0 = dark colour
colour        = dark + tone · (light − dark)          # mix in linear RGB, then encode
```

| Parameter | Value | Where it comes from |
| --- | --- | --- |
| Curve | pure cosine, symmetric, no sharpening | Photos: front sweep, and the bed side's four tones. |
| Shape knob `c3`, optional | 0 (cosine). Up to 0.11 bends it towards a straight line in angle | 0 from this plate's photos; 0.05 to 0.11 from the published single-bead photo. |
| Travel sense | contours of the distance field, uphill always on the left | Inference from the photos. |
| `axis`, top face | 171.5°, ±5° (8.5° off the long edge) | Photos, front sweep. Front view. |
| `axis`, bed face | 34°, ±3° (34° off the long edge) | Photos, bed side. Bed-side view. |
| `light` | sRGB 172, 177, 177 (linear 0.413, 0.438, 0.442), ±15 | Photos, as photographed. |
| `dark` | sRGB 68, 66, 63 (linear 0.058, 0.054, 0.050), ±20 | Darkest front patch and the bed-side fit. The average dark patch reads 90, 86, 82 with reflections in it. |

Each `axis` is the heading that shows the light colour, in that face's own view: looking at that face, x right, y up, 0° travelling right, 90° travelling up, with the loops round the plate's border running counter-clockwise as seen. If the code keeps uphill on the right instead, add 180° to both; the picture is the same. The bed-face view is the plate as the owner holds it, black side up.

The same thing without a travel sense, from the slope direction of the distance field (which points inwards along the border):

```
top face:  tone = 0.5 + 0.5 · cos(slope direction − 261.5°)
bed face:  tone = 0.5 + 0.5 · cos(slope direction − 124°)
```

Top face, every 30° of heading:

| Heading | Tone |
| --- | --- |
| 0° | 0.01 |
| 30° | 0.11 |
| 60° | 0.32 |
| 90° | 0.57 |
| 120° | 0.81 |
| 150° | 0.97 |
| 180° | 0.99 |
| 210° | 0.89 |
| 240° | 0.68 |
| 270° | 0.43 |
| 300° | 0.19 |
| 330° | 0.03 |

Bed face, every 30° of heading:

| Heading | Tone |
| --- | --- |
| 0° | 0.91 |
| 30° | 1.00 |
| 60° | 0.95 |
| 90° | 0.78 |
| 120° | 0.53 |
| 150° | 0.28 |
| 180° | 0.09 |
| 210° | 0.00 |
| 240° | 0.05 |
| 270° | 0.22 |
| 300° | 0.47 |
| 330° | 0.72 |

Four sides of a concentric rectangular fill, which is the check the owner made on the bed side:

| Side (view of that face) | Heading | Bed face tone | Grey level, bed face | Top face tone |
| --- | --- | --- | --- | --- |
| Bottom | 0° | 0.91: light | 170 | 0.01 |
| Right | 90° | 0.78: mid grey | 160 | 0.57 |
| Top | 180° | 0.09: black | 83 | 0.99 |
| Left | 270° | 0.22: black-grey | 104 | 0.43 |

Grey levels are sRGB, 0 to 255, for the `dark` and `light` above mixed in linear light, with no lighting or sheen. In the bed-side photo's own dimmer exposure the same four sides read 65, 83, 130, 137. Either way the two dark sides come out further apart than the two light sides.

With the shape knob, d being `heading − axis`:

```
tone = 0.5 + 0.5 · (cos d + c3 · cos 3d) / (1 + c3)
```

Leave `c3` at 0 unless the preview's mid tones look too contrasty against the photos. It changes no tone by more than 0.10, and it should stay at 0 for the bed face.

Notes for whoever wires it in:

1. **Mix in linear light and compare under a plain view transform.** The two dark sides only come out further apart than the two light sides if the two colours are mixed before encoding. A tone-compressing view transform (Filmic, AgX) will pull them together again; use Standard when checking against these numbers. (Inference.)
2. **Expect ±0.10 of tone on the top face.** That is the misfit of the cosine against the front sweep. Most of it is sheen, which the renderer should add through lighting. Do not bake it into the curve.
3. **Stripes, for close views.** Instead of one mixed colour per bead, split the bead's width: a light stripe `tone` wide beside a dark stripe. Put the light stripe on the left of travel when `heading − axis` is between 0° and 180°, on the right otherwise. From normal viewing distance this averages to the mixed colour. The side rule is inference.
4. **The axis belongs to a spool, a print and a layer, not to the method.** This plate shows 8.5° on one face and 34° on the other. A real print needs a test piece to find it, and it can drift.

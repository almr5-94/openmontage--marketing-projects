# Layout Director — Campaign

Build the **master composition** first (`editorial_layout` page type `campaign`), then the variants:
4:5 social (trim `social_4x5`), 9:16, OOH portrait and landscape, double page. Each variant keeps
the safe area for its placement and has a **text-free version** for the media owner.
Crop with `image_crop` (`smart_crop`, gravity on the object) rather than squeezing. Run the checks.

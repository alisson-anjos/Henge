# References and acknowledgements

This page collects the project references that would otherwise be scattered across the README, model manifest and
source comments. The exact downloadable weights, destinations and profiles remain in
[`config/model-repos.example.json`](../config/model-repos.example.json).

## Models and methods

- [MiniMax H3](https://huggingface.co/MiniMaxAI/MiniMax-H3) is the base video model.
- [ComfyUI](https://github.com/Comfy-Org/ComfyUI) executes every generation graph.
- Character Swap v1.1, Motion Transfer v1.0, TARA v1.0, Combined, Head Swap v1.0 and Little More Sharpness are Henge
  task LoRAs by Alisson Anjos; download and license details are in [models and downloads](models-and-downloads.md).
- The Motion Transfer training adapter is from [ostris](https://huggingface.co/ostris/minimax_h3_training_adapter).
- Turbo LoRAs come from drbaph, Kijai and LightX2V, as identified by their direct links in the model manifest.
- BiRefNet supplies background-removal masks; SAM 3.1 supplies subject tracking and masks.
- TAEH3 is derived from madebyollin's temporal autoencoder work and is used only for previews.

## Community contributions

- The optional **Moving plate** feature was inspired by a script and workflow shared by **crinklypaper** in the
  Banodoco Discord community. Henge adapted the idea into automatic per-shot camera tracking: a chosen background
  follows the original camera before Character Swap or Motion Transfer runs. Thank you, crinklypaper.
- Generated audio per shot was inspired by the community `shot_soundtrack.py` shared with the same Anime Recast
  workflow. Henge integrates the soundtrack on its own shot timeline and joins it with the final render.

## Code and licenses

Third-party source incorporated into the repository, bundled fonts and their licenses are documented in
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md). Demo footage credits are stated in the main README and in the
video itself.

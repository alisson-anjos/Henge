import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import edit_modes

# Real VLM answers for two creature references (a Character Swap job, 2026-10-29): the human checklist came back as
# "no <attribute>" for every item, and a comma split turned "no beard, mustache..." into a positive "mustache".
LIZARD=("Male, small stature, slender body; large and rounded head shape, light blue and textured skin tone, large and round orange eyes; "
        "white and spiky hair color, short and tousled hairstyle, no beard, mustache or other facial hair; no upper-body clothing, no garment types, "
        "no exact colors, no fit, no fabric, no textures, no collars, no sleeves, no buttons, no zippers, no pockets, no logos, no patterns and no layers; "
        "no lower-body clothing, no colors, no materials, no fit and no design details; no footwear; no visible accessories; "
        "no distinctive features such as tattoos, scars, wrinkles or makeup")
GOLLUM=("Male, short stature, emaciated body type; pale and mottled skin tone, blue eyes; matted, dark brown hair, no beard, mustache or other facial hair; "
        "no upper-body clothing, bare skin; tattered, dark brown loincloth made of rough, fibrous material, loose fit; bare feet; no visible accessories; "
        "distinctive features include numerous wrinkles, deep creases, visible veins")
HUMAN=("Female, average height, athletic build; oval face, olive skin, brown eyes; long black hair, no beard; red cotton t-shirt with white logo, "
       "short sleeves, fitted; blue denim jeans, slim fit; white sneakers; silver watch; small tattoo on the left wrist")

def test_checklist_echoes_are_dropped_without_turning_into_positive_words():
    text=edit_modes.clean_details(LIZARD,2000)
    for echo in ('mustache','facial hair','garment','zippers','logos','patterns','design details','scars','makeup','tattoos'):
        assert echo not in text,echo
    assert 'no beard; no upper-body clothing; no lower-body clothing; no footwear; no visible accessories' in text
    assert text.startswith('Male, small stature') and 'orange eyes' in text

def test_real_details_after_a_negation_are_kept():
    text=edit_modes.clean_details(GOLLUM,2000)
    assert 'no upper-body clothing, bare skin;' in text and 'loose fit' in text and 'numerous wrinkles' in text
    assert 'mustache' not in text

def test_an_ordinary_person_description_is_unchanged():
    assert edit_modes.clean_details(HUMAN,2000)==HUMAN

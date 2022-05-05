from .ingredient import Ingredient

# a predefined list of unit's
# TODO this approach doesn't work with multi word units (ex. small bunch).
units = {
    "l": ["l", "litre", "litres", "liter", "liters"],
    "ml": ["ml", "millilitre", "milli litre", "millilitres", "milli litres", "milliliter", "milli liter", "milliliters", "milli liters"],
    "g": ["g", "gram", "grams"],
    "mg": ["mg", "milligram", "milli gram", "milligrams", "milli grams"],
    "kg": ["kg", "kilogram", "kilo gram", "kilograms", "kilo grams"],
    "oz": ["oz", "ounce", "ounces", "-ounce"],
    "qt": ["qt", "quart"],
    "fl": ["fl"],
    "tsp": ["tsp", "tsps", "tsp.", "tsps.", "teaspoon", "teaspoons"],
    "tbsp": ["tbs", "TBS", "tbsp", "tbsps", "tbsp.", "tbsps.", "tablespoon", "tablespoons", "Tbsp", "Tbsps", "Tbsp.", "Tbsps."],
    "cup": ["cup", "cups", "c."],
    "pint": ["pint", "pints"],
    "pinch": ["pinch"],
    "dash": ["dash"],
    "bunch": ["bunch"],
    "pack": ["pack", "packet"],
    "strip": ["strip", "strips"],
    "can": ["can", "cans"],
    "envelope": ["envelope", "envelopes", "sheet", "sheets"],
    "gal": ["gal", "gallon", "gallons"],
    "lb": ["lb", "lbs", "lb.", "lbs.", "pound", "pounds", "-pound"],
    "whole": ["whole"],
    "head": ["head", "heads"],
    "clove": ["clove", "cloves"],
    "bunch": ["bunch", "bunches"],
    "handful": ["handful", "handfuls", "Handful", "Handfuls"],
    "piece": ["piece", "pieces"],
    "whole": ["whole"],
    "large": ["Large", "large"], # e.g.: "One large potato"
    "medium": ["Medium","medium"],
    "small": ["Small","small"],
    "inch": ["inch", "inches", "\""], # e.g.: "2-3inch piece of ginger" or 2-3" piece of ginger
    "cm": ["cm"] # see inch…
}


def parse_ingredient(raw_ingredient : str) -> Ingredient:
    """ Tries to extract the quantity, the unit and the ingredient itself from a string """
    ing=Ingredient()
    ing.parse(raw_ingredient)
    return ing

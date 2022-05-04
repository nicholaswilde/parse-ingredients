import unicodedata
import subprocess
import re
import tempfile
import json
import sys
from types import SimpleNamespace
from dataclasses import dataclass

@dataclass
class Ingredient:
    name : str
    quantity : int
    unit : str
    comment : str
    original_string : str

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

# numbers with a simple slash fraction (1 1/3, 2 4/5, etc.)
numberAndSlashFraction = re.compile(r'(\d{1,3}?\s\d\/\d{1,3})')
# Vulgar fractions (½, ⅓, etc.)
fractionMatch = re.compile(r'[\u00BC-\u00BE\u2150-\u215E]')
# numbers (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
numberMatch = re.compile(r'(\d)')
# numbers and fractions (1⅓, 1 ⅓, etc.)
numberAndFractionMatch = re.compile(r'(\d{1,3}\s?[\u00BC-\u00BE\u2150-\u215E])')
# simple slash fractions (1/2, 1/3, 5/4, etc.)
slashFractionMatch = re.compile(r'(\d{1,3}\/\d{1,3})')
# vulgar slash which is it's own character in unicode.
# for example: 1⁄2, 4⁄3
vulgarSlashFractionMatch = re.compile(r'(\d{1,3}\u2044\d{1,3})')
# number with a vulgar slash in a fraction (1 1⁄2)
numberAndVulgarSlashFraction = re.compile(r'(\d{1,3}?\s\d\u2044\d{1,3})')
# any of the above, where the first character is not a word (to keep out "V8")
quantityMatch = re.compile(r'(?<!\w)((\d{1,3}?\s\d\/\d{1,3})|(\d{1,3}?\s?\d\u2044\d{1,3})|(\d{1,3}\u2044\d{1,3})|(\d{1,3}\s?[\u00BC-\u00BE\u2150-\u215E])|([\u00BC-\u00BE\u2150-\u215E])|(\d{1,3}\/?\d?)%?)')
# string between parantheses, for example: "this is not a match (but this is, including the parantheses)"
betweenParanthesesMatch = re.compile(r'\(([^\)]+)\)')

def isFullTypedFraction(text : str) -> bool:
    if text.find('/') >= 0 or text.find('\u2044') >= 0:
        return True
    else:
        return False

def toFloat(quantity : str) -> float:
    """ Parse a valid quantity string to a float """
    # We're using 'match', which searches only in the front of the string.
    # That way we know that if it's just a fraction (½) it can never be 1 ½, for example.
    # Then just logically look if it's anything else.
    if fractionMatch.match(quantity) is not None:
        return unicodedata.numeric(quantity)
    if slashFractionMatch.match(quantity) is not None:
        splitted = quantity.split('/')
        return int(splitted[0]) / int(splitted[1])
    if vulgarSlashFractionMatch.match(quantity) is not None:
        splitted = quantity.split('\u2044')
        return int(splitted[0]) / int(splitted[1])
    if numberAndFractionMatch.match(quantity) is not None:
        first = numberMatch.match(quantity).group()
        fraction = fractionMatch.search(quantity).group()
        return int(first) + toFloat(fraction)
    if numberAndSlashFraction.match(quantity) is not None:
        first = numberMatch.match(quantity).group()
        fraction = slashFractionMatch.search(quantity).group()
        return int(first) + toFloat(fraction)
    if numberAndVulgarSlashFraction.match(quantity) is not None:
        first = numberMatch.match(quantity).group()
        fraction = vulgarSlashFractionMatch.search(quantity).group()
        return int(first) + toFloat(fraction)
    if numberMatch.match(quantity) is not None:
        return int(quantity)

def average(quantities):
    """ In the case we have multiple numbers in an ingredient string
        '1 - 2 eggs', we can use this function to just average that out.
    """
    # if there is no quantity in the string, there is a good chance the string was
    # just "onion", in which case the quantity should be 1
    if quantities is None or len(quantities) == 0:
        return 1
    total = 0
    n = len(quantities)
    for q in quantities:
        total += toFloat(q.strip(' '))
    return total / n

def cleanhtml(raw_html):
    """ In some recipe websites, the ingredient can contain an HTML tag, mostly an anchor
        to link to some other recipe. Let's remove those.
    """
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext

def parse_ingredient(raw_ingredient : str) -> Ingredient:
    """ Tries to extract the quantity, the unit and the ingredient itself from a string """

    # We're doing a VERY simple parse. This could probably be better with some NLP
    # but we have nowhere near time enough for that during this assignment.

    ingredient = cleanhtml(raw_ingredient)
    quantity = 0
    unit = ''
    name = ''
    comment = ''

    crf_output = _exec_crf_test(raw_ingredient, "./models/ingredients.crfmodel")
    data = import_data(crf_output.split('\n'))
    data = data[0]
    return Ingredient(data["name"].strip(), data["qty"], data["unit"], data["comment"], data["input"])
    sys.exit()
    
    # Recipe websites tend to put a comment between parantheses. 
    # for example: 1 (fresh) egg. Let's see if we can find any and extract it
    betweenMatch = betweenParanthesesMatch.search(ingredient)
    if betweenMatch is not None:
        betweenParentheses = betweenMatch.group()
        comment = comment + (', ' if len(comment) > 0 else '') + betweenParentheses
        ingredient = ingredient.replace(betweenParentheses, '')
        if ingredient[0] == ' ':
            ingredient = ingredient[1:]

    # Some recipe websites tend to put a comment in the end of the line
    # seperated by a comma. Let's see if we can find any and extract it
    # We do this here, pretty early, because there might be numbers in there
    # we don't want to take in account for quantities.
    commaSplitted = ingredient.split(',')
    if len(commaSplitted) > 1:
        comment = comment + ' ' + ', '.join(commaSplitted[1:])
        comment = comment.strip(' ')
        ingredient = commaSplitted[0]


    rest = ingredient

    last_quantity_character = 0

    # First, let's see if we can find any quantity in the forms of:
    # type                              -   example
    # a vulgar fraction                 -   ½ or \u00BC
    # a vulgar slash between numbers    -   1⁄2
    # a normal slash between numbers    -   1/2
    # a number                          -   1 or 2 etc.
    # a number and a vulgar fraction    -   1 ½ or 1½
    match = quantityMatch.findall(ingredient)
    if match is not None and len(match) > 0:
        # Take all found regex matches and take them from their groups into a flat array
        quantity_groups = list(map(lambda x: next(filter(lambda y: y != '', x)), match))

        # We don't want percentages, but we couldn't match them with regex.
        quantity_groups = [i for i in quantity_groups if '%' not in i]
        q_n = len(quantity_groups)
        
        # Find the last character index that matched a quantity
        last_quantity_character = ingredient.rfind(quantity_groups[q_n-1]) + len(quantity_groups[q_n-1])

        # If the last character happens to be in the end of the string...
        # Someone probably said 'see note 1' in the end of his ingredient.
        if last_quantity_character == len(ingredient) or last_quantity_character == len(ingredient) - 1:
            if q_n > 1:
                last_quantity_character = ingredient.rfind(quantity_groups[q_n-2]) + len(quantity_groups[q_n-2])
            else:
                last_quantity_character = 0
            quantity_groups.pop()
    
        quantity = average(quantity_groups)
    
    if last_quantity_character > 0:
        if ingredient[last_quantity_character] == ' ':
            last_quantity_character = last_quantity_character + 1
        rest = ingredient[last_quantity_character:]

    # Now split the rest of the string.
    splitted = rest.strip().split(' ')

    # If the string is just one more word, it's probably safe to assume
    # that there is no unit string available, but we're dealing with, 
    # for example: 1 egg, where egg is both the ingredient and unit.
    if len(splitted) == 1:
        return Ingredient(rest.strip(), quantity, '', comment, ingredient)
    
    # let's see if we can find something in the string that matches any
    # of my defined units. The list isn't finished and will probably miss
    # lot's of them. But by using a predefined list we avoid a situation where
    # "1 fresh egg" gives us a unit "fresh". Here the unit will be undefined 
    # and 'fresh egg' will be the ingredient. This should probably later be 
    # filtered again.

    wouldBeUnit = splitted[0]

    for key in units:
        value = units[key]
        if wouldBeUnit in value:
            unit = key
    
    # If we did have a unit, join the rest of the string
    # if we didn't, join the entire string
    if unit != '':
        name = ' '.join(splitted[1:])
    else:
        wouldBeUnit = splitted[-1]
        for key in units:
            value = units[key]
            if wouldBeUnit in value:
                unit = key
        if unit != '':
            name = ' '.join(splitted[:-1])
        else:
            name = ' '.join(splitted)

    # and voila! The most basic ingredient parser ever.
    # as I said, I'm not too happy with it and NLP would probably
    # be a better fit, but this brings more complexity
    return Ingredient(name.strip(), quantity, unit, comment, raw_ingredient)


def _exec_crf_test(input_text, model_path):
    with tempfile.NamedTemporaryFile(mode='w') as input_file:
        input_file.write(export_data(input_text))
        input_file.flush()
        return subprocess.check_output(
              ['crf_test', '--verbose=1', '--model', model_path,
               input_file.name]).decode('utf-8')
                     
                     

def _convert_crf_output_to_json(crf_output):
    return json.dumps(import_data(crf_output), indent=2, sort_keys=True)
                         
                         
def main(args):
   raw_ingredient_lines = [x for x in sys.stdin.readlines() if x]
   crf_output = _exec_crf_test(raw_ingredient_lines, args.model_file)
   print(_convert_crf_output_to_json(crf_output.split('\n')))

def export_data(line):
    """ Parse "raw" ingredient lines into CRF-ready output """
    output = []
    line_clean = re.sub('<[^<]+?>', '', line)
    tokens = tokenize(line_clean)
    
    for i, token in enumerate(tokens):
        features = getFeatures(token, i + 1, tokens)
        output.append(joinLine([token] + features))
    output.append('')
    return '\n'.join(output)


def tokenize(s):
    """
    Tokenize on parenthesis, punctuation, spaces and American units followed by a slash.
    We sometimes give American units and metric units for baking recipes. For example:
        * 2 tablespoons/30 mililiters milk or cream
        * 2 1/2 cups/300 grams all-purpose flour
            The recipe database only allows for one unit, and we want to use the American one.
                But we must split the text on "cups/" etc. in order to pick it up.
                    """
                
    # handle abbreviation like "100g" by treating it as "100 grams"
    s = re.sub(r'(\d+)g', r'\1 grams', s)
    s = re.sub(r'(\d+)oz', r'\1 ounces', s)
    s = re.sub(r'(\d+)ml', r'\1 milliliters', s, flags=re.IGNORECASE)

    american_units = [
        'cup', 'tablespoon', 'teaspoon', 'pound', 'ounce', 'quart', 'pint'
    ]
    # The following removes slashes following American units and replaces it with a space.
    for unit in american_units:
        s = s.replace(unit + '/', unit + ' ')
        s = s.replace(unit + 's/', unit + 's ')

    return [
        token.strip()
        for token in re.split(r'([,()\s]{1})', clumpFractions(s))
        if token and token.strip()
            ]

def import_data(lines):
    """
    This thing takes the output of CRF++ and turns it into an actual
    data structure.
    """
    data = [{}]
    display = [[]]
    prevTag = None
    #
    # iterate lines in the data file, which looks like:
    #
    #   # 0.511035
    #   1/2       I1  L12  NoCAP  X  B-QTY/0.982850
    #   teaspoon  I2  L12  NoCAP  X  B-UNIT/0.982200
    #   fresh     I3  L12  NoCAP  X  B-COMMENT/0.716364
    #   thyme     I4  L12  NoCAP  X  B-NAME/0.816803
    #   leaves    I5  L12  NoCAP  X  I-NAME/0.960524
    #   ,         I6  L12  NoCAP  X  B-COMMENT/0.772231
    #   finely    I7  L12  NoCAP  X  I-COMMENT/0.825956
    #   chopped   I8  L12  NoCAP  X  I-COMMENT/0.893379
    #
    #   # 0.505999
    #   Black   I1  L8  YesCAP  X  B-NAME/0.765461
    #   pepper  I2  L8  NoCAP   X  I-NAME/0.756614
    #   ,       I3  L8  NoCAP   X  OTHER/0.798040
    #   to      I4  L8  NoCAP   X  B-COMMENT/0.683089
    #   taste   I5  L8  NoCAP   X  I-COMMENT/0.848617
    #
    # i.e. the output of crf_test -v 1
    #
    for line in lines:
        # blank line starts a new ingredient
        if line in ('', '\n'):
            data.append({})
            display.append([])
            prevTag = None
            
        # ignore comments
        elif line[0] == "#":
            pass

        # otherwise it's a token
        # e.g.: potato \t I2 \t L5 \t NoCAP \t B-NAME/0.978253
        else:

            columns = re.split('\t', line.strip())
            token = columns[0].strip()

            # unclump fractions
            token = unclump(token)
            
            # turn B-NAME/123 back into "name"
            tag, confidence = re.split(r'/', columns[-1], 1)
            tag = re.sub('^[BI]\-', "", tag).lower()

            # ---- DISPLAY ----
            # build a structure which groups each token by its tag, so we can
            # rebuild the original display name later.

            if prevTag != tag:
                display[-1].append((tag, [token]))
                prevTag = tag
                
            else:
                display[-1][-1][1].append(token)
                #               ^- token
                #            ^---- tag
                #        ^-------- ingredient

            # ---- DATA ----
            # build a dict grouping tokens by their tag

            # initialize this attribute if this is the first token of its kind
            if tag not in data[-1]:
                data[-1][tag] = []

            # HACK: If this token is a unit, singularize it so Scoop accepts it.
            if tag == "unit":
                token = singularize(token)
                
            data[-1][tag].append(token)
                
    # reassemble the output into a list of dicts.
    output = [
        dict([(k, smartJoin(tokens))
            for k, tokens in ingredient.items()])
        for ingredient in data
        if len(ingredient)
    ]
    
    # Add the marked-up display data
    for i, v in enumerate(output):
        output[i]["display"] = displayIngredient(display[i])
        
        # Add the raw ingredient phrase
        for i, v in enumerate(output):
            output[i]["input"] = smartJoin(
              [" ".join(tokens) for k, tokens in display[i]])
            
    return output

def clumpFractions(s):
    """
    Replaces the whitespace between the integer and fractional part of a quantity
    with a dollar sign, so it's interpreted as a single token. The rest of the
    string is left alone.
        clumpFractions("aaa 1 2/3 bbb")
        # => "aaa 1$2/3 bbb"
    """  
    return re.sub(r'(\d+)\s+(\d)/(\d)', r'\1$\2/\3', s)

def getFeatures(token, index, tokens):
    """
    Returns a list of features for a given token.
    """
    length = len(tokens)

    return [("I%s" % index), ("L%s" % lengthGroup(length)),
            ("Yes" if isCapitalized(token) else "No") + "CAP",
            ("Yes" if insideParenthesis(token, tokens) else "No") + "PAREN"]

def lengthGroup(actualLength):
    """
    Buckets the length of the ingredient into 6 buckets.
    """
    for n in [4, 8, 12, 16, 20]:
        if actualLength < n:
            return str(n)

    return "X"

def isCapitalized(token):
    """
    Returns true if a given token starts with a capital letter.
    """
    return re.match(r'^[A-Z]', token) is not None

def insideParenthesis(token, tokens):
    """
    Returns true if the word is inside parenthesis in the phrase.
    """
    if token in ['(', ')']:
        return True
    else:
        line = " ".join(tokens)
        return re.match(r'.*\(.*' + re.escape(token) + '.*\).*',
                        line) is not None

def joinLine(columns):
    return "\t".join(columns)

def unclump(s):
    """
    Replacess $'s with spaces. The reverse of clumpFractions.
    """
    return re.sub(r'\$', " ", s)

# HACK: fix this
def smartJoin(words):
    """
        Joins list of words with spaces, but is smart about not adding spaces
    before commas.
    """

    input = " ".join(words)
    
    # replace " , " with ", "
    input = input.replace(" , ", ", ")

    # replace " ( " with " ("
    input = input.replace("( ", "(")

    # replace " ) " with ") "
    input = input.replace(" )", ")")
    
    return input

def displayIngredient(ingredient):
    """
    Format a list of (tag, [tokens]) tuples as an HTML string for display.
        displayIngredient([("qty", ["1"]), ("name", ["cat", "pie"])])
        # => <span class='qty'>1</span> <span class='name'>cat pie</span>
    """
                    
    return "".join([
        "<span class='%s'>%s</span>" % (tag, " ".join(tokens))
                for tag, tokens in ingredient
            ])

def singularize(word):
    """
    A poor replacement for the pattern.en singularize function, but ok for now.
    """

    units = {
        "cups": "cup",
        "tablespoons": "tablespoon",
        "teaspoons": "teaspoon",
        "pounds": "pound",
        "ounces": "ounce",
        "cloves": "clove",
        "sprigs": "sprig",
        "pinches": "pinch",
        "bunches": "bunch",
        "slices": "slice",
        "grams": "gram",
        "heads": "head",
        "quarts": "quart",
        "stalks": "stalk",
        "pints": "pint",
        "pieces": "piece",
        "sticks": "stick",
        "dashes": "dash",
        "fillets": "fillet",
        "cans": "can",
        "ears": "ear",
        "packages": "package",
        "strips": "strip",
        "bulbs": "bulb",
        "bottles": "bottle"
    }

    if word in units.keys():
        return units[word]
    else:
        return word

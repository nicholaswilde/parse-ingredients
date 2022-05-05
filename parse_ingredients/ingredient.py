#!/usr/bin/env python
import re
import tempfile
import subprocess
from dataclasses import dataclass
from .tokenizer import tokenize, clumpFractions

@dataclass
class Ingredient:
    name: str
    quantity: int
    unit: str
    comment: str
    original_string: str
        
    def __init__(self, original_string: str=None, name: str=None, quantity: int=0, unit: str=None, comment: str=None):
        """"""
        self.name=name
        self.quantity=quantity
        self.unit=unit
        self.comment=comment
        self.original_string=original_string
        
    def parse(self, raw_ingredient=None, model="./models/ingredients.crfmodel"):
        """"""
        self.original_string = raw_ingredient
        crf_output = self._exec_crf_test(self.original_string, model)
        data = self._import_data(crf_output.split("\n"))
        data = data[0]
        self.name=data["name"].strip()
        self.quantity=data["qty"]
        self.unit=data["unit"]
        self.comment=data["comment"]
        
    def _exec_crf_test(self, input_text, model):
        with tempfile.NamedTemporaryFile(mode='w') as input_file:
            input_file.write(self._export_data(input_text))
            input_file.flush()
            return subprocess.check_output(
                ['crf_test', '--verbose=1', '--model', model,
                input_file.name]).decode('utf-8')

    def _import_data(self, lines):
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
                token = self._unclump(token)

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
                    token = self._singularize(token)

                data[-1][tag].append(token)

        # reassemble the output into a list of dicts.
        output = [
            dict([(k, self._smartJoin(tokens))
                  for k, tokens in ingredient.items()])
            for ingredient in data
            if len(ingredient)
        ]
        # Add the marked-up display data
        for i, v in enumerate(output):
            output[i]["display"] = self._displayIngredient(display[i])
        
        # Add the raw ingredient phrase
        for i, v in enumerate(output):
            output[i]["input"] = self._smartJoin(
                [" ".join(tokens) for k, tokens in display[i]])
        
        return output
        
    def _export_data(self, line):
        """ Parse "raw" ingredient lines into CRF-ready output """
        output = []
        line_clean = re.sub('<[^<]+?>', '', line)
        tokens = tokenize(line_clean)

        for i, token in enumerate(tokens):
            features = self._getFeatures(token, i + 1, tokens)
            output.append(self._joinLine([token] + features))
        output.append('')
        return '\n'.join(output)

    def _getFeatures(self, token, index, tokens):
        """
        Returns a list of features for a given token.
        """
        length = len(tokens)
    
        return [("I%s" % index), ("L%s" % self._lengthGroup(length)),
                ("Yes" if self._isCapitalized(token) else "No") + "CAP",
                ("Yes" if self._insideParenthesis(token, tokens) else "No") + "PAREN"]

    def _isCapitalized(self, token):
        """
        Returns true if a given token starts with a capital letter.
        """
        return re.match(r'^[A-Z]', token) is not None

    
    def _lengthGroup(self, actualLength):
        """
        Buckets the length of the ingredient into 6 buckets.
        """
        for n in [4, 8, 12, 16, 20]:
            if actualLength < n:
                return str(n)
        return "X"

    def _insideParenthesis(self, token, tokens):
        """
        Returns true if the word is inside parenthesis in the phrase.
        """
        if token in ['(', ')']:
            return True
        else:
            line = " ".join(tokens)
            return re.match(r'.*\(.*' + re.escape(token) + '.*\).*',
                            line) is not None

    def _joinLine(self, columns):
        return "\t".join(columns)

    def _singularize(self, word):
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

    def _unclump(self, s):
        """
        Replacess $'s with spaces. The reverse of clumpFractions.
        """
        return re.sub(r'\$', " ", s)

    # HACK: fix this
    def _smartJoin(self, words):
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

    def _displayIngredient(self, ingredient):
        """
        Format a list of (tag, [tokens]) tuples as an HTML string for display.

        displayIngredient([("qty", ["1"]), ("name", ["cat", "pie"])])
            # => <span class='qty'>1</span> <span class='name'>cat pie</span>
        """
              
        return "".join([
                "<span class='%s'>%s</span>" % (tag, " ".join(tokens))
                    for tag, tokens in ingredient
                ])
